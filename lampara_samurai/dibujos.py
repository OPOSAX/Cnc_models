"""Genera img/montaje.png (render 3D) e img/piezas.png (lamina de piezas acotadas)."""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import Polygon
import geometria as G

COL = {"negro": "#2a2a2a", "oro": "#d9a441"}
EDGE = {"negro": "#555555", "oro": "#8a6420"}


def _solid(poly, pl, t):
    o, e1, e2, e3 = pl
    ext = np.array(poly.exterior.coords)[:-1]
    bot = [o + x * e1 + y * e2 for x, y in ext]
    top = [p + t * e3 for p in bot]
    faces = [bot, top]
    n = len(bot)
    for i in range(n):
        j = (i + 1) % n
        faces.append([bot[i], bot[j], top[j], top[i]])
    return faces


def _hat_faces(n=72):
    faces = []
    R0, R1 = G.HAT_RHOLE, G.HAT_R
    z = lambda r: G.HAT_ZAPEX - G.HAT_H / G.HAT_R * r
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        faces.append([(R0 * math.cos(a0), R0 * math.sin(a0), z(R0)), (R1 * math.cos(a0), R1 * math.sin(a0), z(R1)),
                      (R1 * math.cos(a1), R1 * math.sin(a1), z(R1)), (R0 * math.cos(a1), R0 * math.sin(a1), z(R0))])
    return faces


def _light(faces, base_rgb):
    """sombreado simple por normal."""
    L = np.array([0.4, 0.7, 0.6]); L /= np.linalg.norm(L)
    cols = []
    for f in faces:
        f = np.array(f, float)
        nrm = np.cross(f[1] - f[0], f[2] - f[0])
        k = np.linalg.norm(nrm)
        s = abs(np.dot(nrm / k, L)) if k > 1e-9 else 0.5
        cols.append(np.clip(np.array(base_rgb) * (0.45 + 0.75 * s), 0, 1))
    return cols


def render(ax, pcs, explode=0.0, elev=12, azim=60):
    allf, allc = [], []
    for p in pcs:
        rgb = matplotlib.colors.to_rgb(COL[p.color])
        for pl in p.placements:
            o, e1, e2, e3 = pl
            off = np.zeros(3)
            if explode:
                c = o + e1 * 0 + e2 * 0
                zc = o[2]
                off = np.array([0, 0, 0.0])
                if p.pid in ("P09", "P10", "P11"): off[2] = 2.2 * explode
                elif p.pid in ("P08",): off[2] = 1.6 * explode
                elif p.pid in ("P14",): off[2] = 1.1 * explode
                elif p.pid in ("P15", "P16"):
                    off = np.array([o[0] * 0.8, 0.0, 0]) * explode / 100 + np.array([0, 0.6 * explode if p.pid == "P16" else 0.3 * explode, 0.5 * explode])
                elif p.pid in ("P12", "P13"): off = np.array([0, 0.9 * explode, 0.35 * explode])
                elif p.pid in ("P06", "P07"): off = np.array([e3[0], e3[1], 0]) * -0.25 * explode * np.sign(np.dot(o, e3) + 1e-9) + np.array([0, 0, 0.6 * explode])
                elif p.pid in ("P04",): off[2] = 0.3 * explode
                elif p.pid in ("P05",): off[2] = 0.1 * explode
                elif p.pid in ("P01",): off[1] = 0.6 * explode
                elif p.pid in ("P02",): off[1] = -0.6 * explode
                elif p.pid in ("P03",): off[0] = 0.6 * explode * np.sign(o[0])
            pl2 = (o + off, e1, e2, e3)
            f = _solid(p.outline, pl2, p.thick)
            allf += f; allc += _light(f, rgb)
    hat = _hat_faces()
    if explode:
        hat = [[(x, y, z + 2.2 * explode) for x, y, z in f] for f in hat]
    allf += hat; allc += _light(hat, matplotlib.colors.to_rgb(COL["negro"]))
    pc = Poly3DCollection(allf, facecolors=allc, edgecolors=(0, 0, 0, 0.15), linewidths=0.3)
    ax.add_collection3d(pc)
    zmax = 780 + (2.2 * explode if explode else 0)
    ax.set_xlim(-260, 260); ax.set_ylim(-260, 260); ax.set_zlim(0, zmax)
    ax.set_box_aspect((520, 520, zmax))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def montaje(pcs, path):
    fig = plt.figure(figsize=(18, 9), dpi=110)
    titles = ["Vista frontal", "Vista 3/4", "Despiece (explosionado)"]
    views = [(4, 90, 0), (18, 55, 0), (18, 55, 120)]
    for i, (el, az, ex) in enumerate(views):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        render(ax, pcs, explode=ex, elev=el, azim=az)
        ax.set_title(titles[i], fontsize=14)
    fig.suptitle("Lampara Samurai - montaje (altura 760 mm, base 330 x 220 mm, sombrero 440 mm)", fontsize=15)
    plt.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def _draw_piece(ax, p):
    fc = COL[p.color]
    def fill(poly, **kw):
        x, y = poly.exterior.xy
        ax.fill(x, y, **kw)
        for it in poly.interiors:
            xi, yi = it.xy
            ax.fill(xi, yi, color="white")
    fill(p.outline, color=fc, alpha=0.85 if p.color == "oro" else 0.75, ec="k", lw=1)
    for h in p.holes:
        x, y = h.exterior.xy
        ax.fill(x, y, color="white", ec="k", lw=0.8)
    for (pk, dep) in p.pockets:
        x, y = pk.exterior.xy
        ax.fill(x, y, color="#5aa0d8", ec="k", lw=0.6)
        c = pk.centroid
        ax.text(c.x, c.y, f"{dep:g}", ha="center", va="center", fontsize=6, color="white")
    for (cx, cy, d) in p.circles:
        ax.add_patch(plt.Circle((cx, cy), d / 2, color="white", ec="k", lw=0.8))
    for (ln, dep) in p.engraves:
        x, y = ln.xy
        ax.plot(x, y, "r--", lw=1)
    b = p.outline.bounds
    w, h = b[2] - b[0], b[3] - b[1]
    ax.annotate("", xy=(b[0], b[1] - 0.06 * max(w, h)), xytext=(b[2], b[1] - 0.06 * max(w, h)),
                arrowprops=dict(arrowstyle="<->", lw=0.7))
    ax.text((b[0] + b[2]) / 2, b[1] - 0.06 * max(w, h), f"{w:.1f}", ha="center", va="bottom", fontsize=7,
            bbox=dict(fc="white", ec="none", pad=0.5))
    ax.annotate("", xy=(b[2] + 0.06 * max(w, h), b[1]), xytext=(b[2] + 0.06 * max(w, h), b[3]),
                arrowprops=dict(arrowstyle="<->", lw=0.7))
    ax.text(b[2] + 0.06 * max(w, h), (b[1] + b[3]) / 2, f"{h:.1f}", ha="left", va="center", fontsize=7, rotation=90,
            bbox=dict(fc="white", ec="none", pad=0.5))
    m = 0.15 * max(w, h)
    ax.set_xlim(b[0] - m, b[2] + m); ax.set_ylim(b[1] - m, b[3] + m)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    mat = "MDF 15" if p.thick == 15 else f"Contrach. flex {p.thick:g}"
    ax.set_title(f"{p.pid}  {p.name}\nx{p.qty}  |  {mat}  |  {p.color}", fontsize=8.5)


def piezas(pcs, path):
    n = len(pcs)
    cols = 6
    rows = math.ceil(n / cols)
    fig, axs = plt.subplots(rows, cols, figsize=(cols * 3.6, rows * 4.1), dpi=110)
    for ax in axs.flat: ax.set_axis_off()
    for ax, p in zip(axs.flat, pcs):
        ax.set_axis_on()
        _draw_piece(ax, p)
    fig.suptitle("Lampara Samurai - piezas a cortar (cotas en mm; azul = cajera con su profundidad; rojo = linea de marcado)",
                 fontsize=13)
    plt.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    pcs, info = G.build()
    montaje(pcs, "img/montaje.png")
    piezas(pcs, "img/piezas.png")
    print("ok")
