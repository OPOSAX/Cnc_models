"""Verificador independiente de los NC del logo.
1) Exacto (shapely): para cada movimiento en G1 comprueba que la fresa (recta plana o bola) no entra en
   material que debe quedar: a cada altura L por encima de la punta, el centro tiene que estar a una
   distancia >= rho(L) de la zona que debe quedar a >= L.  Tambien: G0 en XY siempre por encima del MDF,
   Z minima, formato.
2) Simulacion por rejilla (0.5 mm) para la imagen: diseno, resultado simulado y diferencia.
Uso: python3 verificar.py --bola 8
"""
import argparse, math, os, re
import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
from shapely.prepared import prep
import logo as Lg

ap = argparse.ArgumentParser(); ap.add_argument("--bola", type=float, required=True); a = ap.parse_args()
R, piece, s = Lg.regions()
D = Lg.DEPTH
pk = {"verde": R["verde"], "cielo": R["cielo"], "letras": R["letras"], "barra": R["barra"]}
# zona que debe quedar a altura >= L
keep = {
    0.0: piece.difference(unary_union([pk["verde"], pk["letras"], pk["barra"]])),
    -D["barra"]: piece.difference(unary_union([pk["verde"], pk["letras"]])),
    -D["verde"]: piece.difference(unary_union([pk["cielo"], pk["letras"]])),
    -D["letras"]: piece.difference(pk["cielo"]),
}
TOL = 0.02


def parse(path):
    txt = open(path, newline="").read()
    assert txt.endswith("M30\r\n%\r\n"), "final"
    lines = txt.split("\r\n")
    assert [l.split(" ", 1)[1] for l in lines[:4]] == ["G40 G17 G80 G49 G90", "M71", "M73", f"S{Lg.SPINDLE} M3"]
    assert lines[4].split(" ", 1)[1].startswith("G0 G54 X") and lines[5].endswith("G43 H1") and lines[6].endswith("G90")
    p = {"X": None, "Y": None, "Z": None}; g = None; moves = []; nprev = None
    for ln in lines:
        if not ln or ln == "%": continue
        n = int(re.match(r"N(\d+) ", ln).group(1)); assert nprev is None or n == nprev + 1; nprev = n
        if "G53" in ln: continue
        m = re.search(r"\bG([01])\b", ln)
        if m: g = m.group(1)
        new = dict(p)
        for k in "XYZ":
            m = re.search(k + r"(-?[\d.]+)", ln)
            if m: new[k] = float(m.group(1))
        if new != p and p["X"] is not None and p["Z"] is not None:
            moves.append((g, (p["X"], p["Y"], p["Z"]), (new["X"], new["Y"], new["Z"])))
        p = new
    return moves


def check(path, tool, r, through=False):
    moves = parse(path)
    preps = {L: prep(G.buffer(0)) for L, G in keep.items()}
    pp = prep(piece)
    worst = 0.0; bad = []; zmin = 0; n = 0
    for g, A, B in moves:
        zmin = min(zmin, B[2])
        if g == "0":
            if (A[0], A[1]) != (B[0], B[1]) and min(A[2], B[2]) < 0.5: bad.append(("G0 bajo", A, B))
            continue
        z = min(A[2], B[2])
        if z >= 0: continue
        seg = LineString([A[:2], B[:2]]) if (A[0], A[1]) != (B[0], B[1]) else Point(A[:2])
        n += 1
        if through:
            # recorte: la fresa no puede entrar en la pieza (salvo los puentes, que son material que queda)
            d = piece.distance(seg)
            if d < r - TOL: bad.append(("corte entra en la pieza", A, B, r - d))
            continue
        for L, G in keep.items():
            if L <= z + 1e-6: continue
            h = L - z                                      # altura sobre la punta
            rho = r if tool == "recta" or h >= r else math.sqrt(r * r - (r - h) ** 2)
            if rho <= TOL: continue
            if preps[L].intersects(seg.buffer(rho - TOL, 8)):
                d = keep[L].distance(seg)
                pen = rho - d
                worst = max(worst, pen); bad.append(("gouge", A, B, L, round(pen, 3)))
    print(f"{os.path.basename(path)}: {len(moves)} movimientos, {n} cortando, Z minima {zmin:g}, "
          f"problemas {len(bad)}" + (f", peor penetracion {worst:.3f} mm" if worst else ""))
    for b in bad[:5]: print("   ", b)
    return moves, not bad


def simulate(all_moves, res=0.5):
    x0, y0, x1, y1 = piece.bounds
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
    nd = os.path.join(Lg.HERE, "nc")
    rb = a.bola / 2
    m1, ok1 = check(os.path.join(nd, "1_desbaste_recta_12.7mm.nc"), "recta", Lg.R_STRAIGHT)
    m2, ok2 = check(os.path.join(nd, f"2_detalle_bola_{a.bola:g}mm.nc"), "bola", rb)
    m3, ok3 = check(os.path.join(nd, "3_corte_recta_12.7mm.nc"), "recta", Lg.R_STRAIGHT, through=True)
    print("TODO OK" if ok1 and ok2 and ok3 else "HAY PROBLEMAS")
    # imagen
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    xs, ys, Zs = simulate([(m1, "recta", Lg.R_STRAIGHT), (m2, "bola", rb)])
    import shapely
    X, Y = np.meshgrid(xs, ys)
    T = np.zeros_like(Zs)
    for n, d in (("verde", D["verde"]), ("letras", D["letras"]), ("barra", D["barra"]), ("cielo", D["cielo"])):
        T[shapely.contains_xy(pk[n], X, Y)] = -d
    ls = LightSource(azdeg=315, altdeg=40)
    fig, ax = plt.subplots(1, 3, figsize=(18, 8), dpi=100)
    ext = (xs[0], xs[-1], ys[0], ys[-1])
    ax[0].imshow(ls.hillshade(T, vert_exag=6, dx=0.5, dy=0.5), cmap="gray", origin="lower", extent=ext); ax[0].set_title("Diseño (profundidades)")
    ax[1].imshow(ls.hillshade(Zs, vert_exag=6, dx=0.5, dy=0.5), cmap="gray", origin="lower", extent=ext); ax[1].set_title(f"Simulación: recta 12.7 + bola {a.bola:g}")
    diff = Zs - T
    im = ax[2].imshow(np.clip(diff, -0.5, 2), cmap="RdYlGn_r", origin="lower", extent=ext, vmin=-0.5, vmax=2)
    ax[2].set_title("Material que queda de más (mm); azul/negativo = cortado de más")
    plt.colorbar(im, ax=ax[2], fraction=0.046)
    for x in ax: x.set_aspect("equal")
    plt.tight_layout(); os.makedirs(os.path.join(Lg.HERE, "img"), exist_ok=True)
    fig.savefig(os.path.join(Lg.HERE, "img", "simulacion.png"), facecolor="white")
    print("sobrante: p50 %.2f  p95 %.2f  max %.2f mm; cortado de mas (raster 0.5 mm) min %.3f" % (
        np.percentile(diff, 50), np.percentile(diff, 95), diff.max(), diff.min()))
