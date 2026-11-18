"""Programa de prueba para la router Chaoda (corte plano, 3 ejes).

Genera dos NC con el mismo dibujo de 120 x 100 mm:
  nc/prueba_1_aire.nc     -> todo 25 mm por encima del tablero: la fresa nunca toca nada.
  nc/prueba_2_grabado.nc  -> grabado de 0.5 mm de profundidad en un retazo.
Dibujo: marco, circulo, estrella, flechas +X / +Y con sus letras y una marca en el origen,
para comprobar recorridos, sentido de los ejes, escala (medir el marco: 100 x 80 mm) y que
los circulos salen redondos.

Origen: X0 Y0 = esquina inferior izquierda del dibujo, Z0 = cara superior del tablero (G54).
Formato: el del post de PowerMill del fabricante (maquina/POST-4axis-table-B.opt) y su ejemplo
rough-1.nc: N, G40 G17 G80 G49 G90, M71, M73, S.. M3, G0 G54 X.. Y.., G43 H1, G90, codigo modal,
sin comentarios ni arcos, final G53 Z0 / M05 / M30 / %.  Uso: python3 prueba.py
G43 H1 activa la compensacion de largo de la herramienta 1: el valor H1 de la maquina tiene que
corresponder a como se fijo Z0 (ver README).
"""
import math, os

SPINDLE = 18000     # rpm (el ejemplo del fabricante trae S1500: cambialo si tu maquina usa otro valor)
FEED = 1000         # mm/min en XY
PLUNGE = 300        # mm/min bajando en Z
SAFE_Z = 10.0       # altura de seguridad sobre el tablero
DEPTH = 0.5         # profundidad del grabado
AIR = 25.0          # en la version en el aire todo sube esto


def fnum(v):
    """Numero como en rough-1.nc: 284. / -.865 / 0"""
    v = round(v, 3) + 0.0
    if v == 0:
        return "0"
    s = f"{v:.3f}".rstrip("0")
    if s.startswith("0."): s = s[1:]
    if s.startswith("-0."): s = "-" + s[2:]
    return s


class Writer:
    def __init__(self):
        self.lines, self.n = [], 10
        self.st = {}
        self.first = True
        self.z = None

    def __call__(self, s):
        self.lines.append(f"N{self.n} {s}"); self.n += 1

    def move(self, g, x=None, y=None, z=None, feed=None):
        words = []
        for k, v in (("X", x), ("Y", y), ("Z", z)):
            if v is None: continue
            fv = fnum(v)
            if self.st.get(k) != fv:
                words.append(k + fv); self.st[k] = fv
        if not words: return
        out = []
        if self.first:                       # primer movimiento: G0 G54 X.. Y.. como en el post
            out += ["G0", "G54"]; self.st["G"] = "G0"; self.first = False
        elif self.st.get("G") != f"G{g}":
            out.append(f"G{g}"); self.st["G"] = f"G{g}"
        out += words
        if g == 1 and feed:
            fs = str(int(feed))
            if self.st.get("F") != fs: out.append("F" + fs); self.st["F"] = fs
        self(" ".join(out))
        if z is not None: self.z = z


def circle(cx, cy, r, n=72, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / n), cy + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n + 1)]


def drawing():
    """Lista de trazos (polilineas). Unidades mm; cabe en 0..120 x 0..100."""
    S = []
    S.append([(10, 10), (110, 10), (110, 90), (10, 90), (10, 10)])          # marco 100 x 80
    S.append(circle(60, 50, 30))                                             # circulo D60
    star = [(60 + 25 * math.cos(math.pi / 2 + 4 * math.pi * i / 5), 50 + 25 * math.sin(math.pi / 2 + 4 * math.pi * i / 5)) for i in range(6)]
    S.append(star)                                                           # estrella inscrita
    S.append([(0, 0), (5, 0)]); S.append([(0, 0), (0, 5)])                   # marca del origen X0 Y0
    S.append([(15, 3), (45, 3)]); S.append([(40, 6), (45, 3), (40, 0)])      # flecha +X
    S.append([(50, 0), (56, 6)]); S.append([(50, 6), (56, 0)])               # letra X
    S.append([(3, 15), (3, 45)]); S.append([(0, 40), (3, 45), (6, 40)])      # flecha +Y
    S.append([(0, 56), (3, 53)]); S.append([(6, 56), (3, 53), (3, 50)])      # letra Y
    return S


def program(z_cut):
    w = Writer()
    w("G40 G17 G80 G49 G90")                                 # inicio del post (tape start)
    w("M71")
    w("M73")
    w(f"S{SPINDLE} M3")
    x0, y0 = drawing()[0][0]
    # como el post: XY a la altura a la que este la maquina (arriba, tras G53 Z0 o el home),
    # luego G43 H1 y G90; la primera Z ya va con la compensacion de largo activa
    w.move(0, x=x0, y=y0)
    w("G43 H1")
    w("G90")
    w.move(0, z=SAFE_Z + (AIR if z_cut > 0 else 0))
    safe = w.z
    for pts in drawing():
        x0, y0 = pts[0]
        w.move(0, z=safe)
        w.move(0, x=x0, y=y0)
        w.move(1, z=z_cut, feed=PLUNGE)
        for x, y in pts[1:]:
            w.move(1, x=x, y=y, feed=FEED)
    w.move(0, z=safe)
    w.move(0, x=0, y=0)
    w("G53 Z0")
    w("G0 M05")
    w("M30")
    return "\r\n".join(w.lines + ["%"]) + "\r\n"


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, "nc"), exist_ok=True)
    for name, z in (("prueba_1_aire.nc", AIR - DEPTH), ("prueba_2_grabado.nc", -DEPTH)):
        with open(os.path.join(here, "nc", name), "w", newline="") as fh:
            fh.write(program(z))
        print(name, "ok")
