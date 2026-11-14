"""
Lampara "Samurai" - geometria parametrica de todas las piezas.

Sistema de coordenadas del montaje (mm):
  X = ancho (derecha +), Y = fondo (frente +), Z = altura (suelo = 0).

Cada pieza se define en 2D (su plano de corte) con:
  outline  : contorno exterior (shapely Polygon)          -> corte pasante exterior
  holes    : agujeros/ventanas interiores (Polygon)         -> corte pasante interior (con dogbones)
  circles  : taladros (x, y, diametro)                      -> helicoidal pasante
  pockets  : cajeras (Polygon, profundidad)                 -> vaciado
  engraves : lineas de marcado (LineString, profundidad)
y una colocacion 3D (origen, e1, e2, e3) para el render del montaje.
"""
import math
from dataclasses import dataclass, field
import numpy as np
from shapely.geometry import Polygon, LineString, box, Point
from shapely.ops import unary_union
from shapely import affinity

# ---------------------------------------------------------------- parametros
T = 15.0          # MDF estructura (mm)
TH = 3.0          # contrachapado flexible del sombrero (mm)
FIT = 0.5         # holgura total en ventanas que reciben otra pieza

# Base (hakama)
B_H = 355.0       # altura total base (incluye tapa)
B_WB = 330.0      # ancho exterior abajo
B_WT = 230.0      # ancho exterior arriba (z = B_H)
B_D = 220.0       # fondo
B_WALL = B_H - T  # altura de paredes (la tapa apoya encima)
SLIT_W = 8.0      # ranura entre "piernas"
SLIT_H = 240.0

# Columna central
C_W = 80.0
C_Z0 = B_H - 3 * T            # arranca 45 mm por debajo de la tapa (2 collares)

# Sombrero (cono)
HAT_R = 220.0
HAT_H = 110.0
HAT_ZAPEX = 760.0
HAT_RHOLE = 30.0              # cono truncado: agujero superior
HAT_OVERLAP = 20.0            # solape de pegado en el borde exterior
HUB_R = 70.0
BTN_R = 35.0
BOLT_D = 7.0                  # pasante para tornillo M6

# Torso / solapas
OBI_Z0 = B_H
OBI_LAYERS = 3
OBI_Z1 = OBI_Z0 + OBI_LAYERS * T     # 400
LAP_TOP = 670.0
YOKE_Z0 = 650.0
TAB_DEPTH = 7.5
POCKET_DEPTH = 8.0

# Solapa: plano vertical que pasa por AI con direccion D (vista en planta, lado derecho)
AI = np.array([48.0, 62.0])
_d = np.array([77.0, -37.0]); DIR = _d / np.linalg.norm(_d)
NRM = np.array([-DIR[1], DIR[0]])          # normal hacia el frente


def P(u, w=0.0, side=1):
    """Punto en planta de la cara frontal de la solapa trasera (lado side=+1/-1)."""
    p = AI + u * DIR + w * NRM
    return np.array([p[0] * side, p[1]])


def base_half_width(z):
    return B_WB / 2 - (B_WB - B_WT) / 2 * z / B_H


# ---------------------------------------------------------------- piezas
@dataclass
class Piece:
    pid: str
    name: str
    qty: int
    thick: float
    color: str                    # 'negro' / 'oro'
    outline: Polygon
    holes: list = field(default_factory=list)
    circles: list = field(default_factory=list)
    pockets: list = field(default_factory=list)
    engraves: list = field(default_factory=list)
    placements: list = field(default_factory=list)   # (origin, e1, e2, e3)
    note: str = ""


def _pl(o, e1, e2, e3):
    return tuple(np.array(v, float) for v in (o, e1, e2, e3))


def build():
    pcs = []

    # ---------------- P01 / P02 frente y trasera base
    hw_top = base_half_width(B_WALL)
    trap = Polygon([(-B_WB / 2, 0), (B_WB / 2, 0), (hw_top, B_WALL), (-hw_top, B_WALL)])
    front = trap.difference(box(-SLIT_W / 2, -1, SLIT_W / 2, SLIT_H))
    back = trap.difference(box(-12, -1, 12, 14))          # salida de cable
    yf = B_D / 2 - T
    pcs.append(Piece("P01", "Frente base (hakama)", 1, T, "negro", front,
                     placements=[_pl((0, yf, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0))],
                     note="Ranura central de 8 mm separa las dos 'piernas'"))
    pcs.append(Piece("P02", "Trasera base", 1, T, "negro", back,
                     placements=[_pl((0, -B_D / 2, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0))],
                     note="Muesca inferior 24x14 para el cable de red"))

    # ---------------- P03 laterales base (inclinados, van entre frente y trasera)
    dx = B_WB / 2 - hw_top
    Ls = math.hypot(dx, B_WALL)
    wi = B_D - 2 * T
    side = box(-wi / 2, 0, wi / 2, Ls)
    pls = []
    for s in (1, -1):
        e2 = np.array([-s * dx, 0, B_WALL]) / Ls
        e3 = np.array([-s * B_WALL, 0, -dx]) / Ls      # hacia dentro
        pls.append(_pl((s * B_WB / 2, 0, 0), (0, 1, 0), e2, e3))
    pcs.append(Piece("P03", "Lateral base", 2, T, "negro", side, placements=pls,
                     note=f"Inclinacion {math.degrees(math.atan(dx / B_WALL)):.1f} grados; sin bisel (holgura interior oculta)"))

    # ---------------- P04 tapa base
    tw, td = 2 * hw_top + 4, B_D + 4
    pcs.append(Piece("P04", "Tapa base", 1, T, "negro", box(-tw / 2, -td / 2, tw / 2, td / 2),
                     holes=[box(-(C_W + FIT) / 2, -(C_W + FIT) / 2, (C_W + FIT) / 2, (C_W + FIT) / 2)],
                     placements=[_pl((0, 0, B_WALL), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Ventana 80.5x80.5 para la columna"))

    # ---------------- P05 collares (bajo la tapa)
    sq = (C_W + FIT) / 2
    pcs.append(Piece("P05", "Collar columna", 2, T, "negro", box(-70, -70, 70, 70),
                     holes=[box(-sq, -sq, sq, sq)],
                     placements=[_pl((0, 0, B_WALL - T), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
                                 _pl((0, 0, B_WALL - 2 * T), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Se encolan bajo la tapa: guian y rigidizan la columna"))

    # ---------------- columna
    beta = math.atan(HAT_H / HAT_R)
    hub_top = HAT_ZAPEX - HAT_H / HAT_R * HUB_R - TH / math.cos(beta)
    cap_top = hub_top - T
    Lc = round(cap_top - T - C_Z0, 1)
    pcs.append(Piece("P06", "Columna frente/trasera", 2, T, "negro",
                     box(-C_W / 2, 0, C_W / 2, Lc),
                     placements=[_pl((0, C_W / 2 - T, C_Z0), (1, 0, 0), (0, 0, 1), (0, 1, 0)),
                                 _pl((0, -C_W / 2, C_Z0), (1, 0, 0), (0, 0, 1), (0, 1, 0))]))
    ci = C_W / 2 - T
    pcs.append(Piece("P07", "Columna lateral", 2, T, "negro", box(-ci, 0, ci, Lc),
                     circles=[(0, Lc - 15, 10.0)],
                     placements=[_pl((C_W / 2 - T, 0, C_Z0), (0, 1, 0), (0, 0, 1), (1, 0, 0)),
                                 _pl((-C_W / 2, 0, C_Z0), (0, 1, 0), (0, 0, 1), (1, 0, 0))],
                     note="Taladro 10 mm (solo en una) para cable de la tira LED"))
    pcs.append(Piece("P08", "Tapa columna", 1, T, "negro", box(-C_W / 2, -C_W / 2, C_W / 2, C_W / 2),
                     circles=[(0, 0, BOLT_D)],
                     placements=[_pl((0, 0, C_Z0 + Lc), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Inserto roscado M6 por debajo"))

    # ---------------- P09 sombrero: desarrollo del cono
    s_out = math.hypot(HAT_R, HAT_H)
    s_in = HAT_RHOLE / HAT_R * s_out
    theta = 2 * math.pi * HAT_R / s_out
    dth = HAT_OVERLAP / s_out
    a = np.linspace(0, theta + dth, 400)
    pts = [(s_out * math.cos(t), s_out * math.sin(t)) for t in a] + \
          [(s_in * math.cos(t), s_in * math.sin(t)) for t in a[::-1]]
    sector = Polygon(pts)
    mark = LineString([(s_in * math.cos(theta), s_in * math.sin(theta)),
                       (s_out * math.cos(theta), s_out * math.sin(theta))])
    pcs.append(Piece("P09", "Sombrero (desarrollo cono)", 1, TH, "negro", sector,
                     engraves=[(mark, 0.5)],
                     note=f"Contrachapado flexible 3 mm. Sector {math.degrees(theta):.1f} grados + solape {HAT_OVERLAP:.0f} mm (linea marcada)"))
    pcs.append(Piece("P10", "Boton sombrero", 1, T, "negro", Point(0, 0).buffer(BTN_R, 64),
                     circles=[(0, 0, BOLT_D)],
                     placements=[_pl((0, 0, HAT_ZAPEX - HAT_H / HAT_R * BTN_R), (1, 0, 0), (0, 1, 0), (0, 0, 1))]))
    pcs.append(Piece("P11", "Buje sombrero", 1, T, "negro", Point(0, 0).buffer(HUB_R, 96),
                     circles=[(0, 0, BOLT_D)],
                     placements=[_pl((0, 0, hub_top - T), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Se encola bajo el cono; atornillado M6 a la columna (desmontable)"))

    # ---------------- solapas (en coordenadas u,z del plano de la solapa)
    lapA = Polygon([(-30, OBI_Z1), (0, OBI_Z1), (0, OBI_Z1 - TAB_DEPTH), (45, OBI_Z1 - TAB_DEPTH),
                    (45, OBI_Z1), (60, OBI_Z1), (85.4, 362), (85.4, 640), (72, LAP_TOP), (0, LAP_TOP)])
    lapB = Polygon([(-30, OBI_Z1), (12, OBI_Z1), (56, 575), (56, 648), (42, 682), (1, 682)])
    plA, plB = [], []
    for s in (1, -1):
        d3 = np.array([s * DIR[0], DIR[1], 0]); n3 = np.array([s * NRM[0], NRM[1], 0])
        o = P(0, 0, s)
        plA.append(_pl((o[0], o[1], 0), d3, (0, 0, 1), -n3))
        o = P(0, T, s)
        plB.append(_pl((o[0], o[1], 0), d3, (0, 0, 1), -n3))
    # dibujo en coordenadas locales con origen abajo
    pcs.append(Piece("P15", "Solapa trasera (kimono)", 2, T, "oro", lapA, placements=plA,
                     note="Cortar 2 iguales; la izquierda se voltea. Espiga inferior entra en la cajera del obi"))
    pcs.append(Piece("P16", "Solapa delantera (cuello)", 2, T, "oro", lapB, placements=plB,
                     note="Se encola sobre la cara frontal de P15 (la izquierda se voltea)"))

    # ---------------- obi (cinturon): 3 capas
    colsq = box(-(C_W + FIT) / 2, -(C_W + FIT) / 2, (C_W + FIT) / 2, (C_W + FIT) / 2)
    quads = []
    for s in (1, -1):
        quads.append(Polygon([P(-30, -T, s), P(60, -T, s), P(60, 30, s), P(-30, 30, s)]))
    obi = unary_union(quads + [box(-C_W / 2, C_W / 2, C_W / 2, C_W / 2 + 10)]).convex_hull.difference(colsq)
    obi_pk = []
    for s in (1, -1):
        obi_pk.append((Polygon([P(-3, -T - 0.25, s), P(48, -T - 0.25, s), P(48, 0.25, s), P(-3, 0.25, s)]),
                       POCKET_DEPTH))
    pcs.append(Piece("P12", "Obi capa superior (con cajeras)", 1, T, "oro", obi, pockets=obi_pk,
                     placements=[_pl((0, 0, OBI_Z0 + 2 * T), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Cajeras de 8 mm para las espigas de P15"))
    pcs.append(Piece("P13", "Obi capa", 2, T, "oro", obi,
                     placements=[_pl((0, 0, OBI_Z0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
                                 _pl((0, 0, OBI_Z0 + T), (1, 0, 0), (0, 1, 0), (0, 0, 1))]))

    # ---------------- P14 yugo (hombros)
    r78, r0 = P(78, -T, 1), P(0, -T, 1)
    yoke = Polygon([(-r78[0], r78[1]), (-r0[0], r0[1]), (r0[0], r0[1]), (r78[0], r78[1]),
                    (r78[0], -C_W / 2 - 15), (-r78[0], -C_W / 2 - 15)])
    pcs.append(Piece("P14", "Yugo hombros", 1, T, "negro", yoke, holes=[colsq],
                     placements=[_pl((0, 0, YOKE_Z0), (1, 0, 0), (0, 1, 0), (0, 0, 1))],
                     note="Sus cantos inclinados soportan la cara trasera de P15"))

    pcs.sort(key=lambda p: p.pid)
    info = dict(Lc=Lc, hub_top=hub_top, cap_top=cap_top, s_out=s_out, s_in=s_in,
                theta_deg=math.degrees(theta), side_len=Ls, side_deg=math.degrees(math.atan(dx / B_WALL)))
    return pcs, info


if __name__ == "__main__":
    pcs, info = build()
    for p in pcs:
        b = p.outline.bounds
        print(f"{p.pid} {p.name:34s} x{p.qty} {p.thick:4.1f}mm {p.color:5s} {b[2]-b[0]:7.1f} x {b[3]-b[1]:7.1f}")
    print(info)
