"""Verificador independiente de los NC para Weihong NK300 (fresa plana).
- Formato: ASCII, CRLF, sin codigos prohibidos (%, N, T, M06, M07-M09, M71, M73, G43, G49, G28, G53, G04, H),
  numeros con cero inicial y punto decimal, cabecera y final seguros.
- Seguridad: todo G00 en XY por encima de Z>=1 (sobre la madera); dentro de la plancha 1200 x 1200;
  Z minima = cajera mas honda; nunca por debajo de -THICK.
- Exacto (shapely): la fresa plana no entra en material que debe quedar (a cada altura L por encima de la
  punta, el centro a >= r de la zona que debe quedar a >= L).
- Simulacion por rejilla para la imagen img/simulacion_nk300.png.
Uso: python3 verificar_nk300.py --fresa 6
"""
import argparse, math, os, re
import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
from shapely.prepared import prep
import logo as Lg, logo_nk300 as N

ap = argparse.ArgumentParser(); ap.add_argument("--fresa", type=float, required=True); a = ap.parse_args()
Lg.WIDTH, Lg.MARGIN = N.LOGO_W, N.CORNER
R, piece, s = Lg.regions()
D = N.DEPTH
sheet = box(0, 0, *N.SHEET)
keep = {
    0.0: sheet.difference(unary_union([R["verde"], R["letras"], R["barra"]])),
    -D["barra"]: sheet.difference(unary_union([R["verde"], R["letras"]])),
    -D["verde"]: sheet.difference(unary_union([R["cielo"], R["letras"]])),
    -D["letras"]: sheet.difference(R["cielo"]),
}
r = a.fresa / 2
TOL = 0.02
FORBID = re.compile(r"(%|^N\d|T\d|M0?0(?!\d)|M0?1(?!\d)|M0?6(?!\d)|M0?7(?!\d)|M0?8(?!\d)|M0?9(?!\d)|M71|M73|G43|G49|G28|G53|G0?4(?!\d)|H\d)")
NUM = re.compile(r"[XYZF](-?\d+\.\d+)")


def parse(path):
    raw = open(path, "rb").read()
    assert raw.isascii(), "no es ASCII"
    txt = raw.decode()
    assert "\n" not in txt.replace("\r\n", ""), "fin de linea no CRLF"
    lines = [l for l in txt.split("\r\n") if l]
    issues = []
    code = [l for l in lines if not l.startswith("(")]
    for l in lines:
        if l.startswith("(") and not l.endswith(")"): issues.append("comentario mal cerrado: " + l)
    for l in code:
        if "(" in l: issues.append("comentario detras de codigo: " + l)
        body = l
        if FORBID.search(body): issues.append("codigo no permitido: " + l)
        # formato compacto como los .nc que ya funcionan en la maquina: Z2. / X-.011 / X0, sin espacios
        if " " in body: issues.append("espacio en: " + l)
        for w in re.findall(r"[XYZF]-?[\d.]+", body):
            if not re.fullmatch(r"[XYZF](0|-?\d*\.\d*)", w) or re.fullmatch(r"[XYZF]-?\.", w): issues.append(f"numero raro: {w} en {l}")
    sz = Lg.fnum(N.cut_params(a.fresa)["safe_z"])
    if code[:3] != ["G90G21", f"G0Z{sz}", f"M3S{N.cut_params(a.fresa)['rpm']}"]: issues.append(f"cabecera {code[:3]}")
    if not code[3].startswith("G0X"): issues.append(f"primer movimiento {code[3]}")
    if code[-4:] != [f"G0Z{sz}", "M5", "G0X0Y0", "M2"]: issues.append(f"final {code[-4:]}")
    p = {"X": None, "Y": None, "Z": None}; g = None; moves = []
    for l in code:
        m = re.match(r"G([01])(?!\d)", l)
        if m: g = m.group(1)
        new = dict(p)
        for k in "XYZ":
            mm = re.search(k + r"(-?[\d.]+)", l)
            if mm: new[k] = float(mm.group(1))
        if new != p:
            if p["X"] is None and new["X"] is not None and p["Z"] is None: issues.append("XY sin Z conocida")
            if p["X"] is not None and p["Z"] is not None:
                moves.append((g, (p["X"], p["Y"], p["Z"]), (new["X"], new["Y"], new["Z"])))
            p = new
    return moves, issues


def check(path):
    moves, issues = parse(path)
    preps = {L: prep(G) for L, G in keep.items()}
    zmin = 0; worst = 0; n = 0; tcut = 0
    for g, A, B in moves:
        zmin = min(zmin, B[2])
        for P_ in (A, B):
            if not (r - 1e-6 <= P_[0] <= N.SHEET[0] - r + 1e-6 and r - 1e-6 <= P_[1] <= N.SHEET[1] - r + 1e-6) and P_[2] < 1:
                issues.append(f"fuera de la plancha {P_}")
        if g == "0":
            if (A[0], A[1]) != (B[0], B[1]) and min(A[2], B[2]) < 1.0: issues.append(f"G00 en XY bajo Z1: {A}->{B}")
            if B[2] < A[2] and B[2] < 1.0: issues.append(f"G00 bajando a la madera: {A}->{B}")
            continue
        z = min(A[2], B[2])
        if z >= 0: continue
        n += 1
        seg = LineString([A[:2], B[:2]]) if (A[0], A[1]) != (B[0], B[1]) else Point(A[:2])
        for L, G in keep.items():
            if L <= z + 1e-6: continue
            if preps[L].intersects(seg.buffer(r - TOL, 8)):
                pen = r - G.distance(seg); worst = max(worst, pen)
                issues.append(f"corte de mas {pen:.3f} mm en {A}->{B} (nivel {L})")
    if zmin < -max(D.values()) - 1e-6 or zmin < -12: issues.append(f"Z minima {zmin}")
    print(f"{os.path.basename(path)}: {len(moves)} movimientos, {n} cortando, Z minima {zmin:g}, problemas {len(issues)}")
    for i in issues[:6]: print("    ", i)
    return moves, not issues


def simulate(all_moves, res=0.5):
    x0, y0, x1, y1 = piece.bounds  # logo + margen
    xs = np.arange(x0 + res / 2, x1, res); ys = np.arange(y0 + res / 2, y1, res)
    Z = np.zeros((len(ys), len(xs)), np.float32)
    for moves, tool, r in all_moves:
        k = int(math.ceil(r / res))
        dx = np.arange(-k, k + 1) * res
        rho = np.hypot(dx[None, :], dx[:, None])
        inside = rho <= r
        prof = np.where(inside, 0.0 if tool == "recta" else r - np.sqrt(np.maximum(0, r * r - rho * rho)), np.inf).astype(np.float32)
        for g, A, B in moves:
            if g != "1" or min(A[2], B[2]) >= 0: continue
            L = math.dist(A[:2], B[:2]); n = max(1, int(L / (res * 0.8)))
            for t in np.linspace(0, 1, n + 1):
                cx, cy, cz = (A[i] + (B[i] - A[i]) * t for i in range(3))
                i0 = int(round((cx - xs[0]) / res)); j0 = int(round((cy - ys[0]) / res))
                a0, a1 = max(0, i0 - k), min(len(xs), i0 + k + 1); b0, b1 = max(0, j0 - k), min(len(ys), j0 + k + 1)
                if a0 >= a1 or b0 >= b1: continue
                sub = prof[b0 - (j0 - k):b1 - (j0 - k), a0 - (i0 - k):a1 - (i0 - k)] + cz
                np.minimum(Z[b0:b1, a0:a1], sub, out=Z[b0:b1, a0:a1])
    return xs, ys, Z


if __name__ == "__main__":
    nd = os.path.join(Lg.HERE, "nc_nk300")
    d = a.fresa
    m1, ok1 = check(os.path.join(nd, f"logo_1_desbaste_plana{d:g}.nc"))
    m2, ok2 = check(os.path.join(nd, f"logo_2_acabado_plana{d:g}.nc"))
    print("TODO OK" if ok1 and ok2 else "HAY PROBLEMAS")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    import shapely
    xs, ys, Zs = simulate([(m1, "recta", r), (m2, "recta", r)])
    X, Y = np.meshgrid(xs, ys)
    T = np.zeros_like(Zs)
    for n_, dd in (("verde", D["verde"]), ("letras", D["letras"]), ("barra", D["barra"]), ("cielo", D["cielo"])):
        T[shapely.contains_xy(R[n_], X, Y)] = -dd
    ls = LightSource(azdeg=315, altdeg=40)
    fig, ax = plt.subplots(1, 3, figsize=(19, 8.5), dpi=100)
    ext = (xs[0], xs[-1], ys[0], ys[-1])
    ax[0].imshow(ls.hillshade(T, vert_exag=5, dx=0.5, dy=0.5), cmap="gray", origin="lower", extent=ext); ax[0].set_title("Diseno (profundidades)")
    ax[1].imshow(ls.hillshade(Zs, vert_exag=5, dx=0.5, dy=0.5), cmap="gray", origin="lower", extent=ext); ax[1].set_title(f"Simulacion: fresa plana D{d:g} (desbaste + acabado)")
    diff = Zs - T
    im = ax[2].imshow(np.clip(diff, -0.5, 3), cmap="RdYlGn_r", origin="lower", extent=ext, vmin=-0.5, vmax=3)
    ax[2].set_title("Material que queda de mas (mm)")
    plt.colorbar(im, ax=ax[2], fraction=0.046)
    for x in ax: x.set_aspect("equal"); x.set_xlabel("X (mm)"); x.set_ylabel("Y (mm)")
    plt.tight_layout(); os.makedirs(os.path.join(Lg.HERE, "img"), exist_ok=True)
    fig.savefig(os.path.join(Lg.HERE, "img", "simulacion_nk300.png"), facecolor="white")
    print("sobrante: p50 %.2f  p95 %.2f  max %.2f mm" % (np.percentile(diff, 50), np.percentile(diff, 95), diff.max()))
