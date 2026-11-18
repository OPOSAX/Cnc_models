"""Logo San Felipe Diacono para Weihong NK300, fresa PLANA (sin trayectorias de bola).

Trabajo: grabado/relieve en MDF de 12 mm (plancha 1200 x 1200), logo de 600 mm de ancho con su esquina
inferior izquierda a 20 mm de la esquina de la plancha. Cero de trabajo: X0 Y0 = esquina inferior
izquierda de la plancha, Z0 = cara superior del MDF (G54). Sin recorte de la pieza.

Cajeras (fondo plano): verde 3 mm, cielo (verde oscuro) 5 mm, letras 4 mm, barra 2 mm.
Programas (misma fresa, sin cambio de herramienta):
  1  desbaste: vacia por niveles dejando SOBREMEDIDA en las paredes; entradas en rampa.
  2  acabado:  contorno de cada pared a la medida exacta (radio de la fresa) a fondo, en concordancia.
Uso: python3 logo_nk300.py --fresa 6
"""
import argparse, math, os
import numpy as np
from shapely.geometry import LineString, Polygon, box
import logo as Lg

# ------------------------------------------------------------------ trabajo
SHEET = (1200.0, 1200.0)
LOGO_W = 600.0
CORNER = 20.0          # margen desde la esquina de la plancha
DEPTH = {"verde": 3.0, "cielo": 5.0, "letras": 4.0, "barra": 2.0}
ALLOW_WALL = 0.3       # sobremedida en paredes que deja el desbaste

# ------------------------------------------------------------------ parametros de corte (MDF, fresa plana 2 filos)
def cut_params(d):
    rpm = 18000
    fz = 0.06 if d >= 6 else 0.04                       # mm por diente en MDF
    feed = int(round(rpm * 2 * fz / 100.0) * 100)       # 2 filos
    feed = min(feed, 3000)
    return dict(
        rpm=rpm, flutes=2, fz=fz,
        feed=feed,                                     # avance XY
        plunge=int(round(feed * 0.3 / 50) * 50),        # avance Z (rampas y bajadas)
        step=round(min(0.35 * d, 2.0), 2),              # profundidad por pasada (desbaste)
        over=round(0.45 * d, 2),                        # paso lateral desbaste
        finish_feed=int(round(feed * 0.8 / 100) * 100), # acabado de paredes
        safe_z=25.0, travel_z=5.0, ramp=0.10,           # rampa 1:10 (unos 5.7 grados)
        d=d,
    )


class NK300:
    """G-code para Weihong NK300 (ver README_NK300.md: instrucciones usadas y por que)."""
    def __init__(self, P, title):
        self.P = P; self.lines = []; self.st = {}
        self.x = self.y = self.z = None
        self.t_cut = 0.0; self.d_rapid = 0.0
        for l in HEADER(P, title): self.lines.append(l)
        self.z = P["safe_z"]; self.st.update(Z="%.3f" % P["safe_z"])   # G sin fijar: el primer movimiento lleva G00

    def emit(self, s): self.lines.append(s)

    def _mv(self, g, x=None, y=None, z=None, f=None):
        w = []
        for k, v in (("X", x), ("Y", y), ("Z", z)):
            if v is None: continue
            fv = f"{v:.3f}"
            if self.st.get(k) != fv: w.append(k + fv); self.st[k] = fv
        if not w: return
        out = []
        if self.st.get("G") != g: out.append(g); self.st["G"] = g
        out += w
        if g == "G01" and f and self.st.get("F") != str(int(f)): out.append(f"F{int(f)}.0"); self.st["F"] = str(int(f))
        nx = self.x if x is None else x; ny = self.y if y is None else y; nz = self.z if z is None else z
        if self.x is not None and self.z is not None:
            d = math.dist((self.x, self.y, self.z), (nx, ny, nz))
            if g == "G01": self.t_cut += d / f
            else: self.d_rapid += d
        self.x, self.y, self.z = nx, ny, nz
        self.emit(" ".join(out))

    # interfaz que usan pocket()/ramp_ring() de logo.py
    @property
    def T(self): return {"plunge": self.P["plunge"], "feed": self.cur_feed}
    cur_feed = 0

    def travel(self, x, y, z_above):
        if self.x is None:                               # ya esta a la Z de seguridad (cabecera)
            self._mv("G00", x=x, y=y); return
        if abs(self.x - x) < 1e-6 and abs(self.y - y) < 1e-6: return
        self._mv("G00", z=max(self.P["travel_z"], self.z))
        self._mv("G00", x=x, y=y)

    def feed(self, x, y, z=None):
        f = self.P["plunge"] if (z is not None and self.z is not None and z < self.z - 1e-6) else self.cur_feed
        self._mv("G01", x, y, z, f)

    def plunge(self, z): self._mv("G01", z=z, f=self.P["plunge"])

    def end(self):
        for l in FOOTER(self.P): self.emit(l)
        txt = "\r\n".join(self.lines) + "\r\n"
        assert txt.isascii(), "solo ASCII"
        return txt

    def minutes(self): return self.t_cut + self.d_rapid / 10000.0


# cabecera y final segun lo investigado del NK300 (README_NK300.md): ASCII, comentarios en linea propia,
# sin %, sin N, sin G43/G49/H, sin T/M06, sin M71/M73, sin M07-M09, sin G28/G53, sin G04.
def HEADER(P, title):
    return [f"({title})",
            "(SIN CAMBIO DE HERRAMIENTA - FRESA PLANA D%s MM - 2 FILOS)" % f"{P['d']:g}",
            "(USAR PINZA ER DEL DIAMETRO DE LA CANA DE LA FRESA - 1/4 PULGADA = 6.35 MM)",
            "(CERO: X0 Y0 ESQUINA INFERIOR IZQUIERDA DE LA PLANCHA - Z0 CARA SUPERIOR DEL MDF - G54)",
            "(S Y F CALCULADOS PARA MDF - REVISAR ANTES DE CORRER)",
            "G90 G21 G17 G40 G80",
            "G54",
            "G00 Z%.3f" % P["safe_z"],
            "M03 S%d" % P["rpm"],
            "(PAUSA: COMPROBAR QUE EL HUSILLO GIRA A REGIMEN Y PULSAR MARCHA)",
            "M00"]


def FOOTER(P):
    return ["G00 Z%.3f" % P["safe_z"], "M05", "G00 X0.000 Y0.000", "M30"]


SIMPLIFY = 0.02        # tolerancia al simplificar trayectorias (mm)


def _rings(g, ccw):
    """Anillos de un (Multi)Polygon simplificados; exterior en el sentido pedido, islas al reves."""
    out = []
    for pg in getattr(g, "geoms", [g]):
        if pg.is_empty or not isinstance(pg, Polygon): continue
        pg = pg.simplify(SIMPLIFY)
        if pg.is_empty or not isinstance(pg, Polygon): continue
        e = list(pg.exterior.coords)
        if Polygon(e).exterior.is_ccw != ccw: e = e[::-1]
        out.append(e)
        for h in pg.interiors:
            hp = list(h.coords)
            if Polygon(hp).exterior.is_ccw == ccw: hp = hp[::-1]
            out.append(hp)
    return out


def pocket_nk(nc, area, z_top, z_bot, r, allow, P):
    """Desbaste por niveles con anillos concentricos de dentro hacia fuera.
    Entrada en rampa en el primer anillo de cada nivel; entre anillos se pasa a la misma Z solo si el
    enlace queda dentro de la zona por la que puede ir el centro de la fresa (si no, sube y baja)."""
    core = area.buffer(-(r + allow), join_style=1)
    levels = []; z = z_top
    while z > z_bot + 1e-6:
        z = max(z_bot, z - P["step"]); levels.append(z)
    for pg in sorted(getattr(core, "geoms", [core]), key=lambda q: (-q.centroid.y, q.centroid.x)):
        if pg.is_empty: continue
        safe = pg.buffer(1e-3)
        rings = []; cur = pg
        while not cur.is_empty:
            rings.append(cur); cur = cur.buffer(-P["over"], join_style=1)
        seq = [pts for g in reversed(rings) for pts in _rings(g, True)]   # de dentro hacia fuera, antihorario
        prev = z_top
        for zl in levels:
            first = True
            for pts in seq:
                pts = Lg.ring_from(pts, nc.x if nc.x is not None else pts[0][0], nc.y if nc.y is not None else pts[0][1])
                link_ok = (not first and nc.z is not None and abs(nc.z - zl) < 1e-6 and
                           LineString([(nc.x, nc.y), pts[0]]).within(safe))
                if link_ok:
                    nc.feed(pts[0][0], pts[0][1])
                    for q in pts[1:]: nc.feed(q[0], q[1])
                else:
                    # bajar en rampa desde lo ya cortado (prev) hasta zl siguiendo el anillo
                    Lg.ramp_ring(nc, pts, prev, zl)
                first = False
            nc.travel(nc.x, nc.y, P["travel_z"])
            prev = zl


def finish_walls(nc, area, z_top, z_bot, r, P):
    """Contorno de cada pared a medida (centro a r del borde), en concordancia (climb):
    para cajeras (material fuera del camino) el exterior en antihorario y las islas en horario.
    Desde z_top hasta z_bot en pasadas de como mucho 2*step (el material es solo la sobremedida)."""
    # + SIMPLIFY: al simplificar el camino puede acercarse a la pared hasta esa tolerancia
    g = area.buffer(-(r + SIMPLIFY), join_style=1)
    levels = []; z = z_top
    while z > z_bot + 1e-6:
        z = max(z_bot, z - 2 * P["step"]); levels.append(z)
    for pg in sorted(getattr(g, "geoms", [g]), key=lambda q: (-q.centroid.y, q.centroid.x)):
        if pg.is_empty: continue
        for pts in _rings(pg, True):
            pts = Lg.ring_from(pts, nc.x if nc.x is not None else pts[0][0], nc.y if nc.y is not None else pts[0][1])
            prev = z_top
            for zl in levels:
                Lg.ramp_ring(nc, pts, prev, zl); prev = zl
            nc.travel(nc.x, nc.y, P["travel_z"])


def build(d):
    P = cut_params(d); r = d / 2
    Lg.WIDTH, Lg.MARGIN = LOGO_W, CORNER
    Lg.TRAVEL_Z = P["travel_z"]; Lg.RAMP = P["ramp"]
    R, piece, s = Lg.regions()
    jobs = [("verde", 0.0, -DEPTH["verde"]), ("cielo", -DEPTH["verde"], -DEPTH["cielo"]),
            ("letras", 0.0, -DEPTH["letras"]), ("barra", 0.0, -DEPTH["barra"])]
    out = {}
    n1 = NK300(P, f"Logo San Felipe - DESBASTE - fresa plana D{d:g} - MDF 12 - Z0 cara superior, X0Y0 esquina inf. izq. plancha")
    n1.cur_feed = P["feed"]
    for n, zt, zb in jobs:
        pocket_nk(n1, R[n], zt, zb, r, ALLOW_WALL, P)
    out[f"logo_1_desbaste_plana{d:g}.nc"] = n1
    n2 = NK300(P, f"Logo San Felipe - ACABADO paredes - fresa plana D{d:g} - misma fresa, mismo cero")
    n2.cur_feed = P["finish_feed"]
    for n, zt, zb in jobs:
        finish_walls(n2, R[n], zt, zb, r, P)
    out[f"logo_2_acabado_plana{d:g}.nc"] = n2
    return out, R, piece, P


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--fresa", type=float, required=True); a = ap.parse_args()
    out, R, piece, P = build(a.fresa)
    os.makedirs(os.path.join(Lg.HERE, "nc_nk300"), exist_ok=True)
    for name, w in out.items():
        txt = w.end()
        open(os.path.join(Lg.HERE, "nc_nk300", name), "w", newline="").write(txt)
        print(f"{name}: {len(w.lines)} lineas, ~{w.minutes():.0f} min")
    print("pieza (logo+margen):", [round(v, 1) for v in piece.bounds], "parametros:", P)
