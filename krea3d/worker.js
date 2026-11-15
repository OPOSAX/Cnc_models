/* Krea3D - calculo pesado fuera de la pagina para que no se congele. */
importScripts("core.js");

self.onmessage = (e) => {
  const { lum, w, h, res, p } = e.data;
  try {
    const H = Krea.prepHeight(lum, w, h, res, p);
    let lastT = 0;
    const files = Krea.generate({ H, w, h, res }, p, (f, msg) => {
      const now = Date.now();
      if (now - lastT > 120 || f >= 1) { lastT = now; self.postMessage({ type: "progress", f, msg }); }
    });
    self.postMessage({ type: "done", files });
  } catch (err) {
    self.postMessage({ type: "error", msg: String(err && err.message || err) });
  }
};
