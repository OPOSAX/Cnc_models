"""Lee los .nc generados y dibuja las trayectorias (verificacion) -> img/trayectorias.png"""
import glob, math, re, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse(path):
    x = y = 0.0; z = 15.0
    segs = []  # (x0,y0,x1,y1,z,kind)
    zmin = 0
    gm = 0
    for line in open(path):
        line = re.sub(r"\(.*?\)", "", line).strip()
        if not line:
            continue
        w = dict((m[0], float(m[1:])) for m in re.findall(r"[A-Z]-?[\d.]+", line))
        if "G" in w and int(w["G"]) in (0, 1, 2, 3):
            gm = int(w["G"])
        g = gm if any(k in w for k in "XYZ") else None
        nx, ny, nz = w.get("X", x), w.get("Y", y), w.get("Z", z)
        if g == 2:
            i, j = w["I"], w["J"]
            cx, cy = x + i, y + j
            r = math.hypot(i, j)
            a0 = math.atan2(y - cy, x - cx)
            for k in range(24):
                a1 = a0 - 2 * math.pi * (k + 1) / 24
                px, py = cx + r * math.cos(a1), cy + r * math.sin(a1)
                segs.append((x, y, px, py, nz, "cut")); x, y = px, py
        elif g in (0, 1):
            segs.append((x, y, nx, ny, min(z, nz), "rapid" if g == 0 else "cut"))
        x, y, z = nx, ny, nz
        zmin = min(zmin, z)
    return segs, zmin


files = sorted(glob.glob("nc/*.nc"))
cols = 6; rows = math.ceil(len(files) / cols)
fig, axs = plt.subplots(rows, cols, figsize=(cols * 3.6, rows * 3.8), dpi=100)
for ax in axs.flat: ax.set_axis_off()
for ax, fp in zip(axs.flat, files):
    segs, zmin = parse(fp)
    ax.set_axis_on()
    for x0, y0, x1, y1, z, k in segs:
        if k == "rapid":
            ax.plot([x0, x1], [y0, y1], color="#bbbbbb", lw=0.4, ls=":")
        elif z < 0:
            c = "#1f77b4" if z <= zmin + 0.01 else ("#d62728" if z > zmin + 0.5 and z <= zmin + 3.5 and z < -1 else "#2ca02c")
            ax.plot([x0, x1], [y0, y1], color=c, lw=0.7)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{os.path.basename(fp)}\nZmin {zmin:.1f} mm", fontsize=8)
fig.suptitle("Trayectorias leidas de los .nc  (azul = profundidad final, rojo = puentes/cajeras, verde = pasadas intermedias)", fontsize=12)
plt.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("img/trayectorias.png", facecolor="white")
print("ok")
