"""
Genera un programa NC (G-code GRBL/Mach3/LinuxCNC compatible) y un DXF por pieza.

Origen de cada programa:
  X0 Y0 = esquina inferior izquierda del rectangulo que envuelve la pieza
  Z0    = cara superior del tablero
Orden de operaciones: taladros -> cajeras -> cortes interiores -> contorno exterior (con puentes).
"""
import math
import os
import numpy as np
import ezdxf
from shapely.geometry import Polygon, LineString
from shapely.geometry.polygon import orient
from shapely import affinity
import geometria as G

# ------------------------------------------------------------- parametros maquina
TOOL_D = 6.0          # fresa plana 6 mm (2 cortes, compresion o upcut)
R = TOOL_D / 2
SPINDLE = 18000
FEED = 2000           # mm/min XY
PLUNGE = 400          # mm/min Z
SAFE_Z = 5.0
CLEAR_Z = 15.0
OVERCUT = 0.3         # pasar por debajo del tablero (martir)
STEPDOWN = {15.0: 5.0, 3.0: 1.8}
TAB_W = 8.0           # ancho del puente (material que queda)
TAB_H = {15.0: 3.0, 3.0: 1.2}
STEPOVER = 0.45 * TOOL_D


def f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


class NC:
    def __init__(self):
        self.l = []
        self.z = None

    def __call__(self, s):
        self.l.append(s)

    def rapid_xy(self, x, y):
        if self.z is None or self.z < SAFE_Z:
            self(f"G0 Z{f(SAFE_Z)}"); self.z = SAFE_Z
        self(f"G0 X{f(x)} Y{f(y)}")

    def plunge(self, z):
        self(f"G1 Z{f(z)} F{PLUNGE}"); self.z = z

    def lin(self, x, y, z=None):
        if z is not None and abs(z - self.z) > 1e-6:
            self(f"G1 X{f(x)} Y{f(y)} Z{f(z)} F{PLUNGE}"); self.z = z
        else:
            self(f"G1 X{f(x)} Y{f(y)} F{FEED}")

    def retract(self):
        self(f"G0 Z{f(SAFE_Z)}"); self.z = SAFE_Z


def levels(depth, step):
    n = max(1, math.ceil(depth / step - 1e-9))
    return [-depth * (i + 1) / n for i in range(n)]


def ring_pts(ring, ccw):
    r = orient(Polygon(ring), 1.0 if ccw else -1.0).exterior
    return [tuple(p) for p in r.coords]


def dogbone_path(hole):
    """Trayectoria interior con dogbones en las esquinas convexas del agujero."""
    inset = hole.buffer(-R, join_style=2)
    pts = ring_pts(inset.exterior, ccw=True)[:-1]
    hv = np.array(hole.exterior.coords)[:-1]
    out = []
    for p in pts:
        out.append(p)
        d = np.linalg.norm(hv - np.array(p), axis=1)
        k = int(np.argmin(d))
        if d[k] < R * 1.6:              # esquina en angulo: ir hasta tocarla
            h = hv[k]; v = np.array(p) - h; v /= np.linalg.norm(v)
            q = h + v * R
            out += [tuple(q), p]
    out.append(out[0])
    return out


def contour(nc, pts, depth, step, tabs=0, tab_h=0.0):
    """Recorre un contorno cerrado a varias profundidades; puentes en la ultima pasada."""
    zs = levels(depth, step)
    pts = [np.array(p, float) for p in pts]
    seg_len = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]
    L = sum(seg_len)
    tab_iv = []
    if tabs:
        span = TAB_W + TOOL_D
        for i in range(tabs):
            c = L * (i + 0.5) / tabs
            tab_iv.append((c - span / 2, c + span / 2))
    tab_z = -depth + tab_h
    nc.rapid_xy(*pts[0]); nc.plunge(0.5)
    for zi, z in enumerate(zs):
        last = zi == len(zs) - 1
        nc.plunge(z)
        if not (last and tab_iv and z < tab_z):
            for p in pts[1:]:
                nc.lin(p[0], p[1])
            continue
        # ultima pasada con puentes: trocear segmentos en los limites de los puentes
        s0 = 0.0
        for i in range(len(pts) - 1):
            a, b, sl = pts[i], pts[i + 1], seg_len[i]
            cuts = [0.0, sl]
            for (t0, t1) in tab_iv:
                for t in (t0, t1):
                    if s0 < t < s0 + sl:
                        cuts.append(t - s0)
            cuts = sorted(set(cuts))
            for c0, c1 in zip(cuts[:-1], cuts[1:]):
                mid = s0 + (c0 + c1) / 2
                inside = any(t0 <= mid <= t1 for t0, t1 in tab_iv)
                zt = tab_z if inside else z
                pa = a + (b - a) * (c0 / sl) if sl else a
                pb = a + (b - a) * (c1 / sl) if sl else b
                if abs(zt - nc.z) > 1e-6:
                    nc(f"G1 Z{f(zt)} F{PLUNGE}"); nc.z = zt
                nc.lin(pb[0], pb[1])
            s0 += sl
        if abs(nc.z - z) > 1e-6:
            nc(f"G1 Z{f(z)} F{PLUNGE}"); nc.z = z
    nc.retract()


def pocket(nc, poly, depth, step):
    rings = []
    first = dogbone_path(poly)
    rings.append(first)
    k = 1
    while True:
        g = poly.buffer(-R - k * STEPOVER, join_style=2)
        if g.is_empty:
            break
        for gp in getattr(g, "geoms", [g]):
            rings.append(ring_pts(gp.exterior, ccw=True))
        k += 1
    rings = rings[::-1]                 # de dentro hacia fuera
    for z in levels(depth, step):
        for r in rings:
            nc.rapid_xy(*r[0]); nc.plunge(0.5); nc.plunge(z)
            for p in r[1:]:
                nc.lin(*p)
            nc.retract()


def drill(nc, x, y, d, depth, step):
    rr = (d - TOOL_D) / 2
    nc.rapid_xy(x + rr, y); nc.plunge(0.5)
    if rr < 0.05:
        for z in levels(depth, 1.5):    # picoteo
            nc.plunge(z); nc.retract(); nc.plunge(z + 0.5)
        nc.retract(); return
    for z in levels(depth, 1.0):        # helicoidal, 1 mm por vuelta
        nc(f"G2 X{f(x + rr)} Y{f(y)} Z{f(z)} I{f(-rr)} J0 F{FEED // 2}"); nc.z = z
    nc(f"G2 X{f(x + rr)} Y{f(y)} I{f(-rr)} J0 F{FEED // 2}")
    nc.retract()


def normalize(p):
    """Traslada la pieza para que su bbox empiece en (0,0)."""
    bx, by = p.outline.bounds[:2]
    t = lambda g: affinity.translate(g, -bx, -by)
    return dict(outline=t(p.outline), holes=[t(h) for h in p.holes],
                pockets=[(t(k), d) for k, d in p.pockets],
                circles=[(x - bx, y - by, d) for x, y, d in p.circles],
                engraves=[(t(l), d) for l, d in p.engraves])


def gen_piece(p, outdir_nc, outdir_dxf):
    g = normalize(p)
    T = p.thick
    step = STEPDOWN[T]
    depth = T + OVERCUT
    b = g["outline"].bounds
    nc = NC()
    nc(f"( Lampara Samurai - {p.pid} {p.name} )")
    nc(f"( Cantidad: {p.qty}  |  Material: {'MDF' if T == 15 else 'contrachapado flexible'} {T:g} mm  |  Acabado: {p.color} )")
    nc(f"( Tamano pieza: {b[2]:.1f} x {b[3]:.1f} mm  -> tablero minimo {b[2] + 20:.0f} x {b[3] + 20:.0f} mm )")
    nc(f"( Origen: X0 Y0 = esquina inf. izq. de la pieza (dejar 10 mm de margen), Z0 = cara superior del tablero )")
    nc(f"( Herramienta: fresa plana D{TOOL_D:g} mm  S{SPINDLE}  F{FEED}  pasada {step:g} mm  sobrecorte {OVERCUT:g} mm )")
    if p.note:
        nc(f"( Nota: {p.note} )")
    nc("G21 G90 G17 G94")
    nc(f"G0 Z{f(CLEAR_Z)}")
    nc(f"M3 S{SPINDLE}")
    nc("G4 P3")
    nc.z = CLEAR_Z
    if g["circles"]:
        nc("( --- Taladros --- )")
        for x, y, d in g["circles"]:
            drill(nc, x, y, d, depth, step)
    if g["engraves"]:
        nc("( --- Marcado --- )")
        for ln, d in g["engraves"]:
            c = list(ln.coords)
            nc.rapid_xy(*c[0]); nc.plunge(0.5); nc.plunge(-d)
            for q in c[1:]:
                nc.lin(*q)
            nc.retract()
    if g["pockets"]:
        nc("( --- Cajeras --- )")
        for pk, d in g["pockets"]:
            pocket(nc, pk, d, 4.0)
    if g["holes"]:
        nc("( --- Cortes interiores --- )")
        for h in g["holes"]:
            contour(nc, dogbone_path(h), depth, step, tabs=0)
    nc("( --- Contorno exterior con puentes --- )")
    outer = g["outline"].buffer(R, resolution=16)
    pts = ring_pts(outer.exterior, ccw=False)            # horario = fresado en concordancia
    L = outer.exterior.length
    ntabs = int(min(6, max(3, round(L / 300))))
    contour(nc, pts, depth, step, tabs=ntabs, tab_h=TAB_H[T])
    nc(f"G0 Z{f(CLEAR_Z)}")
    nc("M5")
    nc("G0 X0 Y0")
    nc("M30")
    fn = f"{p.pid}_{p.name.split('(')[0].strip().lower().replace(' ', '_').replace('/', '-')}"
    with open(os.path.join(outdir_nc, fn + ".nc"), "w") as fh:
        fh.write("\n".join(nc.l) + "\n")

    # DXF
    doc = ezdxf.new("R2010", setup=True); msp = doc.modelspace()
    for name, col in (("CORTE_EXT", 1), ("CORTE_INT", 3), ("CAJERA", 5), ("TALADRO", 4), ("MARCADO", 6)):
        doc.layers.add(name, color=col)
    msp.add_lwpolyline(list(g["outline"].exterior.coords), close=True, dxfattribs={"layer": "CORTE_EXT"})
    for h in g["holes"]:
        msp.add_lwpolyline(list(h.exterior.coords), close=True, dxfattribs={"layer": "CORTE_INT"})
    for pk, d in g["pockets"]:
        msp.add_lwpolyline(list(pk.exterior.coords), close=True, dxfattribs={"layer": f"CAJERA"})
    for x, y, d in g["circles"]:
        msp.add_circle((x, y), d / 2, dxfattribs={"layer": "TALADRO"})
    for ln, d in g["engraves"]:
        msp.add_lwpolyline(list(ln.coords), dxfattribs={"layer": "MARCADO"})
    doc.saveas(os.path.join(outdir_dxf, fn + ".dxf"))
    return fn, nc.l


if __name__ == "__main__":
    pcs, info = G.build()
    for p in pcs:
        fn, lines = gen_piece(p, "nc", "dxf")
        print(f"{fn}.nc  ({len(lines)} lineas)")
