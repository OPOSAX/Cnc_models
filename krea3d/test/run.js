#!/usr/bin/env node
/* Pruebas del nucleo de Krea3D (Node, sin dependencias).
   Uso: node krea3d/test/run.js            (sale con codigo 1 si algo falla)
   Incluye un verificador EXACTO e independiente de core.js: lee el G-code generado, recorre cada
   movimiento con un muestreo fino y compara la fresa real (bola, plana o V) con el relieve modelado como
   pixeles cuadrados. Mide la penetracion (gouge, material que la fresa quita de mas) y el material
   sobrante por pixel. */
"use strict";
const path = require("path");
const K = require(path.join(__dirname, "..", "core.js"));

// ------------------------------------------------------------------ utilidades
let nFail = 0, nOk = 0;
const T0 = Date.now();
const results = [];
function check(name, ok, info) {
  if (ok) nOk++; else nFail++;
  results.push({ name, ok, info });
  console.log((ok ? "  ok   " : "  FALLO ") + name + (info ? "  [" + info + "]" : ""));
}
function rng(seed) {             // mulberry32
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const f3 = (v) => (Math.round(v * 1000) / 1000).toFixed(3);

function baseParams(o) {
  const p = {
    name: "t", depth: 8, res: 0.5, panelW: 1000, panelH: 1000, format: "chaoda",
    safeZ: 10, travelZ: 3, frame: false, tolerance: 0.02, rapid: 5000,
    rough: { on: false, tool: { type: "flat", d: 6 }, stepdown: 3, stepoverPct: 40, allowance: 0, feed: 2000, plunge: 600, rpm: 16000 },
    finish: { on: true, tool: { type: "ball", d: 3 }, stepover: 0.3, dir: "x", feed: 1800, plunge: 500, rpm: 18000 },
  };
  for (const k of Object.keys(o || {})) {
    if (k === "rough" || k === "finish") p[k] = Object.assign({}, p[k], o[k]);
    else p[k] = o[k];
  }
  return p;
}
/** Relieve desde una funcion z(x, y) evaluada en el centro de cada pixel (fila 0 = arriba). */
function relief(w, h, res, fz) {
  const H = new Float32Array(w * h);
  for (let row = 0; row < h; row++) for (let c = 0; c < w; c++) {
    const x = (c + 0.5) * res, y = (h - row - 0.5) * res;
    H[row * w + c] = fz(x, y, c, h - 1 - row);
  }
  return { H, w, h, res };
}
const textOf = (f) => f.parts.join("");

// ------------------------------------------------------------------ verificador independiente
function toolProfile(tool) {
  const r = tool.d / 2;
  if (tool.type === "ball") return (d) => r - Math.sqrt(Math.max(0, r * r - d * d));
  if (tool.type === "v") { const t = Math.tan((tool.angle || 90) * Math.PI / 360); return (d) => d / t; }
  return () => 0;
}

/** Lee el programa: devuelve movimientos con coordenadas absolutas del panel y problemas de formato. */
function parseNC(text, fmt) {
  const issues = [];
  if (!text.endsWith("\r\n")) issues.push("no termina en CRLF");
  if (/[^\r]\n|\r[^\n]/.test(text) || text.startsWith("\n")) issues.push("saltos de linea que no son CRLF");
  if (/NaN|Infinity|undefined|null/.test(text)) issues.push("valor no numerico en el texto");
  if (/[^\x20-\x7e\r\n]/.test(text)) issues.push("caracteres no ASCII");
  const lines = text.split("\r\n"); lines.pop();
  let G = null, X = null, Y = null, Z = null, nExpect = 10, afterG53 = false;
  const moves = [];
  lines.forEach((ln, i) => {
    if (ln === "") { issues.push("linea vacia " + (i + 1)); return; }
    if (fmt === "chaoda") {
      if (ln === "%") { if (i !== lines.length - 1) issues.push("% antes del final"); return; }
      const m = /^N(\d+) (.*)$/.exec(ln);
      if (!m) { issues.push("linea sin N: " + ln); return; }
      if (+m[1] !== nExpect) issues.push("numeracion N no consecutiva en " + ln);
      nExpect = +m[1] + 1; ln = m[2];
      if (/\(/.test(ln)) issues.push("comentario en chaoda: " + ln);
    } else if (ln.startsWith("(")) { if (!ln.endsWith(")")) issues.push("comentario mal cerrado"); return; }
    if (/\bG0?[23]\b/.test(ln)) issues.push("arco G2/G3: " + ln);
    if (/B/.test(ln)) issues.push("eje B: " + ln);
    if (/G53/.test(ln)) { afterG53 = true; return; }
    const toks = ln.match(/[A-Z][-+]?[\d.]+/g) || [];
    if (toks.join(" ") !== ln.trim()) issues.push("palabras raras: " + ln);
    let nx = X, ny = Y, nz = Z, has = false;
    for (const t of toks) {
      const c = t[0], v = parseFloat(t.slice(1));
      if (!Number.isFinite(v)) issues.push("numero no valido: " + t);
      if (c === "G" && (v === 0 || v === 1)) G = v;
      if (c === "X") { nx = v; has = true; } else if (c === "Y") { ny = v; has = true; } else if (c === "Z") { nz = v; has = true; }
    }
    if (has) {
      if (afterG53) issues.push("movimiento despues de G53: " + ln);
      if (G == null) issues.push("movimiento sin G0/G1: " + ln);
      moves.push({ g: G, x0: X, y0: Y, z0: Z, x: nx, y: ny, z: nz, src: ln, line: i + 1 });
      X = nx; Y = ny; Z = nz;
    }
  });
  return { moves, issues, lines };
}

/**
 * Verificacion exacta de un archivo. g: relieve completo; file: salida de generate; tool; opt.frame.
 * Material del tablero de ese panel: sus pixeles; fuera del mural, Z0 solo si hay marco y ese lado del
 * panel es borde exterior del mural.
 */
function verify(file, g, tool, p, opt) {
  opt = opt || {};
  const { H, w, h, res } = g;
  const r = tool.d / 2, prof = toolProfile(tool);
  const [ox, oy] = file.origin, [sw, sh] = file.size;
  const C0 = Math.round(ox / res), C1 = Math.round((ox + sw) / res), B0 = Math.round(oy / res), B1 = Math.round((oy + sh) / res);
  const fr = !!p.frame;
  const okC = (c) => (c >= C0 && c < C1) || (fr && C0 === 0 && c < 0) || (fr && C1 === w && c >= w);
  const okB = (b) => (b >= B0 && b < B1) || (fr && B0 === 0 && b < 0) || (fr && B1 === h && b >= h);
  const mat = (c, b) => {
    if (!okC(c) || !okB(b)) return null;
    if (c < 0 || b < 0 || c >= w || b >= h) return 0;
    return H[(h - 1 - b) * w + c];
  };
  const { moves, issues } = parseNC(textOf(file), p.format);
  const sub = opt.sub || 3;
  const tw = C1 - C0, th = B1 - B0;
  const env = opt.env === false ? null : new Float64Array(tw * th * sub * sub).fill(Infinity);
  let maxGouge = 0, gougeAt = null;
  const rapidBad = [];
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, deepX = -Infinity;
  let unknownStart = 0, minZ = Infinity;
  for (const m of moves) {
    if (m.z != null) minZ = Math.min(minZ, m.z);
    if (m.x != null) { minX = Math.min(minX, m.x); maxX = Math.max(maxX, m.x); }
    if (m.y != null) { minY = Math.min(minY, m.y); maxY = Math.max(maxY, m.y); }
    const xyMove = (m.x !== m.x0 || m.y !== m.y0);
    if (m.g === 0) {
      if (xyMove && (m.z0 == null || m.z0 < p.travelZ - 1e-9 || m.z < p.travelZ - 1e-9)) rapidBad.push(m.src + " (linea " + m.line + ")");
      if (!xyMove && m.z0 != null && m.z < m.z0 && m.z < p.travelZ - 1e-9) rapidBad.push("G0 baja de la Z de traslado: " + m.src);
      if (m.z0 == null && m.z == null) rapidBad.push("G0 sin Z conocida: " + m.src);
      continue;
    }
    if (m.x0 == null || m.y0 == null || m.z0 == null) { unknownStart++; continue; }
    if (m.z <= opt.deepZ && m.y >= 0.25 * sh && m.y <= 0.75 * sh) deepX = Math.max(deepX, m.x);
    const len = Math.hypot(m.x - m.x0, m.y - m.y0);
    const nseg = Math.max(1, Math.ceil(len / Math.min(res / 8, 0.05)), Math.ceil(Math.abs(m.z - m.z0) / 0.01));
    for (let q = (m.first ? 0 : 0); q <= nseg; q++) {
      const t = q / nseg;
      const x = ox + m.x0 + (m.x - m.x0) * t, y = oy + m.y0 + (m.y - m.y0) * t, z = m.z0 + (m.z - m.z0) * t;
      const c0 = Math.floor((x - r) / res), c1 = Math.floor((x + r) / res);
      const b0 = Math.floor((y - r) / res), b1 = Math.floor((y + r) / res);
      for (let b = b0; b <= b1; b++) for (let c = c0; c <= c1; c++) {
        const Hv = mat(c, b);
        if (Hv == null) continue;
        const pxl = c * res, pxr = pxl + res, pyb = b * res, pyt = pyb + res;
        const dmin = Math.hypot(Math.max(pxl - x, 0, x - pxr), Math.max(pyb - y, 0, y - pyt));
        if (dmin >= r - 1e-9) continue;
        const gg = Hv - (z + prof(dmin));
        if (gg > maxGouge) { maxGouge = gg; gougeAt = { x: x - ox, y: y - oy, z, c, b, Hv, src: m.src, line: m.line }; }
        if (env && c >= C0 && c < C1 && b >= B0 && b < B1) {
          const base = ((b - B0) * tw + (c - C0)) * sub * sub;
          for (let a = 0; a < sub; a++) for (let e = 0; e < sub; e++) {
            const sx = pxl + (a + 0.5) * res / sub, sy = pyb + (e + 0.5) * res / sub;
            const dd = Math.hypot(sx - x, sy - y);
            if (dd < r) { const zz = z + prof(dd); const k = base + a * sub + e; if (zz < env[k]) env[k] = zz; }
          }
        }
      }
    }
  }
  // material sobrante por pixel (el peor de sus submuestras), con el pixel en coordenadas globales
  let left = null, maxLeft = 0;
  if (env) {
    left = new Float64Array(tw * th);
    for (let b = B0; b < B1; b++) for (let c = C0; c < C1; c++) {
      const base = ((b - B0) * tw + (c - C0)) * sub * sub;
      let mx = -Infinity;
      for (let k = 0; k < sub * sub; k++) mx = Math.max(mx, env[base + k]);
      const Hv = H[(h - 1 - b) * w + c];
      const l = Math.max(0, Math.min(mx, 0) - Hv);
      left[(b - B0) * tw + (c - C0)] = l;
      if (l > maxLeft) maxLeft = l;
    }
  }
  return { maxGouge, gougeAt, rapidBad, issues, nmoves: moves.length, unknownStart, C0, C1, B0, B1, left, maxLeft,
    bounds: { minX, maxX, minY, maxY }, deepX, moves, minZ };
}

/** Comprobaciones comunes a cada archivo generado. */
function checkFile(tag, f, g, p, opt) {
  opt = opt || {};
  const tool = f.op === "desbaste" ? { type: "flat", d: p.rough.tool.d } : p.finish.tool;
  const v = verify(f, g, tool, p, opt);
  const tol = f.op === "desbaste" ? 0 : p.tolerance;
  const lim = tol + 0.003;
  check(`${tag} ${f.name}: sin penetracion (gouge ${f3(v.maxGouge)} <= ${f3(lim)} mm)`, v.maxGouge <= lim,
    v.maxGouge > lim ? JSON.stringify(v.gougeAt) : "");
  check(`${tag} ${f.name}: formato`, v.issues.length === 0, v.issues.slice(0, 3).join(" | "));
  check(`${tag} ${f.name}: ningun G0 por debajo de la Z de traslado`, v.rapidBad.length === 0, v.rapidBad.slice(0, 2).join(" | "));
  check(`${tag} ${f.name}: ninguna Z por debajo de -profundidad`, v.minZ >= -p.depth - 1e-9, "Z min " + f3(v.minZ));
  check(`${tag} ${f.name}: un solo movimiento de inicio sin XY previo`, v.unknownStart === 0, "n=" + v.unknownStart);
  // coordenadas: dentro del panel, salvo el sobrepaso deliberado (radio) en uniones y bordes sin marco
  const r = tool.d / 2, [sw, sh] = f.size;
  const C0 = v.C0, C1 = v.C1, B0 = v.B0, B1 = v.B1, fr = !!p.frame;
  const ovL = (C0 === 0 && fr) ? 0 : r, ovR = (C1 === g.w && fr) ? 0 : r, ovB = (B0 === 0 && fr) ? 0 : r, ovT = (B1 === g.h && fr) ? 0 : r;
  const b = v.bounds, e = 1e-3;
  check(`${tag} ${f.name}: coordenadas en [-sobrepaso, tamano+sobrepaso]`,
    b.minX >= -ovL - e && b.maxX <= sw + ovR + e && b.minY >= -ovB - e && b.maxY <= sh + ovT + e,
    `X ${f3(b.minX)}..${f3(b.maxX)} Y ${f3(b.minY)}..${f3(b.maxY)} tam ${f3(sw)}x${f3(sh)} sobrepaso L${ovL} R${ovR} B${ovB} T${ovT}`);
  // contrato de salida
  const txt = textOf(f);
  const nl = txt.split("\r\n").length - 1;
  check(`${tag} ${f.name}: contrato {parts, lines, bytes}`,
    Array.isArray(f.parts) && f.parts.every((s) => typeof s === "string" && s.endsWith("\r\n")) && nl === f.lines &&
    txt.length === f.bytes && !("text" in f) && Array.isArray(f.origin) && Array.isArray(f.size) && Number.isFinite(f.minutes) &&
    Array.isArray(f.warnings),
    `lines ${f.lines}/${nl} bytes ${f.bytes}/${txt.length}`);
  return v;
}

function run(tag, g, p, opt) {
  const files = K.generate(g, p, null);
  return files.map((f) => ({ f, v: checkFile(tag, f, g, p, opt) }));
}

// ------------------------------------------------------------------ casos
const ONLY = process.env.ONLY ? new RegExp(process.env.ONLY, "i") : null;   // filtro opcional: ONLY=costura
function section(t) { if (ONLY && !ONLY.test(t)) return false; console.log("\n== " + t); return true; }

if (section("Postes de 5x5 px (paredes verticales y esquinas)")) {
  const res = 0.5, w = 40, h = 40;
  const g = relief(w, h, res, (x, y, c, b) => (c >= 18 && c < 23 && b >= 18 && b < 23) ? 0 : -8);
  for (const tool of [{ type: "ball", d: 3 }, { type: "flat", d: 6 }, { type: "flat", d: 3 }, { type: "v", d: 6, angle: 90 }, { type: "ball", d: 6 }]) {
    run(`poste ${tool.type}${tool.d}`, g, baseParams({ finish: { tool, stepover: 0.3 }, rough: { on: true } }));
  }
  const g2 = relief(44, 44, 0.46, (x, y, c, b) => (c >= 20 && c < 25 && b >= 20 && b < 25) ? 0 : -8);
  run("poste flat3.1 res0.46", g2, baseParams({ res: 0.46, finish: { tool: { type: "flat", d: 3.1 }, stepover: 0.4 } }));
}

if (section("Escalones verticales (y alcance junto a la pared)")) {
  const res = 0.5, w = 40, h = 20;
  const g = relief(w, h, res, (x) => x < 10 ? -8 : 0);
  const out = run("pared flat6", g, baseParams({ finish: { tool: { type: "flat", d: 6 }, stepover: 0.5 } }), { deepZ: -7.99 });
  const deep = out[0].v.deepX;
  check(`pared flat6: la fresa llega a X>=6.75 a Z-8 (antes 6.25)`, deep >= 6.75 - 1e-6, "X max a fondo = " + f3(deep));
  const left = out[0].v.left;  // fila central, columnas 16..19
  const row = 10, tw = out[0].v.C1 - out[0].v.C0;
  check(`pared flat6: columnas 16..18 limpias (sobrante < 0.05 mm)`, [16, 17, 18].every((c) => left[row * tw + c] < 0.05),
    [16, 17, 18, 19].map((c) => f3(left[row * tw + c])).join(" "));
  run("pared ball3", g, baseParams({ finish: { tool: { type: "ball", d: 3 }, stepover: 0.3 } }));
  run("pared V90", g, baseParams({ finish: { tool: { type: "v", d: 6, angle: 90 }, stepover: 0.3 } }));
  const gs = relief(w, h, res, (x, y) => (x < 10 ? -8 : 0) + (y < 5 ? -2 : 0));
  run("escalones cruzados ball3 dir y", gs, baseParams({ finish: { tool: { type: "ball", d: 3 }, stepover: 0.3, dir: "y" } }));
}

if (section("Relieve aleatorio por bloques (varias semillas)")) {
  for (const seed of [1, 2, 3, 4, 5]) {
    const R = rng(seed);
    const res = seed % 2 ? 0.7 : 0.5, w = 34, h = 26;
    const H = new Float32Array(w * h).fill(-6);
    for (let k = 0; k < 14; k++) {
      const bw = 1 + Math.floor(R() * 6), bh = 1 + Math.floor(R() * 6), c0 = Math.floor(R() * (w - bw)), r0 = Math.floor(R() * (h - bh)), z = -R() * 8;
      for (let rr = r0; rr < r0 + bh; rr++) for (let cc = c0; cc < c0 + bw; cc++) H[rr * w + cc] = z;
    }
    const g = { H, w, h, res };
    const tools = [{ type: "ball", d: 3 }, { type: "flat", d: 3 }, { type: "v", d: 4, angle: 60 }];
    const tool = tools[seed % 3];
    run(`bloques s${seed} ${tool.type}${tool.d}`, g, baseParams({ res, depth: 8, finish: { tool, stepover: 0.35, dir: seed % 2 ? "x" : "y" }, rough: { on: true, tool: { type: "flat", d: 4 }, stepdown: 2.5, allowance: seed === 4 ? 0.3 : 0 } }), { env: false });
  }
}

if (section("Relieve suave (pendientes): penetracion y sobrante")) {
  const res = 0.5, w = 60, h = 40;
  const g = relief(w, h, res, (x, y) => Math.max(-8, Math.min(0, -8 + 1.0 * (12 - Math.hypot(x - 15, y - 10))))); // cono 45 grados
  for (const tool of [{ type: "ball", d: 3 }, { type: "flat", d: 3 }, { type: "v", d: 6, angle: 90 }]) {
    const out = run(`cono45 ${tool.type}${tool.d}`, g, baseParams({ finish: { tool, stepover: 0.2 } }));
    console.log(`     sobrante maximo ${f3(out[0].v.maxLeft)} mm, lineas ${out[0].f.lines}`);
  }
}

if (section("Resolucion que no divide el panel (73x47 px a 0.7 mm, paneles 20 mm -> 3x2)")) {
  const res = 0.7, w = 73, h = 47;
  const R = rng(7);
  const g = relief(w, h, res, (x, y) => -4 - 3 * Math.sin(x / 3) * Math.cos(y / 4) + (R() < 0.02 ? 1 : 0));
  const p = baseParams({ res, panelW: 20, panelH: 20, finish: { tool: { type: "ball", d: 3 }, stepover: 0.5 }, rough: { on: true } });
  const files = K.generate(g, p, null);
  const T = K.tiles(w, h, res, 20, 20);
  check("73x47: 3x2 paneles", T.nx === 3 && T.ny === 2 && files.length === 12, `${T.nx}x${T.ny}, ${files.length} archivos`);
  const okSize = files.every((f) => f.size[0] < 20 + res - 1e-9 && f.size[1] < 20 + res - 1e-9 &&
    Math.abs(f.size[0] / res - Math.round(f.size[0] / res)) < 1e-6 && Math.abs(f.origin[0] / res - Math.round(f.origin[0] / res)) < 1e-6);
  check("73x47: paneles de pixeles enteros y < 20 mm + un pixel", okSize, files.map((f) => f3(f.size[0]) + "x" + f3(f.size[1])).slice(0, 6).join(" "));
  let area = 0; for (const f of files) if (f.op === "acabado") area += f.size[0] * f.size[1];
  check("73x47: los paneles cubren el mural exacto", Math.abs(area - w * h * res * res) < 1e-6, f3(area));
  for (const f of files) checkFile("73x47", f, g, p, { env: false });
}

if (section("Paneles 3x2: la union no deja escalon (comparado con una sola pieza)")) {
  const res = 0.5, w = 120, h = 80;
  // rampas de 45 y 60 grados que cruzan las uniones (x=20, x=40, y=20) mas un cono
  const fz = (x, y) => {
    const ramp = Math.min(0, -8 + Math.abs(x - 30) * 1.0);
    const ramp2 = Math.min(0, -8 + Math.abs(y - 20) * Math.tan(60 * Math.PI / 180));
    const cone = Math.min(0, -8 + 0.8 * Math.hypot(x - 41, y - 21));
    return Math.max(-8, Math.min(ramp, ramp2, cone, 0) * 0.999);
  };
  const g = relief(w, h, res, fz);
  for (const cfg of [
    { tool: { type: "ball", d: 3 }, dir: "x", frame: false },
    { tool: { type: "ball", d: 3 }, dir: "y", frame: true },
    { tool: { type: "flat", d: 3 }, dir: "x", frame: false },
  ]) {
    const tag = `costura ${cfg.tool.type}${cfg.tool.d} dir${cfg.dir}${cfg.frame ? " marco" : ""}`;
    const pS = baseParams({ frame: cfg.frame, finish: { tool: cfg.tool, stepover: cfg.so || 0.2, dir: cfg.dir } });
    const pP = baseParams({ frame: cfg.frame, panelW: 20, panelH: 20, finish: { tool: cfg.tool, stepover: cfg.so || 0.2, dir: cfg.dir } });
    const single = run(tag + " pieza", g, pS)[0].v;
    const panels = run(tag + " paneles", g, pP);
    check(`${tag}: 6 paneles`, panels.length === 6, "n=" + panels.length);
    const L = new Float64Array(w * h);
    for (const { v } of panels) {
      const tw = v.C1 - v.C0;
      for (let b = v.B0; b < v.B1; b++) for (let c = v.C0; c < v.C1; c++) L[b * w + c] = v.left[(b - v.B0) * tw + (c - v.C0)];
    }
    const r = cfg.tool.d / 2, band = Math.ceil(2 * r / res);
    const cuts = K.tiles(w, h, res, 20, 20);
    let worst = -Infinity, at = null, seamMaxP = 0, seamMaxS = 0;
    for (let b = 0; b < h; b++) for (let c = 0; c < w; c++) {
      const nearX = cuts.cols.slice(1, -1).some((cc) => Math.abs(c + 0.5 - cc) < band);
      const nearY = cuts.rows.slice(1, -1).some((bb) => Math.abs(b + 0.5 - bb) < band);
      if (!nearX && !nearY) continue;
      const s = single.left[b * w + c], q = L[b * w + c];
      seamMaxP = Math.max(seamMaxP, q); seamMaxS = Math.max(seamMaxS, s);
      if (q - s > worst) { worst = q - s; at = { c, b, panels: f3(q), pieza: f3(s) }; }
    }
    const lim = pP.tolerance + 0.03;
    check(`${tag}: sobrante en la union - sobrante en una pieza = ${f3(worst)} <= ${f3(lim)} mm`, worst <= lim,
      JSON.stringify(at) + ` max union ${f3(seamMaxP)} max pieza ${f3(seamMaxS)}`);
  }
}

if (section("Esquinas de panel: comparado pixel a pixel con una sola pieza")) {
  // Cono que cruza las esquinas de 3x3 paneles con cortes que no son multiplos del paso. Antes, la primera
  // y la ultima muestra de cada pasada se quedaban a la Z elevada por su tramo (sin bajar a su Z minima) y
  // en las esquinas quedaban 0.4-0.5 mm de mas respecto a una pieza entera.
  const res = 0.45, w = 48, h = 38;
  const g = relief(w, h, res, (x, y) => Math.max(-8, -1.2 * Math.hypot(x - 12.1, y - 9.3)));
  for (const cfg of [
    { tool: { type: "flat", d: 3.175 }, dir: "x", frame: true },
    { tool: { type: "flat", d: 3.175 }, dir: "y", frame: false },
    { tool: { type: "ball", d: 3 }, dir: "x", frame: false },
    { tool: { type: "v", d: 6, angle: 90 }, dir: "y", frame: true },
  ]) {
    const tag = `esquinas ${cfg.tool.type}${cfg.tool.d} dir${cfg.dir}${cfg.frame ? " marco" : ""}`;
    const pS = baseParams({ res, frame: cfg.frame, finish: { tool: cfg.tool, stepover: 0.9, dir: cfg.dir } });
    const pP = baseParams({ res, frame: cfg.frame, panelW: 7.7, panelH: 6.1, finish: { tool: cfg.tool, stepover: 0.9, dir: cfg.dir } });
    const single = run(tag + " pieza", g, pS, { sub: 1 })[0].v;     // sub 1: material en el centro de cada pixel
    const panels = run(tag + " paneles", g, pP, { sub: 1 });
    check(`${tag}: 3x3 paneles`, panels.length === 9, "n=" + panels.length);
    let worst = -Infinity, at = null;
    for (const { v } of panels) {
      const tw = v.C1 - v.C0;
      for (let b = v.B0; b < v.B1; b++) for (let c = v.C0; c < v.C1; c++) {
        const q = v.left[(b - v.B0) * tw + (c - v.C0)], s0 = single.left[b * w + c];
        if (q - s0 > worst) { worst = q - s0; at = { c, b, paneles: f3(q), pieza: f3(s0) }; }
      }
    }
    // limite: fusion de escalones (theta = 0.2 mm, deja material de mas en puntos sueltos) + tolerancia
    const lim = 0.2 + pP.tolerance + 0.03;
    check(`${tag}: sobrante paneles - sobrante pieza = ${f3(worst)} <= ${f3(lim)} mm en todo pixel`, worst <= lim, JSON.stringify(at));
  }
}

if (section("Extremos de pasada en el borde sin marco")) {
  // columna de borde a -8 junto a Z0: la muestra del extremo (X-1.25 con plana 3) debe bajar a -8
  const res = 0.5, w = 20, h = 10;
  const g = relief(w, h, res, (x, y, c) => (c === 0 || c === w - 1 || c === 10) ? -8 : 0);
  const p = baseParams({ format: "generic", finish: { tool: { type: "flat", d: 3 }, stepover: 0.5 } });
  const out = run("borde plana3", g, p);
  const mv = out[0].v.moves;
  const reachL = mv.some((m) => m.g === 1 && m.x <= -1.2 && m.z <= -7.99);
  const reachR = mv.some((m) => m.g === 1 && m.x >= w * res + 1.2 && m.z <= -7.99);
  check("borde plana3: el extremo de la pasada baja a Z-8 en los dos bordes", reachL && reachR, `izq ${reachL} der ${reachR}`);
}

if (section("Sobrepaso: la punta no baja de -profundidad")) {
  // fuera del panel no hay material y una V estrecha o una bola grande bajaria por debajo del fondo
  const res = 0.5, w = 200, h = 120;
  const g = relief(w, h, res, (x, y) => (x > 20 && x < 80 && y > 15 && y < 45) ? -1 : -8);
  for (const cfg of [
    { tool: { type: "v", d: 10, angle: 30 }, frame: false, panelW: 1000 },
    { tool: { type: "v", d: 12.7, angle: 20 }, frame: true, panelW: 50 },
    { tool: { type: "ball", d: 6 }, frame: false, panelW: 1000, depth: 15 },
  ]) {
    const p = baseParams({ res, depth: cfg.depth || 8, frame: cfg.frame, panelW: cfg.panelW, thick: 18,
      finish: { tool: cfg.tool, stepover: 2 } });
    const H2 = cfg.depth ? relief(w, h, res, (x, y) => (x > 20 && x < 80 && y > 15 && y < 45) ? -1 : -15) : g;
    run(`suelo ${cfg.tool.type}${cfg.tool.d}${cfg.tool.angle ? "/" + cfg.tool.angle : ""}${cfg.frame ? " marco" : ""}`, H2, p, { env: false });
  }
}

if (section("Paneles: 2400x1200 con panel 1200x2400 da 2 paneles con cualquier resolucion")) {
  for (const r0 of [0.7, 0.45, 0.9, 0.5, 1.1, 0.31, 0.33]) {
    const w = Math.round(2400 / r0), h = Math.round(1200 / r0), res = 2400 / w;
    const T = K.tiles(w, h, res, 1200, 2400);
    const sizes = T.cols.slice(1).map((c, i) => (c - T.cols[i]) * res);
    check(`tiles ${r0} mm/px (${w} px): 2x1 paneles de <= 1200 + medio pixel`,
      T.nx === 2 && T.ny === 1 && sizes.every((s) => s <= 1200 + res / 2 + 1e-9), `${T.nx}x${T.ny} ${sizes.map(f3).join(" ")}`);
  }
  // Murales de 3 o mas tableros: no se anade un panel por una fraccion de pixel (tampoco en Y).
  for (const [W, H, r0, pw, ph, ex, ey] of [[3600, 1200, 0.7, 1200, 2400, 3, 1], [3600, 1200, 0.9, 1200, 2400, 3, 1],
    [3600, 1200, 0.33, 1200, 2400, 3, 1], [3600, 1200, 0.37, 1200, 2400, 3, 1], [4800, 2400, 0.7, 1200, 2400, 4, 1],
    [6000, 2400, 0.7, 1200, 2400, 5, 1], [3600, 2400, 0.33, 1200, 2400, 3, 1], [2400, 600, 0.45, 600, 600, 4, 1],
    [4800, 4800, 0.7, 1200, 2400, 4, 2]]) {
    const w = Math.round(W / r0), h = Math.round(H / r0), res = W / w;
    const T = K.tiles(w, h, res, pw, ph);
    check(`tiles mural ${W}x${H} a ${r0} con panel ${pw}x${ph}: ${ex}x${ey}`, T.nx === ex && T.ny === ey,
      `${T.nx}x${T.ny} ${T.cols.slice(1).map((c, i) => f3((c - T.cols[i]) * res)).join(" ")}`);
  }
  // Propiedades en casos aleatorios: ningun panel vacio ni de >= panel + 1 px, y numero minimo de paneles.
  {
    const R = rng(91); let bad = 0, first = "";
    for (let it = 0; it < 20000; it++) {
      const res = 0.1 + R() * 2, w = 1 + Math.floor(R() * 400), h = 1 + Math.floor(R() * 400);
      const pw = res * (1 + R() * 60), ph = res * (1 + R() * 60);
      const T = K.tiles(w, h, res, pw, ph);
      for (const [cuts, n, L, N] of [[T.cols, T.nx, pw, w], [T.rows, T.ny, ph, h]]) {
        const sz = cuts.slice(1).map((c, i) => c - cuts[i]);
        const capN = Math.max(1, Math.floor(L / res + 1 - 1e-6));
        const ok = cuts[0] === 0 && cuts[n] === N && sz.length === n && sz.every((s) => s >= 1 && s * res < L + res + 1e-9) &&
          (n === 1 || Math.ceil(N / (n - 1)) > capN);
        if (!ok) { bad++; if (!first) first = `res ${res} N ${N} L ${L} -> ${n} [${sz.join(",")}]`; }
      }
    }
    check("tiles aleatorio: sin paneles vacios, < panel + 1 px, numero minimo", bad === 0, bad ? `${bad} fallos, p. ej. ${first}` : "20000 casos");
  }
  const T = K.tiles(73, 47, 0.7, 20, 20);
  check("tiles 73x47 a 0.7 con 20 mm: 3x2", T.nx === 3 && T.ny === 2, `${T.nx}x${T.ny}`);
}

if (section("Aviso de programa vacio")) {
  // marco y una plana de 8 en un panel de 6.6 mm de alto: no cabe, no hay nada que cortar
  const g = relief(30, 11, 0.6, () => -4);
  const p = baseParams({ res: 0.6, frame: true, rough: { on: true, tool: { type: "flat", d: 8 } }, finish: { on: true, tool: { type: "ball", d: 3 } } });
  const files = K.generate(g, p, null);
  const R = files.find((f) => f.op === "desbaste"), F = files.find((f) => f.op === "acabado");
  check("vacio: el desbaste trae un aviso", R.warnings.length === 1 && /nada que cortar/.test(R.warnings[0]), JSON.stringify(R.warnings));
  check("vacio: el acabado (que si corta) no trae avisos", F.warnings.length === 0, JSON.stringify(F.warnings));
}

if (section("Marco (frame) en un panel suelto")) {
  const res = 0.5, w = 40, h = 30;
  const g = relief(w, h, res, (x, y) => (x < 3 || y > 12) ? -8 : -3);
  for (const fr of [true, false]) {
    const p = baseParams({ frame: fr, finish: { tool: { type: "ball", d: 3 }, stepover: 0.3 }, rough: { on: true } });
    const out = run(`marco=${fr}`, g, p, { env: false });
    const b = out[out.length - 1].v.bounds, sz = out[0].f.size;
    if (fr) check("marco=true: la fresa no sale del mural (respeta el marco)", b.minX >= -1e-6 && b.minY >= -1e-6 && b.maxX <= sz[0] + 1e-6 && b.maxY <= sz[1] + 1e-6,
      `X ${f3(b.minX)}..${f3(b.maxX)} Y ${f3(b.minY)}..${f3(b.maxY)}`);
    else check("marco=false: la fresa sobrepasa el borde hasta su radio para limpiarlo", b.minX < -1 && b.minX >= -1.5 - 1e-6,
      `X ${f3(b.minX)}..${f3(b.maxX)}`);
  }
}

if (section("Formato Chaoda y generico")) {
  const g = relief(30, 20, 0.5, (x, y) => -2 - 2 * Math.sin(x / 2));
  const p = baseParams({ rough: { on: true } });
  const files = K.generate(g, p, null);
  for (const f of files) {
    const L = textOf(f).split("\r\n");
    check(`chaoda ${f.op}: cabecera N10 G90 / N11 S.. M3 / N12 G0 G54 Z10. / N13 XY`,
      L[0] === "N10 G90" && /^N11 S\d+ M3$/.test(L[1]) && L[2] === "N12 G0 G54 Z10." && /^N13 X[-\d.]+ Y[-\d.]+$/.test(L[3]),
      L.slice(0, 4).join(" | "));
    const n = L.length;
    check(`chaoda ${f.op}: final G0 Z10. / G53 Z0 / G0 M05 / M30 / %`,
      L[n - 1] === "" && L[n - 2] === "%" && /^N\d+ M30$/.test(L[n - 3]) && /^N\d+ G0 M05$/.test(L[n - 4]) && /^N\d+ G53 Z0$/.test(L[n - 5]) && /^N\d+ (G0 )?Z10\.$/.test(L[n - 6]),
      L.slice(n - 6).join(" | "));
    check(`chaoda ${f.op}: G54 solo en el primer movimiento y sin F en G0`, textOf(f).split("G54").length === 2 && !/G0[^\r]*F/.test(textOf(f)));
  }
  const pg = baseParams({ format: "generic", rough: { on: true } });
  const fg = K.generate(g, pg, null);
  for (const f of fg) {
    checkFile("generico", f, g, pg, { env: false });
    const L = textOf(f).split("\r\n");
    const iZ = L.indexOf("G0 Z10."), iM3 = L.findIndex((s) => /^M3 S\d+$/.test(s)), iXY = L.findIndex((s) => /X/.test(s) && !s.startsWith("("));
    check(`generico ${f.op}: sube a Z de seguridad antes de M3 y antes del primer XY`, iZ >= 0 && iZ < iM3 && iM3 < iXY, `Z ${iZ} M3 ${iM3} XY ${iXY}`);
    check(`generico ${f.op}: G4 P3 documentado y final M5/M30`, L.includes("G4 P3") && L.some((s) => /G4 P3000/.test(s)) && L[L.length - 3] === "M5" && L[L.length - 2] === "M30");
  }
}

if (section("Validacion de parametros")) {
  const g = relief(10, 10, 0.5, () => -1);
  check("validate: parametros por defecto sin errores", K.validate(baseParams({ rough: { on: true } })).length === 0,
    K.validate(baseParams({ rough: { on: true } })).join(" | "));
  const bad = [
    ["paso lateral 0", { finish: { stepover: 0 } }],
    ["paso vertical 0", { rough: { on: true, stepdown: 0 } }],
    ["paso % negativo", { rough: { on: true, stepoverPct: -5 } }],
    ["rpm NaN", { finish: { rpm: NaN } }],
    ["avance 0", { finish: { feed: 0 } }],
    ["entrada Infinity", { rough: { on: true, plunge: Infinity } }],
    ["Z traslado >= seguridad", { travelZ: 10, safeZ: 10 }],
    ["Z traslado 0", { travelZ: 0 }],
    ["profundidad 0", { depth: 0 }],
    ["panel 0", { panelW: 0 }],
    ["diametro 0", { finish: { tool: { type: "ball", d: 0 } } }],
    ["diametro desbaste NaN", { rough: { on: true, tool: { type: "flat", d: NaN } } }],
    ["sin operaciones", { finish: { on: false } }],
    ["panel menor que un pixel", { panelW: 0.3, panelH: 0.3 }],
    ["panel alto menor que un pixel", { panelH: 0.4 }],
    ["profundidad mayor que el espesor", { depth: 20, thick: 18 }],
    ["espesor 0", { thick: 0 }],
  ];
  check("validate: espesor valido sin errores", K.validate(baseParams({ thick: 18 })).length === 0);
  {
    const p = baseParams({ panelW: 0.3, panelH: 0.3 }); delete p.res;
    let thrown = null; try { K.generate(g, p, null); } catch (e) { thrown = e; }
    check("generate rechaza panel menor que el pixel del relieve aunque falte p.res", thrown && /pixel/.test(thrown.message), thrown ? thrown.message : "no lanzo");
  }
  for (const [t, o] of bad) {
    const p = baseParams(o);
    const errs = K.validate(p);
    let thrown = null;
    try { K.generate(g, p, null); } catch (e) { thrown = e; }
    check(`validate/generate rechazan: ${t}`, errs.length > 0 && thrown instanceof Error && thrown.message.length > 0, thrown ? thrown.message : "no lanzo");
  }
}

if (section("Salida por bloques (programa de mas de 200.000 lineas)")) {
  const R = rng(11);
  const w = 400, h = 300, res = 0.3;
  const H = new Float32Array(w * h); for (let i = 0; i < H.length; i++) H[i] = -2 - 4 * R();
  const p = baseParams({ res, depth: 6, finish: { tool: { type: "ball", d: 1 }, stepover: 0.1 } });
  const t0 = Date.now();
  const f = K.generate({ H, w, h, res }, p, null)[0];
  const txt = textOf(f);
  check("bloques: varios parts, cada uno <= 200000 lineas y terminado en CRLF",
    f.parts.length >= 2 && f.parts.every((s) => s.endsWith("\r\n") && s.split("\r\n").length - 1 <= 200000),
    `${f.parts.length} parts, ${f.lines} lineas, ${(f.bytes / 1e6).toFixed(1)} MB, ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  check("bloques: lines y bytes coinciden con el texto unido", txt.length === f.bytes && txt.split("\r\n").length - 1 === f.lines);
  const iss = parseNC(txt, "chaoda").issues;
  check("bloques: formato del archivo unido", iss.length === 0, iss.slice(0, 3).join(" | "));
}

// ------------------------------------------------------------------ STL
console.log("\nSTL");
{
  function stlBin(tris, extra) {
    const b = new ArrayBuffer(84 + 50 * tris.length + (extra || 0)), d = new DataView(b);
    d.setUint32(80, tris.length, true);
    tris.forEach((t, i) => t.forEach((v, k) => d.setFloat32(84 + 50 * i + 12 + 4 * k, v, true)));
    return b;
  }
  function stlAscii(tris, solidHeader) {
    const s = (solidHeader || "solid t") + "\n" + tris.map((t) => "  facet normal 0 0 1\n    outer loop\n" +
      [0, 1, 2].map((k) => `      vertex ${t[3 * k].toExponential(6)} ${t[3 * k + 1]} ${t[3 * k + 2]}`).join("\n") +
      "\n    endloop\n  endfacet").join("\n") + "\nendsolid t\n";
    return new TextEncoder().encode(s).buffer;
  }
  // piramide de base 100 x 50 (z = 5) sobre una losa que baja hasta z = 0, cuspide a z = 25
  const A = [0, 0, 5], B = [100, 0, 5], C = [100, 50, 5], D = [0, 50, 5], Tp = [50, 25, 25];
  const pyr = [[A, B, Tp], [B, C, Tp], [C, D, Tp], [D, A, Tp], [[0, 0, 0], [100, 50, 0], [100, 0, 0]], [[0, 0, 0], [0, 50, 0], [100, 50, 0]],
    [[0, 0, 0], [100, 0, 0], [100, 0, 5]], [[0, 0, 0], [100, 0, 5], [0, 0, 5]]].map((t) => t.flat());
  const mb = K.parseSTL(stlBin(pyr));
  check("STL binario: triangulos y limites", mb.n === 8 && mb.max[2] === 25 && mb.min[2] === 0 && mb.max[0] === 100);
  const ma = K.parseSTL(stlAscii(pyr));
  check("STL de texto: mismos triangulos que el binario", ma.n === 8 && ma.tri.every((v, i) => Math.abs(v - mb.tri[i]) < 1e-4));
  const mh = K.parseSTL(stlBin(pyr, 7));
  check("STL binario con bytes de mas al final", mh.n === 8);
  const mSolid = (() => { const b = stlBin(pyr); new Uint8Array(b).set(new TextEncoder().encode("solid exported by cad"), 0); return K.parseSTL(b); })();
  check("STL binario cuya cabecera empieza por 'solid'", mSolid.n === 8);
  check("STL de Uint8Array (no ArrayBuffer)", K.parseSTL(new Uint8Array(stlBin(pyr))).n === 8);
  let msg = "";
  try { K.parseSTL(new ArrayBuffer(30)); } catch (e) { msg = e.message; }
  check("archivo que no es STL: error claro", /no parece un STL/.test(msg), msg);
  msg = ""; try { K.parseSTL(stlBin([[0, 0, 0, NaN, 0, 0, 0, 1, 0]])); } catch (e) { msg = e.message; }
  check("STL sin triangulos validos: error claro", /no contiene/.test(msg), msg);

  const r = K.rasterSTL(mb, "z", 100, 50);
  const at = (x, y) => r.hm[y * 100 + x];
  check("raster: todo cubierto", r.covered === 5000);
  // el pixel de la esquina se mide en su centro (0.5, 0.5): cara D-A-T -> 5 + 20 * 0.5 / 50 = 5.2
  check("raster: la base (z=0) no cuenta, el relieve visible va de ~5 a 25", Math.abs(r.zLo - 5.2) < 1e-4 && Math.abs(r.zHi - 25) < 1e-6, `${r.zLo}..${r.zHi}`);
  check("raster: cuspide arriba (1) y esquinas abajo (~0)", at(50, 25) > 0.97 && at(0, 0) < 0.03 && at(99, 49) < 0.03, `${at(50, 25)} ${at(0, 0)}`);
  // altura exacta en un punto interior: cara A-B-T, en (25.5, 10.5) -> 5 + 20 * (y / 25)
  const zExp = 5 + 20 * (10.5 / 25);
  const zGot = r.zLo + (r.zHi - r.zLo) * at(25, 50 - 1 - 10);
  check("raster: altura interpolada exacta", Math.abs(zGot - zExp) < 1e-3, `${zGot} vs ${zExp}`);
  check("raster: fila 0 = arriba (y maxima)", Math.abs(at(50, 0) - at(50, 49)) < 1e-6 && at(50, 12) > at(50, 1));
  const ry = K.rasterSTL(mb, "y", 100, 25);
  check("eje Y arriba: planta X-Z (100 x 25), relieve en Y", ry.size.sizeU === 100 && ry.size.sizeV === 25 && ry.size.sizeZ === 50);
  const rx = K.rasterSTL(mb, "x", 50, 25);
  check("eje X arriba: planta Y-Z", rx.size.sizeU === 50 && rx.size.sizeV === 25 && rx.size.sizeZ === 100);
  // triangulo mas pequeno que un pixel: no se pierde
  const tiny = K.parseSTL(stlBin([[0, 0, 0, 10, 0, 0, 0, 10, 0], [4.9, 4.9, 3, 5.0, 4.9, 3, 4.9, 5.0, 3]].map((t) => t)));
  const rt = K.rasterSTL(tiny, "z", 10, 10);
  check("triangulo menor que un pixel: su altura aparece", Math.max(...rt.hm) === 1);
  // modelo que no cubre todo: el fondo queda a 0 y lo cubierto se mide desde el punto mas bajo del modelo
  const isl = K.parseSTL(stlBin([[0, 0, 0, 100, 0, 0, 0, 100, 0], [100, 100, 10, 100, 0, 0, 0, 100, 0]].map((t) => t)));
  const ri = K.rasterSTL(isl, "z", 50, 50);
  check("modelo con zonas vacias: fondo a 0", ri.covered === 2500 || ri.hm.some((v) => v === 0));
  msg = ""; try { K.rasterSTL(K.parseSTL(stlBin([[0, 0, 0, 10, 0, 0, 0, 0, 10]])), "z", 10, 10); } catch (e) { msg = e.message; }
  check("modelo sin planta visto desde arriba: error claro", /no tiene ancho o alto/.test(msg), msg);
  // de punta a punta: STL -> prepHeight -> generate, sin gouge respecto al propio relieve
  const w = 120, h = 60, res = 0.5;
  const hm = K.rasterSTL(mb, "z", w, h).hm;
  const p = baseParams({ depth: 10, rough: { on: true }, finish: { on: true, tool: { type: "ball", d: 3 } } });
  p.W = w * res; p.H = h * res; p.thick = 18; p.gamma = 1; p.blackPoint = 0; p.whitePoint = 1; p.smoothMm = 0; p.darkHigh = false;
  const H = K.prepHeight(hm, w, h, res, p);
  const files = K.generate({ H, w, h, res }, p, null);
  const txt = files.map((f) => f.parts.join("")).join("");
  check("STL -> NC: desbaste y acabado sin NaN", files.length === 2 && !/NaN|Infinity/.test(txt) && Math.min(...H) >= -10.0001 && Math.max(...H) <= 1e-6,
    files.map((f) => f.op + ":" + f.lines).join(" "));
}

// ------------------------------------------------------------------ resumen
console.log(`\nResumen: ${nOk} correctas, ${nFail} fallos (${((Date.now() - T0) / 1000).toFixed(0)} s).`);
if (nFail) {
  console.log("Fallos:");
  for (const r of results) if (!r.ok) console.log("  - " + r.name + (r.info ? "  [" + r.info + "]" : ""));
}
process.exit(nFail ? 1 : 0);
