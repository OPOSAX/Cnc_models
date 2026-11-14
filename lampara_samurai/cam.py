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
SPINDLE = 18000       # rpm (el .tap de referencia de PowerMill traia S1500: revisar)
FEED = 1500           # mm/min XY  (referencia PowerMill: 1000)
PLUNGE = 500          # mm/min Z   (referencia PowerMill: 500)
SAFE_Z = 10.0         # altura de seguridad sobre el tablero
CLEAR_Z = 10.0
OVERCUT = 0.3         # pasar por debajo del tablero (martir)
STEPDOWN = {15.0: 5.0, 3.0: 1.8}
TAB_W = 8.0           # ancho del puente (material que queda)
TAB_H = {15.0: 3.0, 3.0: 1.2}
STEPOVER = 0.45 * TOOL_D


def f(v):
    """Formato PowerMill: 10. / -.5 / 1.376 / 0"""
    v = round(v, 3)
    if abs(v) < 5e-4:
        return "0"
    t = f"{v:.3f}".rstrip("0")
    if t.startswith("0."):
        t = t[1:]
    elif t.startswith("-0."):
        t = "-" + t[2:]
    return t


class NC:
    """Escribe G-code con el estilo del ejemplo del fabricante (rough-1.nc, Chaoda):
    numeros de linea N, palabras separadas por espacio, G54, codigo modal,
    sin comentarios ni arcos, F entero, final G53 Z0 / M05 / M30 / %."""

    def __init__(self):
        self.l = []
        self.n = 10
        self.z = None
        self.st = dict(G=None, X=None, Y=None, Z=None, F=None)
        self.first = True

    def __call__(self, s, numbered=True):
        if numbered:
            self.l.append(f"N{self.n} {s}"); self.n += 1
        else:
            self.l.append(s)

    def move(self, g, x=None, y=None, z=None, feed=None):
        words = []
        for k, v in (("X", x), ("Y", y), ("Z", z)):
            if v is None:
                continue
            fv = f(v)
            if self.st[k] != fv:
                words.append(k + fv); self.st[k] = fv
        if not words:
            return
        out = []
        gs = f"G{g}"
        if self.first:
            # primer movimiento como el ejemplo: G0 G54 X.. Y..
            self.first = False
            out += [gs, "G54"]; self.st["G"] = gs
        elif self.st["G"] != gs:
            out.append(gs); self.st["G"] = gs
        out += words
        if g == 1 and feed is not None:
            ff = str(int(round(feed)))
            if self.st["F"] != ff:
                out.append("F" + ff); self.st["F"] = ff
        self(" ".join(out))

    def rapid_xy(self, x, y):
        if self.first:                      # XY a la altura actual y luego bajar a Z seguridad
            self.move(0, x=x, y=y); self.move(0, z=SAFE_Z); self.z = SAFE_Z
            return
        if self.z is None or self.z < SAFE_Z - 1e-6:
            self.move(0, z=SAFE_Z); self.z = SAFE_Z
        self.move(0, x=x, y=y)

    def plunge(self, z):
        self.move(1, z=z, feed=PLUNGE); self.z = z

    def lin(self, x, y, z=None):
        if z is not None and abs(z - self.z) > 1e-6:
            self.move(1, x, y, z, feed=PLUNGE); self.z = z
        else:
            self.move(1, x, y, feed=FEED)

    def retract(self):
        self.move(0, z=SAFE_Z); self.z = SAFE_Z


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
                    nc.plunge(zt)
                nc.lin(pb[0], pb[1])
            s0 += sl
        if abs(nc.z - z) > 1e-6:
            nc.plunge(z)
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
    """Helicoidal con segmentos rectos (sin G2/G3), 1 mm de bajada por vuelta."""
    rr = (d - TOOL_D) / 2
    nc.rapid_xy(x + rr, y); nc.plunge(0.5)
    if rr < 0.05:
        for z in levels(depth, 1.5):    # picoteo
            nc.plunge(z); nc.retract(); nc.plunge(z + 0.5)
        nc.retract(); return
    nseg = 24
    zc = 0.0
    for z in levels(depth, 1.0) + [None]:
        for k in range(1, nseg + 1):
            a = -2 * math.pi * k / nseg          # sentido horario
            zz = zc + (z - zc) * k / nseg if z is not None else zc
            nc.move(1, x + rr * math.cos(a), y + rr * math.sin(a), zz, feed=FEED // 2)
            nc.z = zz
        if z is not None:
            zc = z
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
    nc("G90")
    nc(f"S{SPINDLE} M3")
    nc.z = SAFE_Z
    if g["circles"]:
        for x, y, d in g["circles"]:
            drill(nc, x, y, d, depth, step)
    if g["engraves"]:
        for ln, d in g["engraves"]:
            c = list(ln.coords)
            nc.rapid_xy(*c[0]); nc.plunge(0.5); nc.plunge(-d)
            for q in c[1:]:
                nc.lin(*q)
            nc.retract()
    if g["pockets"]:
        for pk, d in g["pockets"]:
            pocket(nc, pk, d, 4.0)
    if g["holes"]:
        for h in g["holes"]:
            contour(nc, dogbone_path(h), depth, step, tabs=0)
    outer = g["outline"].buffer(R, resolution=16)
    pts = ring_pts(outer.exterior, ccw=False)            # horario = fresado en concordancia
    L = outer.exterior.length
    ntabs = int(min(6, max(3, round(L / 300))))
    contour(nc, pts, depth, step, tabs=ntabs, tab_h=TAB_H[T])
    nc.move(0, z=SAFE_Z)
    nc("G53 Z0")
    nc("G0 M05")
    nc("M30")
    nc("%", numbered=False)
    fn = f"{p.pid}_{p.name.split('(')[0].strip().lower().replace(' ', '_').replace('/', '-')}"
    with open(os.path.join(outdir_nc, fn + ".nc"), "w", newline="") as fh:
        fh.write("\r\n".join(nc.l) + "\r\n")          # CRLF como el .tap de PowerMill

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
