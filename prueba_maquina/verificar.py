"""Lee los NC de nc/, comprueba limites y dibuja img/trayectoria.png (rojo = corte, gris = en vacio)."""
import os, re
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

here = os.path.dirname(os.path.abspath(__file__))
fig, axs = plt.subplots(1, 2, figsize=(13, 6), dpi=110)
for ax, name in zip(axs, ("prueba_1_aire.nc", "prueba_2_grabado.nc")):
    txt = open(os.path.join(here, "nc", name), newline="").read()
    assert txt.endswith("M30\r\n%\r\n") and "\n" not in txt.replace("\r\n", ""), "fin de linea o final"
    p = {"X": 0.0, "Y": 0.0, "Z": None}; g = None
    zmin, safe_ok, n_prev = 1e9, True, None
    for ln in txt.split("\r\n"):
        if not ln or ln == "%": continue
        n = int(re.match(r"N(\d+)", ln).group(1)); assert n_prev is None or n == n_prev + 1; n_prev = n
        for m in re.finditer(r"G(\d+)", ln):
            if m.group(1) in ("0", "1"): g = m.group(1)
        if "G53" in ln: continue
        new = dict(p)
        for k in "XYZ":
            m = re.search(k + r"(-?[\d.]+)", ln)
            if m: new[k] = float(m.group(1))
        if new == p: continue
        assert p["Z"] is not None or (new["X"], new["Y"]) == (p["X"], p["Y"]), "XY antes de subir Z"
        if g == "0" and (new["X"], new["Y"]) != (p["X"], p["Y"]) and new["Z"] < 9.99: safe_ok = False
        zmin = min(zmin, new["Z"])
        if p["Z"] is not None:
            ax.plot([p["X"], new["X"]], [p["Y"], new["Y"]], color="red" if g == "1" else "0.75", lw=1.6 if g == "1" else 0.7)
        p = new
    print(f"{name}: Z minima {zmin}, desplazamientos rapidos en XY por encima de Z10: {safe_ok}")
    ax.set_title(f"{name}  (Z minima {zmin:g} mm)")
    ax.set_aspect("equal"); ax.grid(alpha=.3); ax.set_xlim(-8, 125); ax.set_ylim(-8, 100)
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")
os.makedirs(os.path.join(here, "img"), exist_ok=True)
fig.suptitle("Programa de prueba: rojo = corte (G1), gris = en vacio (G0). Origen X0 Y0 = esquina de la marca en L")
plt.tight_layout(); fig.savefig(os.path.join(here, "img", "trayectoria.png"), facecolor="white")
