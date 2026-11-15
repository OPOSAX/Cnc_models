/* Krea3D - nucleo de calculo: imagen -> relieve -> trayectorias -> G-code.
   Se usa en el navegador (pagina y worker) y en Node (pruebas). Sin dependencias. */
(function (root) {
  "use strict";

  // ------------------------------------------------------------ imagen -> alturas
  function boxBlur(a, w, h, r) {
    if (r < 1) return a;
    const tmp = new Float32Array(a.length), out = new Float32Array(a.length);
    const k = 2 * r + 1;
    for (let y = 0; y < h; y++) {               // horizontal
      const o = y * w; let s = 0;
      for (let x = -r; x <= r; x++) s += a[o + Math.min(w - 1, Math.max(0, x))];
      for (let x = 0; x < w; x++) {
        tmp[o + x] = s / k;
        s += a[o + Math.min(w - 1, x + r + 1)] - a[o + Math.max(0, x - r)];
      }
    }
    for (let x = 0; x < w; x++) {               // vertical
      let s = 0;
      for (let y = -r; y <= r; y++) s += tmp[Math.min(h - 1, Math.max(0, y)) * w + x];
      for (let y = 0; y < h; y++) {
        out[y * w + x] = s / k;
        s += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x];
      }
    }
    return out;
  }

  /** lum: Float32Array 0..1 (0 = negro). Devuelve Z en mm (0 = cara del tablero, negativo = tallado). */
  function prepHeight(lum, w, h, res, p) {
    let v = new Float32Array(lum.length);
    const bp = p.blackPoint || 0, wp = p.whitePoint == null ? 1 : p.whitePoint;
    const g = p.gamma || 1;
    for (let i = 0; i < lum.length; i++) {
      let t = (lum[i] - bp) / Math.max(1e-6, wp - bp);
      t = Math.min(1, Math.max(0, t));
      if (p.darkHigh) t = 1 - t;               // oscuro = alto
      v[i] = Math.pow(t, g);
    }
    const r = Math.round((p.smoothMm || 0) / res);
    if (r >= 1) { v = boxBlur(v, w, h, r); v = boxBlur(v, w, h, r); }
    const H = new Float32Array(v.length);
    for (let i = 0; i < v.length; i++) H[i] = -p.depth * (1 - v[i]);
    return H;
  }

  // ------------------------------------------------------------ herramienta
  /** Lista de celdas que toca la fresa y cuanto sube la punta en cada una. */
  function buildKernel(tool, res) {
    const r = tool.d / 2, m = res * Math.SQRT2, n = Math.ceil((r + m) / res);
    const di = [], dj = [], dz = [];
    const half = (tool.angle || 90) * Math.PI / 360;
    for (let j = -n; j <= n; j++) for (let i = -n; i <= n; i++) {
      // distancia minima a cualquier punto del pixel, mas la holgura de muestreo (conservador)
      const d = Math.max(0, Math.hypot(i * res, j * res) - m);
      if (d > r + 1e-9) continue;
      let z = 0;
      if (tool.type === "ball") z = r - Math.sqrt(Math.max(0, r * r - d * d));
      else if (tool.type === "v") z = d / Math.tan(half);
      di.push(i); dj.push(j); dz.push(z);
    }
    return { di: Int32Array.from(di), dj: Int32Array.from(dj), dz: Float32Array.from(dz), n: di.length };
  }

  /** Altura de la punta para no cortar por debajo del relieve en la celda (c, r). */
  function dropAt(H, w, h, K, c, r, frame) {
    let m = -Infinity;
    for (let k = 0; k < K.n; k++) {
      const cc = c + K.di[k], rr = r + K.dj[k];
      let z;
      if (cc < 0 || rr < 0 || cc >= w || rr >= h) { if (!frame) continue; z = 0; }
      else z = H[rr * w + cc];
      z -= K.dz[k];
      if (z > m) m = z;
    }
    return m;
  }

  // ------------------------------------------------------------ simplificacion
  /** Quita puntos alineados (tolerancia en Z) - algoritmo de "manga". */
  function simplify(s, z, tol) {
    const n = s.length;
    if (n <= 2) return Array.from({ length: n }, (_, i) => i);
    const keep = [0];
    let a = 0, lo = -Infinity, hi = Infinity;
    for (let i = 1; i < n; i++) {
      const sl = (z[i] - z[a]) / (s[i] - s[a]);
      if (sl < lo - 1e-12 || sl > hi + 1e-12) { a = i - 1; keep.push(a); lo = -Infinity; hi = Infinity; }
      const d = s[i] - s[a];
      const l2 = (z[i] - tol - z[a]) / d, h2 = (z[i] + tol - z[a]) / d;
      if (l2 > lo) lo = l2;
      if (h2 < hi) hi = h2;
    }
    if (keep[keep.length - 1] !== n - 1) keep.push(n - 1);
    return keep;
  }

  // ------------------------------------------------------------ escritor G-code
  function fnum(v) {
    v = Math.round(v * 1000) / 1000;
    if (Math.abs(v) < 5e-4) return "0";
    let s = v.toFixed(3).replace(/0+$/, "");
    if (s.startsWith("0.")) s = s.slice(1);
    else if (s.startsWith("-0.")) s = "-" + s.slice(2);
    return s;
  }

  class Writer {
    constructor(o) {
      this.o = o; this.L = []; this.n = 10; this.first = true;
      this.st = { G: null, X: null, Y: null, Z: null, F: null };
      this.x = 0; this.y = 0; this.z = null;
      this.tCut = 0; this.tRapid = 0; this.dist = 0;
    }
    line(s) {
      if (this.o.format === "chaoda") { this.L.push("N" + this.n + " " + s); this.n++; }
      else this.L.push(s);
    }
    header(title) {
      if (this.o.format === "chaoda") {
        this.line("G90");
        this.line("S" + this.o.rpm + " M3");
      } else {
        this.L.push("(" + title + ")");
        this.L.push("G21 G90 G17");
        this.L.push("M3 S" + this.o.rpm);
        this.L.push("G4 P3");
      }
    }
    move(g, x, y, z, feed) {
      const words = [];
      const nx = x == null ? this.x : x, ny = y == null ? this.y : y, nz = z == null ? this.z : z;
      for (const [k, v] of [["X", x], ["Y", y], ["Z", z]]) {
        if (v == null) continue;
        const fv = fnum(v);
        if (this.st[k] !== fv) { words.push(k + fv); this.st[k] = fv; }
      }
      if (!words.length) return;
      const d = Math.hypot(nx - this.x, ny - this.y, (nz == null || this.z == null) ? 0 : nz - this.z);
      const out = [];
      const gs = "G" + g;
      if (this.first) {
        this.first = false; out.push(gs);
        if (this.o.format === "chaoda") out.push("G54");
        this.st.G = gs;
      } else if (this.st.G !== gs) { out.push(gs); this.st.G = gs; }
      out.push(...words);
      if (g === 1 && feed != null) {
        const ff = String(Math.round(feed));
        if (this.st.F !== ff) { out.push("F" + ff); this.st.F = ff; }
        this.tCut += d / feed;
      } else if (g === 0) this.tRapid += d / (this.o.rapid || 5000);
      this.dist += d;
      this.line(out.join(" "));
      this.x = nx; this.y = ny; this.z = nz;
    }
    /** Ir a (x,y) por encima del material. */
    travel(x, y) {
      if (this.first) { this.move(0, x, y); this.move(0, null, null, this.o.safeZ); return; }
      if (this.z < this.o.travelZ - 1e-6) this.move(0, null, null, this.o.travelZ);
      this.move(0, x, y);
    }
    plunge(z) { this.move(1, null, null, z, this.o.plunge); }
    cut(x, y, z) {
      const dxy = Math.hypot(x - this.x, y - this.y), dz = z - this.z;
      const f = (dz < 0 && -dz > dxy) ? this.o.plunge : this.o.feed;   // bajada fuerte -> avance de entrada
      this.move(1, x, y, z, f);
    }
    lift() { this.move(0, null, null, this.o.travelZ); }
    end() {
      this.move(0, null, null, this.o.safeZ);
      if (this.o.format === "chaoda") {
        this.line("G53 Z0"); this.line("G0 M05"); this.line("M30"); this.L.push("%");
      } else { this.L.push("M5"); this.L.push("M30"); }
    }
  }

  // ------------------------------------------------------------ trayectorias
  function linePositions(a0, a1, step) {
    const out = [];
    for (let v = a0; v < a1 - 1e-6; v += step) out.push(v);
    out.push(a1);
    return out;
  }

  /**
   * Genera los programas.
   * g = { H, w, h, res } relieve (fila 0 = arriba de la imagen)
   * p = parametros (ver app.js)
   * Devuelve [{name, op, tile, text, lines, minutes}]
   */
  function generate(g, p, progress) {
    const { H, w, h, res } = g;
    const W = w * res, Ht = h * res;
    const nx = Math.max(1, Math.ceil(W / p.panelW - 1e-6)), ny = Math.max(1, Math.ceil(Ht / p.panelH - 1e-6));
    const files = [];
    const ops = [];
    if (p.rough && p.rough.on) ops.push("desbaste");
    if (p.finish && p.finish.on) ops.push("acabado");
    const totalJobs = ops.length * nx * ny;
    let job = 0;
    const colOf = (x) => Math.min(w - 1, Math.max(0, Math.round(x / res - 0.5)));
    const rowOf = (y) => Math.min(h - 1, Math.max(0, Math.round((Ht - y) / res - 0.5)));

    for (let ty = 0; ty < ny; ty++) for (let tx = 0; tx < nx; tx++) {
      const x0 = tx * W / nx, x1 = (tx + 1) * W / nx, y0 = ty * Ht / ny, y1 = (ty + 1) * Ht / ny;
      const tileName = (nx * ny > 1) ? `_panel${ty + 1}-${tx + 1}` : "";
      for (const op of ops) {
        const T = op === "desbaste" ? p.rough : p.finish;
        const K = buildKernel(T.tool, res);
        const wr = new Writer({ format: p.format, rpm: T.rpm, feed: T.feed, plunge: T.plunge,
          safeZ: p.safeZ, travelZ: p.travelZ, rapid: p.rapid });
        const title = `Krea3D ${p.name} ${op}${tileName}`;
        wr.header(title);
        const alongX = op === "desbaste" || p.finish.dir === "x";
        // lineas de pasada
        const step = op === "desbaste" ? T.tool.d * T.stepoverPct / 100 : T.stepover;
        const fixed = alongX ? linePositions(y0, y1, step) : linePositions(x0, x1, step);
        // muestras a lo largo de cada linea
        const a0 = alongX ? colOf(x0 + 1e-6) : rowOf(y0 + 1e-6), a1 = alongX ? colOf(x1 - 1e-6) : rowOf(y1 - 1e-6);
        const idxs = [];
        if (alongX) for (let c = a0; c <= a1; c++) idxs.push(c);
        else for (let r = a0; r >= a1; r--) idxs.push(r);          // de y bajo a y alto
        const S = new Float64Array(idxs.length);
        for (let k = 0; k < idxs.length; k++)
          S[k] = alongX ? (idxs[k] + 0.5) * res - x0 : (Ht - (idxs[k] + 0.5) * res) - y0;
        const lineDrop = (fv) => {
          const out = new Float64Array(idxs.length);
          if (alongX) { const r = rowOf(fv); for (let k = 0; k < idxs.length; k++) out[k] = dropAt(H, w, h, K, idxs[k], r, p.frame); }
          else { const c = colOf(fv); for (let k = 0; k < idxs.length; k++) out[k] = dropAt(H, w, h, K, c, idxs[k], p.frame); }
          return out;
        };
        const XY = (s, fv) => alongX ? [s, fv - y0] : [fv - x0, s];

        if (op === "desbaste") {
          const allow = T.allowance || 0;
          const drops = fixed.map((fv, i) => {
            if (i % 8 === 0) progress && progress((job + 0.3 * i / fixed.length) / totalJobs, `Desbaste${tileName}: calculando`);
            const d = lineDrop(fv); for (let k = 0; k < d.length; k++) d[k] += allow; return d;
          });
          const levels = [];
          for (let z = -T.stepdown; z > -p.depth + 1e-6; z -= T.stepdown) levels.push(z);
          levels.push(-p.depth);
          let prev = 0;
          levels.forEach((L, li) => {
            progress && progress((job + 0.3 + 0.7 * li / levels.length) / totalJobs, `Desbaste${tileName}: nivel ${fnum(L)} mm`);
            fixed.forEach((fv, i) => {
              const need = drops[i];
              const rev = i % 2 === 1;
              const order = rev ? idxs.map((_, k) => idxs.length - 1 - k) : idxs.map((_, k) => k);
              let run = [];
              const flush = () => {
                if (!run.length) return;
                const s = Float64Array.from(run, (k) => S[k]), z = Float64Array.from(run, (k) => Math.max(L, need[k]));
                const sAbs = rev ? s.map((v) => -v) : s;
                const keep = simplify(sAbs, z, 0.05);
                const [sx, sy] = XY(s[0], fv);
                wr.travel(sx, sy); wr.plunge(z[0]);
                for (let q = 1; q < keep.length; q++) { const [cx, cy] = XY(s[keep[q]], fv); wr.cut(cx, cy, z[keep[q]]); }
                wr.lift(); run = [];
              };
              for (const k of order) {
                if (need[k] < prev - 1e-3) run.push(k); else flush();
              }
              flush();
            });
            prev = L;
          });
        } else {
          let last = null;
          fixed.forEach((fv, i) => {
            if (i % 8 === 0) progress && progress((job + i / fixed.length) / totalJobs, `Acabado${tileName}: pasada ${i + 1}/${fixed.length}`);
            const d = lineDrop(fv);
            const rev = i % 2 === 1;
            const ord = rev ? Array.from(idxs, (_, k) => idxs.length - 1 - k) : Array.from(idxs, (_, k) => k);
            const s = Float64Array.from(ord, (k) => S[k]), z = Float64Array.from(ord, (k) => d[k]);
            const sAbs = rev ? s.map((v) => -v) : s;
            const keep = simplify(sAbs, z, p.tolerance);
            const [sx, sy] = XY(s[0], fv);
            if (last == null) { wr.travel(sx, sy); wr.plunge(z[0]); }
            else {
              // enlace entre pasadas: por encima de lo que haya entre las dos lineas
              let zc = Math.max(wr.z, z[0]);
              const k0 = ord[0];
              const f0 = last, f1 = fv, nmid = Math.ceil(Math.abs(f1 - f0) / res);
              for (let m = 1; m < nmid; m++) {
                const fm = f0 + (f1 - f0) * m / nmid;
                const zz = alongX ? dropAt(H, w, h, K, idxs[k0], rowOf(fm), p.frame) : dropAt(H, w, h, K, colOf(fm), idxs[k0], p.frame);
                if (zz > zc) zc = zz;
              }
              if (zc > wr.z + 1e-6) wr.cut(wr.x, wr.y, zc);
              wr.cut(sx, sy, zc);
              if (z[0] < zc - 1e-6) wr.cut(sx, sy, z[0]);
            }
            for (let q = 1; q < keep.length; q++) { const [cx, cy] = XY(s[keep[q]], fv); wr.cut(cx, cy, z[keep[q]]); }
            last = fv;
          });
        }
        wr.end();
        job++;
        files.push({
          name: `${p.name}_${op}${tileName}.nc`, op, tile: tileName ? `${ty + 1}-${tx + 1}` : "",
          origin: [x0, y0], size: [x1 - x0, y1 - y0],
          text: wr.L.join("\r\n") + "\r\n", lines: wr.L.length,
          minutes: (wr.tCut + wr.tRapid) * 1.15,       // +15% por aceleraciones
        });
      }
    }
    progress && progress(1, "Listo");
    return files;
  }

  // ------------------------------------------------------------ sombreado para la vista previa
  function hillshade(H, w, h, res, depth, rgba) {
    const L = [-0.55, 0.55, 0.63];
    const ex = 2.5;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const zl = H[y * w + Math.max(0, x - 1)], zr = H[y * w + Math.min(w - 1, x + 1)];
      const zu = H[Math.max(0, y - 1) * w + x], zd = H[Math.min(h - 1, y + 1) * w + x];
      const dx = (zr - zl) / (2 * res) * ex, dy = (zu - zd) / (2 * res) * ex;
      const nl = Math.hypot(dx, dy, 1);
      let s = (-dx * L[0] - dy * L[1] + L[2]) / nl;
      s = Math.max(0, Math.min(1, s * 1.25));
      const t = depth > 0 ? 1 + H[i] / depth : 1;          // 1 = superficie
      const base = [176 + 50 * t, 140 + 48 * t, 98 + 44 * t];  // tono MDF/madera
      const o = i * 4;
      rgba[o] = base[0] * (0.35 + 0.75 * s); rgba[o + 1] = base[1] * (0.35 + 0.75 * s);
      rgba[o + 2] = base[2] * (0.35 + 0.75 * s); rgba[o + 3] = 255;
    }
  }

  const api = { boxBlur, prepHeight, buildKernel, dropAt, simplify, fnum, Writer, generate, hillshade };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Krea = api;
})(typeof self !== "undefined" ? self : this);
