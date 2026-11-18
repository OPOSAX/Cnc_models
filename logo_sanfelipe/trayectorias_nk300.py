"""Dibuja las trayectorias de los NC del NK300 sobre la plancha: img/trayectorias_nk300.png"""
import os, re, sys
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
d = float(sys.argv[1]) if len(sys.argv) > 1 else 6
suf = "_centro" if len(sys.argv) > 2 and sys.argv[2] == "centro" else ""
off = -600 if suf else 0
here = os.path.dirname(os.path.abspath(__file__))
fig, axs = plt.subplots(1, 2, figsize=(18, 9.5), dpi=110)
for ax, (name, title) in zip(axs, ((f"logo_1_desbaste_plana{d:g}{suf}.nc", "1 Desbaste"), (f"logo_2_acabado_plana{d:g}{suf}.nc", "2 Acabado de paredes"))):
    p = {"X": None, "Y": None, "Z": None}; g = None; cut = []; zc = []; rap = []
    for l in open(os.path.join(here, "nc_nk300", name)).read().split("\n"):
        l = l.strip()
        if not l or l.startswith("("): continue
        m = re.match(r"G([01])(?!\d)", l)
        if m: g = m.group(1)
        new = dict(p)
        for k in "XYZ":
            mm = re.search(k + r"(-?[\d.]+)", l)
            if mm: new[k] = float(mm.group(1))
        if None not in p.values() and None not in new.values() and (new["X"], new["Y"]) != (p["X"], p["Y"]):
            seg = [(p["X"], p["Y"]), (new["X"], new["Y"])]
            if g == "0": rap.append(seg)
            else: cut.append(seg); zc.append(min(p["Z"], new["Z"]))
        p = new
    ax.add_patch(Rectangle((off, off), 1200, 1200, fill=False, ec="0.4", lw=1.2, ls="--"))
    ax.add_collection(LineCollection(rap, colors="0.75", lw=0.3))
    lc = LineCollection(cut, array=zc, cmap="viridis", lw=0.35); ax.add_collection(lc)
    ax.plot(0, 0, "r+", ms=14, mew=2); ax.annotate("X0 Y0", (0, 0), (15, -30), color="r")
    ax.set_xlim(off - 30, off + 1230); ax.set_ylim(off - 60, off + 1230); ax.set_aspect("equal")
    ax.set_title(f"{title}: {name}\n(gris = desplazamiento rapido G00 a Z5/Z25; color = corte G01 segun profundidad)")
    plt.colorbar(lc, ax=ax, fraction=0.04, label="Z (mm)")
fig.suptitle(f"Logo San Felipe en plancha MDF 1200 x 1200 x 12 - fresa plana D{d:g} - Weihong NK300")
plt.tight_layout(); fig.savefig(os.path.join(here, "img", f"trayectorias_nk300{suf}.png"), facecolor="white")
print("ok")
