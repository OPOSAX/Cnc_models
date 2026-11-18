"""Logo San Felipe Diacono en MDF de 12 mm (corte plano, 3 ejes, router Chaoda).

De la imagen del logo salen cajeras de fondo plano por colores:
  verde (cielo y suelo del cuadro) ..... 2.5 mm
  verde oscuro (cielo), ademas ......... hasta 4.0 mm (se ve el horizonte)
  letras ............................... 3.0 mm
  barra naranja de abajo ............... 1.5 mm
  naranja (marco y figura) y blanco .... quedan en la cara del tablero (Z0)
y tres programas, uno por fresa (cambio manual entre ellos):
  1_desbaste  fresa recta 1/2" (12.7 mm): vacia las cajeras grandes dejando SOBREMEDIDA en las paredes
  2_detalle   fresa bola: paredes a medida y los rincones a donde la de 1/2" no llega
  3_corte     fresa recta 1/2": recorta la pieza (rectangulo con 15 mm de margen) con 4 puentes
Origen: X0 Y0 = esquina inferior izquierda de la pieza, Z0 = cara superior del MDF (G54).
Formato: el del post de PowerMill del fabricante (ver ../maquina) igual que ../prueba_maquina.
Uso: python3 logo.py  [--bola 6]
"""
import argparse, math, os
import numpy as np
import cv2
from PIL import Image
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ parametros
WIDTH = 300.0          # ancho del logo (mm)
MARGIN = 15.0          # margen de la pieza alrededor del logo
THICK = 12.0           # espesor del MDF
THROUGH = 0.3          # cuanto pasa el corte por debajo del MDF (en la mesa de sacrificio)
DEPTH = {"verde": 2.5, "cielo": 4.0, "letras": 3.0, "barra": 1.5}
R_STRAIGHT = 12.7 / 2  # fresa recta 1/2"
ALLOW = 0.25           # sobremedida que deja el desbaste en las paredes
SPINDLE = 18000
SAFE_Z, TRAVEL_Z = 10.0, 3.0
TOOLS = {   # avance, entrada, paso vertical, paso lateral (fraccion del diametro)
    "recta": dict(feed=2500, plunge=700, step=3.0, over=0.45),
    "bola": dict(feed=2000, plunge=500, step=1.5, over=0.35),
}
TABS = dict(n_side=1, width=10.0, height=2.0)   # puentes del recorte: uno por lado
MIN_FEATURE = 1.2      # mm: manchas y puntitos mas pequenos que esto se ignoran
RAMP = 0.12            # pendiente de entrada en rampa (dz/dxy)

# ------------------------------------------------------------------ imagen -> regiones
COL = {"blanco": (245, 245, 245), "naranja": (226, 160, 45), "verde_osc": (62, 108, 68), "verde_cla": (82, 148, 62)}


def classify(path, K=4):
    src = Image.open(path).convert("RGB")
    big = np.asarray(src.resize((src.width * K, src.height * K), Image.BICUBIC)).astype(np.float32)
    names = list(COL)
    cen = np.array([COL[n] for n in names], np.float32)
    lab = ((big[:, :, None, :] - cen[None, None]) ** 2).sum(-1).argmin(-1).astype(np.uint8)
    # filtro de moda 5x5 dos veces: bordes limpios
    for _ in range(2):
        cnt = np.stack([cv2.boxFilter((lab == k).astype(np.float32), -1, (5, 5), normalize=False) for k in range(len(names))])
        lab = cnt.argmax(0).astype(np.uint8)
    return lab, names


def mask_to_polys(mask, s, H, min_area):
    """Mascara (fila 0 arriba) -> MultiPolygon en mm (Y hacia arriba). s = mm por pixel."""
    m = (mask.astype(np.uint8)) * 255
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return MultiPolygon()
    hier = hier[0]
    to_mm = lambda c: [((p[0][0] + 0.5) * s, (H - p[0][1] - 0.5) * s) for p in c]
    polys = []
    for i, c in enumerate(cs):
        if hier[i][3] != -1 or len(c) < 3:
            continue
        holes = []
        j = hier[i][2]
        while j != -1:
            if len(cs[j]) >= 3:
                holes.append(to_mm(cs[j]))
            j = hier[j][0]
        pg = Polygon(to_mm(c), holes).buffer(0)
        if pg.area >= min_area:
            polys.append(pg)
    u = unary_union(polys).simplify(0.08)
    # agujeros diminutos (motas) fuera
    out = []
    for pg in getattr(u, "geoms", [u]):
        if pg.is_empty: continue
        pg = Polygon(pg.exterior, [h for h in pg.interiors if Polygon(h).area >= min_area])
        out.append(pg)
    return MultiPolygon(out) if out else MultiPolygon()


def regions():
    lab, names = classify(os.path.join(HERE, "logo_original.jpg"))
    H, W = lab.shape
    k = {n: i for i, n in enumerate(names)}
    ys, xs = np.where(lab != k["blanco"])
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    s = WIDTH / (x1 - x0 + 1)                              # mm por pixel
    green = (lab == k["verde_osc"]) | (lab == k["verde_cla"])
    orange = lab == k["naranja"]
    rows = np.arange(H)[:, None]
    # el cuadro termina donde acaba el marco naranja; debajo estan las letras y la barra
    orange_rows = orange.sum(1)
    sq_end = y0 + np.argmax(orange_rows[y0:] < 0.05 * orange_rows[y0:].max())   # primera fila sin marco
    in_sq = rows < sq_end
    rad = max(1, int(round(0.6 / s)))                       # limpieza morfologica ~0.6 mm
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rad + 1, 2 * rad + 1))
    clean = lambda m: cv2.morphologyEx(cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, ker), cv2.MORPH_CLOSE, ker)
    amin = MIN_FEATURE ** 2
    R = {}
    R["verde"] = mask_to_polys(clean(green & in_sq), s, H, amin)
    sky = (lab == k["verde_osc"]) & in_sq
    # el cielo es la mitad de arriba del cuadro (las motas claras dentro del cielo cuentan como cielo)
    sky_rows = sky.sum(1)
    hz = y0 + int(np.argmax((sky_rows[y0:sq_end] < 0.3 * sky_rows[y0:sq_end].max()) & (np.arange(y0, sq_end) > (y0 + sq_end) // 2 - 200)))
    R["cielo"] = mask_to_polys(clean(green & in_sq & (rows < hz)), s, H, amin)
    R["cielo"] = R["cielo"].intersection(R["verde"].buffer(-0.05))   # el escalon nunca sale de la cajera verde
    R["letras"] = mask_to_polys(clean(green & ~in_sq), s, H, amin)
    R["barra"] = mask_to_polys(clean(orange & ~in_sq), s, H, amin)
    # pieza: logo + margen; se traslada para que la pieza empiece en X0 Y0
    lx0, ly0 = x0 * s, (H - 1 - y1) * s
    dx, dy = MARGIN - lx0, MARGIN - ly0
    from shapely import affinity
    for n in R:
        R[n] = affinity.translate(R[n], dx, dy)
    piece = box(0, 0, (x1 - x0 + 1) * s + 2 * MARGIN, (y1 - y0 + 1) * s + 2 * MARGIN)
    return R, piece, s


# ------------------------------------------------------------------ G-code
def fnum(v):
    v = round(v, 3) + 0.0
    if v == 0: return "0"
    t = f"{v:.3f}".rstrip("0")
    if t.startswith("0."): t = t[1:]
    if t.startswith("-0."): t = "-" + t[2:]
    return t


class NC:
    def __init__(self, tool):
        self.T = TOOLS[tool]
        self.lines, self.n, self.st = [], 10, {}
        self.x = self.y = None; self.z = None
        self.cut_len = 0.0; self.rapid_len = 0.0
        self("G40 G17 G80 G49 G90"); self("M71"); self("M73"); self(f"S{SPINDLE} M3")

    def __call__(self, s):
        self.lines.append(f"N{self.n} {s}"); self.n += 1

    def _mv(self, g, x=None, y=None, z=None, f=None):
        w = []
        for k, v in (("X", x), ("Y", y), ("Z", z)):
            if v is None: continue
            fv = fnum(v)
            if self.st.get(k) != fv: w.append(k + fv); self.st[k] = fv
        if not w: return
        out = []
        if self.st.get("G") != g: out.append(g); self.st["G"] = g
        out += w
        if g == "G1" and f is not None and self.st.get("F") != str(int(f)):
            out.append("F" + str(int(f))); self.st["F"] = str(int(f))
        nx, ny, nz = (self.x if x is None else x), (self.y if y is None else y), (self.z if z is None else z)
        if self.x is not None and self.z is not None:
            d = math.dist((self.x, self.y, self.z), (nx, ny, nz))
            if g == "G1": self.cut_len += d / f
            else: self.rapid_len += d
        self.x, self.y, self.z = nx, ny, nz
        self(" ".join(out))

    def start(self, x, y):
        # como el post: G0 G54 X Y con la maquina arriba, G43 H1, G90 y luego la Z de seguridad
        self("G0 G54 X" + fnum(x) + " Y" + fnum(y)); self.st.update(G="G0", X=fnum(x), Y=fnum(y)); self.x, self.y = x, y
        self("G43 H1"); self("G90")
        self._mv("G0", z=SAFE_Z)

    def travel(self, x, y, z_above):
        """Ir a (x, y) por arriba. z_above: Z de traslado segura sobre el material."""
        if self.x is None:
            self.start(x, y); return
        if abs(self.x - x) < 1e-6 and abs(self.y - y) < 1e-6: return
        self._mv("G0", z=max(z_above, self.z))
        self._mv("G0", x=x, y=y)

    def feed(self, x, y, z=None):
        fz = z is not None and self.z is not None and z < self.z - 1e-6
        self._mv("G1", x, y, z, self.T["plunge"] if fz and math.hypot(x - self.x, y - self.y) < 1e-6 else self.T["feed"])

    def plunge(self, z):
        self._mv("G1", z=z, f=self.T["plunge"])

    def end(self):
        self._mv("G0", z=SAFE_Z)
        self("G53 Z0"); self("G0 M05"); self("M30")
        return "\r\n".join(self.lines + ["%"]) + "\r\n"

    def minutes(self):
        return self.cut_len + self.rapid_len / 8000.0


def rings_of(geom):
    out = []
    for pg in getattr(geom, "geoms", [geom]):
        if pg.is_empty or not isinstance(pg, Polygon): continue
        out.append(list(pg.exterior.coords))
        for h in pg.interiors: out.append(list(h.coords))
    return out


def ring_from(pts, x, y):
    """Rota un anillo cerrado para empezar en el vertice mas cercano a (x, y)."""
    p = pts[:-1]
    i = min(range(len(p)), key=lambda k: (p[k][0] - x) ** 2 + (p[k][1] - y) ** 2)
    q = p[i:] + p[:i]
    return q + [q[0]]


def ramp_ring(nc, pts, z_from, z_to):
    """Baja en rampa siguiendo el anillo y luego da una vuelta completa a z_to."""
    nc.travel(pts[0][0], pts[0][1], TRAVEL_Z)
    nc.plunge(min(z_from + 0.5, TRAVEL_Z)) if nc.z > z_from + 0.5 else None
    z = min(nc.z, z_from + 0.5)
    i = 0; n = len(pts) - 1
    per = LineString(pts).length
    if per < 1e-6:
        nc.plunge(z_to); return
    while z > z_to + 1e-6:
        a, b = pts[i % n], pts[i % n + 1]
        seg = math.dist(a, b)
        z = max(z_to, z - seg * RAMP)
        nc.feed(b[0], b[1], z); i += 1
        if i > 2000 * n: break
    k = i % n
    loop = pts[k:-1] + pts[:k] + [pts[k]]
    for q in loop[1:]: nc.feed(q[0], q[1])


def pocket(nc, area, z_top, z_bot, r, allow, over, step):
    """Vacia 'area' (poligonos, mm) desde z_top hasta z_bot con una fresa de radio r.
    Centro de la fresa dentro de area.buffer(-(r+allow)); anillos de afuera hacia adentro."""
    levels = []
    z = z_top
    while z > z_bot + 1e-6:
        z = max(z_bot, z - step); levels.append(z)
    core = area.buffer(-(r + allow), join_style=1)
    for pg in sorted(getattr(core, "geoms", [core]), key=lambda g: (-g.centroid.y, g.centroid.x)):
        if pg.is_empty: continue
        rings = []
        cur = pg
        while not cur.is_empty:
            rings.append(cur)
            cur = cur.buffer(-over, join_style=1)
        for zl in levels:
            # de adentro hacia afuera: el centro primero, para entrar en rampa en material ya libre
            for ring_geom in reversed(rings):
                for pts in rings_of(ring_geom):
                    pts = ring_from(pts, nc.x if nc.x is not None else pts[0][0], nc.y if nc.y is not None else pts[0][1])
                    ramp_ring(nc, pts, nc.z if nc.z is not None and nc.z < TRAVEL_Z and nc.z >= zl else (z_top if zl == levels[0] else levels[levels.index(zl) - 1]), zl)
            nc.travel(nc.x, nc.y, TRAVEL_Z)


def ball_reach(rb, d):
    """Radio horizontal de una fresa bola de radio rb a la altura de la superficie, con la punta a d."""
    return rb if d >= rb else math.sqrt(rb * rb - (rb - d) ** 2)


def detail(nc, area, z_top, z_bot, rb, r_big, allow, over, step):
    """Fresa bola, pasadas concentricas desde el borde hacia dentro (como un 'v-carve' con bola).
    Con el centro a una distancia delta del borde, la punta baja hasta r - sqrt(r^2 - delta^2) (medido desde
    Z0): asi la bola llega justo al borde en la cara del tablero y nunca entra en lo que debe quedar.
    Cerca del borde la pared sale redondeada (radio de la bola); los trazos estrechos (DIACONO) quedan
    como un canal por el centro; donde cabe, llega a z_bot. Lo que la recta ya vacio a fondo no se repite."""
    D = -z_bot
    full = ball_reach(rb, D)                     # a partir de esta distancia ya se llega a fondo
    big_cleared = area.buffer(-(r_big + allow), join_style=1).buffer(r_big + allow - 0.2, join_style=1)
    deltas = [d for d in np.arange(0.4, full, 0.4)] + [full]
    k = 1
    while True:
        dd = full + k * over
        if area.buffer(-dd, join_style=1).is_empty: break
        deltas.append(dd); k += 1
    passes = []                                  # (z, [lineas])
    for d in deltas:
        g = area.buffer(-d, join_style=1)
        if g.is_empty: break
        z = -(rb - math.sqrt(max(0.0, rb * rb - d * d))) if d < rb else -rb
        z = max(z, z_bot)
        if z >= z_top - 0.02: continue           # aun no llega por debajo de lo ya cortado
        lines = []
        for pts in rings_of(g):
            ln = LineString(pts)
            if d >= full - 1e-9:
                # a fondo: solo donde la recta no llego (rincones, zonas estrechas)
                ln = ln.difference(big_cleared.buffer(-rb * 0.5))
            for piece_ln in getattr(ln, "geoms", [ln]):
                if piece_ln.is_empty or piece_ln.length < 0.5: continue
                lines.append(list(piece_ln.coords))
        if lines: passes.append((z, lines))
    # niveles en Z: cada pasada se corta bajando de 'step' en 'step'
    for z, lines in passes:
        zs = []
        zz = z_top
        while zz > z + 1e-6:
            zz = max(z, zz - step); zs.append(zz)
        for zl in zs:
            for pts in lines:
                closed = math.dist(pts[0], pts[-1]) < 1e-6
                if closed:
                    pts = ring_from(pts, nc.x if nc.x is not None else pts[0][0], nc.y if nc.y is not None else pts[0][1])
                    ramp_ring(nc, pts, z_top, zl)
                else:
                    if nc.x is not None and math.dist((nc.x, nc.y), pts[-1]) < math.dist((nc.x, nc.y), pts[0]):
                        pts = pts[::-1]
                    nc.travel(pts[0][0], pts[0][1], TRAVEL_Z)
                    nc.plunge(zl)
                    for q in pts[1:]: nc.feed(q[0], q[1])
            nc.travel(nc.x, nc.y, TRAVEL_Z)


def cutout(nc, piece, r):
    """Recorte exterior en sentido horario (convencional con husillo a derechas) con puentes."""
    path = piece.buffer(r, join_style=2)
    pts = list(path.exterior.coords)
    if Polygon(pts).exterior.is_ccw: pts = pts[::-1]
    # puentes: centro de cada lado
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    tabs = [(cx, min(ys)), (cx, max(ys)), (min(xs), cy), (max(xs), cy)]
    zend = -(THICK + THROUGH)
    ztab = -THICK + TABS["height"]
    line = LineString(pts)
    L = line.length
    tab_iv = []
    for t in tabs:
        s = line.project(LineString([t, t]).centroid) if False else line.project(Polygon(pts).exterior.interpolate(Polygon(pts).exterior.project(__import__("shapely").geometry.Point(t))))
        half = TABS["width"] / 2 + r
        tab_iv.append((s - half, s + half))
    # puntos densos para poder levantar en los puentes
    dense = [line.interpolate(d) for d in np.arange(0, L, 2.0)] + [line.interpolate(L)]
    levels = []
    z = 0.0
    while z > zend + 1e-6:
        z = max(zend, z - TOOLS["recta"]["step"]); levels.append(z)
    nc.travel(pts[0][0], pts[0][1], TRAVEL_Z)
    prev = 0.0
    for zl in levels:
        # entrada en rampa sobre el primer tramo
        ramp_ring(nc, pts, prev, zl) if False else None
        nc.plunge(prev + 0.2) if nc.z > prev + 0.2 else None
        dpos = 0.0
        for i, P in enumerate(dense):
            dpos = line.project(P)
            in_tab = zl < ztab and any(a <= dpos <= b for a, b in tab_iv)
            zt = max(zl, ztab) if in_tab else zl
            # rampa: los primeros 40 mm de cada nivel bajan poco a poco
            zr = max(zt, prev - dpos * RAMP) if dpos < (prev - zl) / RAMP + 1e-6 else zt
            nc.feed(P.x, P.y, zr)
        prev = zl
    nc.travel(nc.x, nc.y, SAFE_Z)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bola", type=float, default=None, help="diametro de la fresa bola (mm)")
    a = ap.parse_args()
    R, piece, s = regions()
    os.makedirs(os.path.join(HERE, "nc"), exist_ok=True)
    rS = R_STRAIGHT
    jobs = [("verde", 0.0, -DEPTH["verde"]), ("cielo", -DEPTH["verde"], -DEPTH["cielo"]),
            ("letras", 0.0, -DEPTH["letras"]), ("barra", 0.0, -DEPTH["barra"])]
    info = {"mm_por_px": s, "pieza": piece.bounds}
    # 1 desbaste
    nc = NC("recta")
    for n, zt, zb in jobs:
        pocket(nc, R[n], zt, zb, rS, ALLOW, 2 * rS * TOOLS["recta"]["over"], TOOLS["recta"]["step"])
    out = {"1_desbaste_recta_12.7mm.nc": nc}
    if a.bola:
        rb = a.bola / 2
        nb = NC("bola")
        for n, zt, zb in jobs:
            detail(nb, R[n], zt, zb, rb, rS, ALLOW, 2 * rb * TOOLS["bola"]["over"], TOOLS["bola"]["step"])
        out[f"2_detalle_bola_{a.bola:g}mm.nc"] = nb
    nc3 = NC("recta")
    cutout(nc3, piece, rS)
    out["3_corte_recta_12.7mm.nc"] = nc3
    for name, w in out.items():
        txt = w.end()
        with open(os.path.join(HERE, "nc", name), "w", newline="") as fh: fh.write(txt)
        print(f"{name}: {len(w.lines)} lineas, ~{w.minutes():.0f} min")
    x0, y0, x1, y1 = piece.bounds
    print(f"pieza {x1 - x0:.1f} x {y1 - y0:.1f} mm, {s:.4f} mm/px")
    return R, piece


if __name__ == "__main__":
    main()
