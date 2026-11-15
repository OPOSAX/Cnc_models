/* Krea3D - interfaz. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const num = (id) => parseFloat($(id).value);
  let src = null;          // canvas con la imagen original
  let aspect = 1;
  let lastFiles = [];

  // ---------------------------------------------------------- imagen de ejemplo
  function sampleImage() {
    const c = document.createElement("canvas"); c.width = 960; c.height = 600;
    const g = c.getContext("2d");
    const sky = g.createLinearGradient(0, 0, 0, 600);
    sky.addColorStop(0, "#3a3a3a"); sky.addColorStop(1, "#7a7a7a");
    g.fillStyle = sky; g.fillRect(0, 0, 960, 600);
    // sol con rayos
    g.save(); g.translate(640, 210);
    for (let i = 0; i < 24; i++) {
      g.rotate(Math.PI / 12); g.fillStyle = i % 2 ? "#8c8c8c" : "#9d9d9d";
      g.beginPath(); g.moveTo(0, 0); g.lineTo(330, -26); g.lineTo(330, 26); g.closePath(); g.fill();
    }
    const sun = g.createRadialGradient(0, 0, 10, 0, 0, 110);
    sun.addColorStop(0, "#ffffff"); sun.addColorStop(1, "#d9d9d9");
    g.fillStyle = sun; g.beginPath(); g.arc(0, 0, 105, 0, Math.PI * 2); g.fill();
    g.restore();
    // montañas
    const ridge = (base, amp, f, ph, col) => {
      g.fillStyle = col; g.beginPath(); g.moveTo(0, 600);
      for (let x = 0; x <= 960; x += 6) {
        const y = base - amp * (0.6 * Math.sin(x / f + ph) + 0.3 * Math.sin(x / (f * 0.37) + ph * 2) + 0.15 * Math.sin(x / (f * 0.13)));
        g.lineTo(x, y);
      }
      g.lineTo(960, 600); g.closePath(); g.fill();
    };
    ridge(360, 90, 120, 0.5, "#b4b4b4");
    ridge(430, 70, 90, 2.1, "#cfcfcf");
    ridge(500, 45, 70, 4.0, "#e8e8e8");
    // olas
    g.strokeStyle = "#5a5a5a"; g.lineWidth = 7;
    for (let k = 0; k < 3; k++) {
      g.beginPath();
      for (let x = 0; x <= 960; x += 4) g.lineTo(x, 540 + k * 22 + 8 * Math.sin(x / 26 + k));
      g.stroke();
    }
    return c;
  }

  function setSource(canvas, label) {
    src = canvas; aspect = canvas.width / canvas.height;
    $("imgTag").textContent = label;
    if ($("lock").checked) $("Hh").value = Math.round(num("W") / aspect);
    refresh();
  }

  function loadFile(file) {
    if (!file || !file.type.startsWith("image/")) { showAlerts([{ bad: true, t: "Ese archivo no es una imagen. Usa JPG o PNG." }]); return; }
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      const c = document.createElement("canvas"); c.width = im.naturalWidth; c.height = im.naturalHeight;
      c.getContext("2d").drawImage(im, 0, 0); URL.revokeObjectURL(url);
      const base = file.name.replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "_").slice(0, 40);
      if (base) $("name").value = base;
      setSource(c, `${im.naturalWidth} × ${im.naturalHeight} px`);
    };
    im.onerror = () => showAlerts([{ bad: true, t: "No se pudo leer la imagen." }]);
    im.src = url;
  }

  /** Luminancia 0..1 de la imagen remuestreada a w×h. */
  function luminance(w, h) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.fillStyle = "#fff"; g.fillRect(0, 0, w, h);
    g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
    g.drawImage(src, 0, 0, w, h);
    const d = g.getImageData(0, 0, w, h).data;
    const lum = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) lum[i] = (0.2126 * d[i * 4] + 0.7152 * d[i * 4 + 1] + 0.0722 * d[i * 4 + 2]) / 255;
    return lum;
  }

  // ---------------------------------------------------------- parametros
  function params() {
    const fType = $("fType").value;
    return {
      name: ($("name").value || "mural").replace(/[^\w-]+/g, "_"),
      W: num("W"), H: num("Hh"), depth: num("depth"), thick: num("thick"), res: num("res"),
      darkHigh: $("darkHigh").checked, gamma: num("gamma"),
      blackPoint: num("blackPoint") / 100, whitePoint: num("whitePoint") / 100, smoothMm: num("smoothMm"),
      rough: { on: $("roughOn").checked, tool: { type: "flat", d: num("rD") }, stepdown: num("rStep"),
        stepoverPct: num("rOver"), allowance: num("rAllow"), feed: num("rF"), plunge: num("rFz"), rpm: Math.round(num("rS")) },
      finish: { on: $("finishOn").checked, tool: { type: fType, d: num("fD"), angle: num("fAngle") }, stepover: num("fOver"),
        dir: $("fDir").value, feed: num("fF"), plunge: num("fFz"), rpm: Math.round(num("fS")) },
      format: $("format").value, safeZ: num("safeZ"), travelZ: num("travelZ"), frame: $("frame").checked,
      tolerance: num("tolerance"), panelW: num("panelW"), panelH: num("panelH"), rapid: 5000,
    };
  }

  function check(p) {
    const a = [];
    const bad = (t) => a.push({ bad: true, t }), warn = (t) => a.push({ t });
    if (!(p.W > 0 && p.H > 0)) bad("Indica el ancho y el alto del mural.");
    if (!(p.depth > 0)) bad("La profundidad debe ser mayor que 0.");
    if (p.depth > p.thick - 3) warn(`La profundidad (${p.depth} mm) deja menos de 3 mm de fondo en un tablero de ${p.thick} mm.`);
    if (!p.rough.on && !p.finish.on) bad("Activa al menos el desbaste o el acabado.");
    if (p.rough.on && p.rough.stepdown > p.rough.tool.d) warn("El paso vertical del desbaste es mayor que el diámetro de la fresa; es arriesgado.");
    if (p.finish.on && p.finish.stepover > p.finish.tool.d / 2) warn("El paso lateral del acabado es grande para esa fresa: quedarán surcos visibles.");
    if (p.finish.on && !p.rough.on && p.depth > 3) warn("Sin desbaste, la fresa de acabado tendrá que quitar todo el material de una pasada.");
    if (p.travelZ >= p.safeZ) warn("La Z de traslado debería ser menor que la Z de seguridad.");
    const cells = (p.W / p.res) * (p.H / p.res);
    if (cells > 30e6) bad(`Con ${p.res} mm/px salen ${(cells / 1e6).toFixed(0)} millones de puntos. Sube la resolución a ${Math.sqrt(p.W * p.H / 25e6).toFixed(2)} mm/px o más.`);
    if (p.finish.on && p.finish.tool.d / 2 < p.res) warn("La fresa de acabado es más fina que la resolución: baja los mm/px para aprovecharla.");
    return a;
  }

  function showAlerts(a) {
    const box = $("alerts"); box.textContent = "";
    for (const x of a) { const d = document.createElement("div"); d.className = "alert" + (x.bad ? " bad" : ""); d.textContent = x.t; box.appendChild(d); }
  }

  const panelsOf = (p) => [Math.max(1, Math.ceil(p.W / p.panelW - 1e-6)), Math.max(1, Math.ceil(p.H / p.panelH - 1e-6))];

  // ---------------------------------------------------------- vista previa
  let prevH = null, prevW = 0, prevHh = 0;
  function refresh() {
    if (!src) return;
    const p = params();
    const [nx, ny] = panelsOf(p);
    $("meta").textContent = `${p.W} × ${p.H} mm`;
    $("kSize").textContent = `${p.W} × ${p.H}`;
    $("kPanels").textContent = nx * ny === 1 ? "1" : `${nx * ny} (${nx}×${ny})`;
    $("kGrid").textContent = `${Math.round(p.W / p.res)} × ${Math.round(p.H / p.res)}`;
    $("kDepth").textContent = `${p.depth} mm`;
    $("fTag").textContent = { ball: "fresa bola", flat: "fresa plana", v: "fresa en V" }[p.finish.tool.type];
    $("fmtTag").textContent = p.format === "chaoda" ? "Chaoda" : "Genérico";
    $("fAngleBox").hidden = p.finish.tool.type !== "v";
    $("gammaV").textContent = (+p.gamma).toFixed(2);
    $("bpV").textContent = Math.round(p.blackPoint * 100);
    $("wpV").textContent = Math.round(p.whitePoint * 100);
    showAlerts(check(p));
    if (!(p.W > 0 && p.H > 0)) return;

    const cv = $("cv2d");
    const maxW = 900, maxH = 560;
    const s = Math.min(maxW / p.W, maxH / p.H);
    const w = Math.max(20, Math.round(p.W * s)), h = Math.max(20, Math.round(p.H * s));
    const res = p.W / w;
    const lum = luminance(w, h);
    const H = Krea.prepHeight(lum, w, h, res, p);
    prevH = H; prevW = w; prevHh = h;
    cv.width = w; cv.height = h;
    const g = cv.getContext("2d");
    const img = g.createImageData(w, h);
    Krea.hillshade(H, w, h, res, p.depth, img.data);
    g.putImageData(img, 0, 0);
    if (nx * ny > 1) {
      g.save(); g.setLineDash([8, 6]); g.lineWidth = 2; g.strokeStyle = "#3bbfb5";
      g.font = "600 14px 'IBM Plex Mono', monospace"; g.fillStyle = "#ffffff";
      for (let i = 1; i < nx; i++) { const x = Math.round(w * i / nx) + 0.5; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); }
      for (let j = 1; j < ny; j++) { const y = Math.round(h * j / ny) + 0.5; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
        const lbl = `${ny - j}-${i + 1}`;
        g.fillText(lbl, w * i / nx + 8, h * (j + 1) / ny - 8);
      }
      g.restore();
    }
    if (!$("v3d").hidden) draw3d();
  }

  // ---------------------------------------------------------- 3D
  let three = null;
  function draw3d() {
    if (!window.THREE || !prevH) return;
    const el = $("v3d");
    const p = params();
    if (!three) {
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
      el.appendChild(renderer.domElement);
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(35, 1, 1, 20000);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 0.55));
      const sun = new THREE.DirectionalLight(0xffffff, 0.9); sun.position.set(-1, 1.2, 1.4); scene.add(sun);
      const controls = THREE.OrbitControls ? new THREE.OrbitControls(camera, renderer.domElement) : null;
      if (controls) controls.enableDamping = true;
      three = { renderer, scene, camera, controls, mesh: null };
      const loop = () => {
        requestAnimationFrame(loop);
        if (el.hidden) return;
        const cw = el.clientWidth, ch = el.clientHeight;
        if (renderer.domElement.width !== Math.round(cw * renderer.getPixelRatio())) {
          renderer.setSize(cw, ch, false); camera.aspect = cw / ch; camera.updateProjectionMatrix();
        }
        controls && controls.update();
        renderer.render(scene, camera);
      };
      loop();
    }
    const sx = Math.max(2, Math.min(prevW - 1, 360)), sy = Math.max(2, Math.round(sx * prevHh / prevW));
    const geo = new THREE.PlaneGeometry(p.W, p.H, sx, sy);
    const pos = geo.attributes.position;
    for (let j = 0; j <= sy; j++) for (let i = 0; i <= sx; i++) {
      const ci = Math.min(prevW - 1, Math.round(i / sx * (prevW - 1))), rj = Math.min(prevHh - 1, Math.round(j / sy * (prevHh - 1)));
      pos.setZ(j * (sx + 1) + i, prevH[rj * prevW + ci]);
    }
    geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: 0xc9a06a, roughness: 0.85, metalness: 0 });
    if (three.mesh) { three.scene.remove(three.mesh); three.mesh.geometry.dispose(); }
    three.mesh = new THREE.Mesh(geo, mat);
    three.scene.add(three.mesh);
    three.scene.background = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue("--stage").trim() || "#2b3237");
    const R = Math.max(p.W, p.H);
    if (!three.placed) { three.camera.position.set(-0.25 * R, -0.9 * R, 1.25 * R); three.placed = true; }
    three.camera.lookAt(0, 0, 0);
  }

  // ---------------------------------------------------------- trayectoria
  function drawPath(file) {
    const cv = $("cvPath"), g = cv.getContext("2d");
    const [W, H] = file.size;
    const s = Math.min(900 / W, 560 / H);
    cv.width = Math.round(W * s) + 20; cv.height = Math.round(H * s) + 20;
    g.fillStyle = "#1d2226"; g.fillRect(0, 0, cv.width, cv.height);
    const depth = num("depth");
    const lines = file.text.split("\r\n");
    const step = Math.max(1, Math.floor(lines.length / 400000));
    let x = 0, y = 0, z = 10, G = 0;
    g.lineWidth = 1;
    for (let k = 0; k < lines.length; k += 1) {
      const ln = lines[k];
      const m = ln.match(/([GXYZ])(-?[\d.]+)/g);
      if (!m) continue;
      let nx = x, ny = y, nz = z;
      for (const t of m) {
        const v = parseFloat(t.slice(1));
        if (t[0] === "G" && (v === 0 || v === 1)) G = v;
        else if (t[0] === "X") nx = v; else if (t[0] === "Y") ny = v; else if (t[0] === "Z") nz = v;
      }
      if (k % step === 0 && (nx !== x || ny !== y)) {
        if (G === 0 || nz > 0) g.strokeStyle = "rgba(160,160,160,.25)";
        else { const t = Math.min(1, -nz / depth); g.strokeStyle = `hsl(${40 - 30 * t}, ${60 + 20 * t}%, ${75 - 45 * t}%)`; }
        g.beginPath(); g.moveTo(10 + x * s, cv.height - 10 - y * s); g.lineTo(10 + nx * s, cv.height - 10 - ny * s); g.stroke();
      }
      x = nx; y = ny; z = nz;
    }
  }

  // ---------------------------------------------------------- generar
  let worker = null;
  function generate() {
    const p = params();
    const errs = check(p).filter((a) => a.bad);
    if (errs.length) { showAlerts(check(p)); return; }
    const w = Math.round(p.W / p.res), h = Math.round(p.H / p.res);
    const res = p.W / w;
    const lum = luminance(w, h);
    const job = Object.assign({}, p, { depth: p.depth });
    $("gen").disabled = true; $("prog").hidden = false; $("barI").style.width = "0%"; $("progMsg").textContent = "Preparando…";
    if (worker) worker.terminate();
    try { worker = new Worker("worker.js"); }
    catch (e) { worker = null; }
    const done = (files) => {
      $("gen").disabled = false; $("progMsg").textContent = "Listo";
      $("barI").style.width = "100%";
      lastFiles = files; showResults(files);
    };
    if (!worker) {           // sin worker: calcular aqui
      setTimeout(() => {
        const H = Krea.prepHeight(lum, w, h, res, job);
        done(Krea.generate({ H, w, h, res }, job, null));
      }, 30);
      return;
    }
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === "progress") { $("barI").style.width = (m.f * 100).toFixed(1) + "%"; $("progMsg").textContent = m.msg; }
      else if (m.type === "done") done(m.files);
      else if (m.type === "error") { $("gen").disabled = false; showAlerts([{ bad: true, t: "Error al calcular: " + m.msg }]); }
    };
    worker.onerror = () => {
      worker = null; $("progMsg").textContent = "Calculando en la página…";
      setTimeout(() => { const H = Krea.prepHeight(lum, w, h, res, job); done(Krea.generate({ H, w, h, res }, job, null)); }, 30);
    };
    worker.postMessage({ lum, w, h, res, p: job }, [lum.buffer]);
  }

  const fmtTime = (m) => { m = Math.max(1, Math.round(m)); return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`; };
  const fmtSize = (b) => b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.ceil(b / 1e3) + " KB";

  function save(name, blob) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  function showResults(files) {
    const box = $("results"); box.textContent = "";
    const t = document.createElement("table");
    t.innerHTML = "<thead><tr><th>Programa</th><th>Operación</th><th>Panel</th><th>Tamaño panel</th><th>Líneas</th><th>Tiempo aprox.</th><th>Archivo</th><th></th></tr></thead>";
    const tb = document.createElement("tbody");
    files.forEach((f, i) => {
      const tr = document.createElement("tr");
      const td = (txt, cls) => { const c = document.createElement("td"); c.textContent = txt; if (cls) c.className = cls; tr.appendChild(c); return c; };
      td(f.name);
      const op = td(""); const pill = document.createElement("span"); pill.className = "pill" + (f.op === "desbaste" ? " r" : ""); pill.textContent = f.op; op.appendChild(pill);
      td(f.tile || "—", "num");
      td(`${Math.round(f.size[0])} × ${Math.round(f.size[1])}`, "num");
      td(f.lines.toLocaleString("es"), "num");
      td(fmtTime(f.minutes), "num");
      td(fmtSize(f.text.length), "num");
      const act = td("");
      const v = document.createElement("button"); v.type = "button"; v.className = "btn ghost"; v.textContent = "Ver";
      v.onclick = () => { setTab("path"); drawPath(f); };
      const d = document.createElement("button"); d.type = "button"; d.className = "btn ghost"; d.textContent = "Descargar";
      d.onclick = () => save(f.name, new Blob([f.text], { type: "text/plain" }));
      act.style.display = "flex"; act.style.gap = "6px"; act.append(v, d);
      tb.appendChild(tr);
    });
    t.appendChild(tb); box.appendChild(t);
    const total = files.reduce((s, f) => s + f.minutes, 0);
    const foot = document.createElement("div"); foot.className = "go"; foot.style.padding = "10px 12px";
    const sum = document.createElement("span"); sum.className = "note"; sum.textContent = `${files.length} programas · tiempo total aprox. ${fmtTime(total)}`;
    foot.appendChild(sum);
    if (files.length > 1 && window.JSZip) {
      const z = document.createElement("button"); z.type = "button"; z.className = "btn ghost"; z.textContent = "Descargar todo (.zip)";
      z.onclick = async () => {
        const zip = new JSZip(); files.forEach((f) => zip.file(f.name, f.text));
        save(`${params().name}_nc.zip`, await zip.generateAsync({ type: "blob", compression: "DEFLATE" }));
      };
      foot.appendChild(z);
    }
    box.appendChild(foot);
    $("tabPath").disabled = false;
    setTab("path"); drawPath(files[files.length - 1]);
  }

  // ---------------------------------------------------------- pestañas y eventos
  function setTab(t) {
    $("tab2d").setAttribute("aria-selected", t === "2d"); $("tab3d").setAttribute("aria-selected", t === "3d");
    $("tabPath").setAttribute("aria-selected", t === "path");
    $("v2d").hidden = t !== "2d"; $("v3d").hidden = t !== "3d"; $("vPath").hidden = t !== "path";
    $("legend").hidden = t === "3d";
    if (t === "3d") draw3d();
  }
  $("tab2d").onclick = () => setTab("2d");
  $("tab3d").onclick = () => setTab("3d");
  $("tabPath").onclick = () => { setTab("path"); if (lastFiles.length) drawPath(lastFiles[lastFiles.length - 1]); };

  let tmr = 0;
  const later = () => { clearTimeout(tmr); tmr = setTimeout(refresh, 120); };
  $("form").addEventListener("input", (e) => {
    if (e.target.id === "W" && $("lock").checked) $("Hh").value = Math.round(num("W") / aspect);
    if (e.target.id === "Hh" && $("lock").checked) $("W").value = Math.round(num("Hh") * aspect);
    if (e.target.id === "file") return;
    later();
  });
  $("form").addEventListener("submit", (e) => e.preventDefault());
  ["roughOn", "finishOn"].forEach((id) => $(id).addEventListener("click", (e) => e.stopPropagation()));
  $("file").addEventListener("change", (e) => loadFile(e.target.files[0]));
  const drop = $("drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => loadFile(e.dataTransfer.files[0]));
  $("gen").onclick = generate;

  if (/claude\.ai|claudeusercontent|anthropic/.test(location.hostname)) $("sandboxNote").hidden = false;

  setSource(sampleImage(), "ejemplo");
})();
