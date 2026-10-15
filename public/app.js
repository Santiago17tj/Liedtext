"use strict";
const $ = (id) => document.getElementById(id);
const CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZñÑáéíóúÁÉÍÓÚüÜ0123456789.,;:¿?¡!()-\"'/%+=°&@";
const LOWER = "abcdefghijklmnopqrstuvwxyz";
const READY_MIN_LOWER = 20;           // letras minúsculas mínimas para poder escribir
const SIZE_DEFAULT = { rayado: 3.0, cuadriculado: 2.3, blanco: 3.2 };
const STORE_KEY = "lc.v1";
const SAMPLE = "# Taller de categorización\n\nLa categorización permite organizar la información y relacionarla con conocimientos previos.\n- Primer punto: clasificar los estímulos.\n- Segundo punto: justificar la respuesta.\n\n¿Qué conducta es aprendida? Explícalo en dos o tres líneas.";

// ---- utilidades -------------------------------------------------------------
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); for (const k of kids) e.append(k); return e; };
const notice = (box, text, kind = "info") => box.appendChild(el("div", { className: "notice " + kind, textContent: text }));
const clear = (box) => { box.replaceChildren(); };
const radio = (name) => document.querySelector(`input[name=${name}]:checked`).value;

// ---- almacenamiento local (solo en este dispositivo) ------------------------------
let store = { current: null, profiles: {} };
let storeOk = true;
function loadStore() {
  try { const s = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); if (s && s.profiles) store = s; } catch { storeOk = false; }
}
function saveStore() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); return true; }
  catch { storeOk = false; return false; }
}
const profile = () => store.profiles[store.current] || null;
const newId = () => Math.random().toString(36).slice(2, 10);

function coverage(p) {
  const have = new Set(p.glyphs.map((g) => g.char));
  const lower = [...LOWER].filter((c) => have.has(c)).length;
  return { total: have.size, lower, ready: lower >= READY_MIN_LOWER, missing: [...CHARSET].filter((c) => !have.has(c)) };
}

// ---- diálogos propios (sin ventanas del navegador) ---------------------------------
function dialog({ title, body, ok = "Aceptar", cancel = "Cancelar", input = null }) {
  return new Promise((resolve) => {
    const dlg = $("dlg");
    $("dlgTitle").textContent = title;
    const bodyBox = $("dlgBody"); clear(bodyBox);
    if (body) bodyBox.appendChild(el("p", { textContent: body }));
    let field = null;
    if (input) { field = el("input", { type: input.type || "text", id: "dlgInput", autocomplete: "off", style: "margin-top:12px" }); bodyBox.appendChild(field); }
    const btns = $("dlgBtns"); clear(btns);
    let value = null;
    if (cancel) btns.appendChild(el("button", { type: "button", textContent: cancel, onclick: () => dlg.close() }));
    btns.appendChild(el("button", { type: "submit", className: "primary", textContent: ok, onclick: () => { value = field ? field.value : true; } }));
    dlg.onclose = () => resolve(value);
    dlg.showModal();
    if (field) field.focus();
  });
}

// ---- llamadas al servidor --------------------------------------------------
async function askPassword(wrong) {
  return dialog({ title: "Contraseña", body: wrong ? "Esa contraseña no es correcta. Inténtalo otra vez." : "Esta página está protegida. Escribe la contraseña para continuar.",
                  ok: "Entrar", input: { type: "password" } });
}
async function api(path, opts, retried = false) {
  const r = await fetch(path, opts);
  const isJson = (r.headers.get("content-type") || "").includes("json");
  const body = isJson ? await r.json() : null;
  if (r.status === 401 && body && body.login && !retried) {
    let wrong = false;
    for (;;) {
      const pw = await askPassword(wrong);
      if (pw === null) throw new Error("Necesitas la contraseña para continuar.");
      const lr = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: pw }) });
      if (lr.ok) break;
      wrong = true;
    }
    return api(path, opts, true);
  }
  if (!r.ok) throw new Error((body && body.error) || (r.status >= 500 ? "El servidor tuvo un problema. Inténtalo de nuevo en un momento." : "Algo salió mal (" + r.status + ")."));
  return body;
}
const postJson = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ---- navegación entre pantallas -------------------------------------------
let step = 1;
function go(n, focus = true) {
  if (n >= 2 && !profile()) n = 1;
  if (n === 4 && !(profile() && coverage(profile()).ready)) n = 3;
  step = n;
  for (let i = 1; i <= 4; i++) $("s" + i).hidden = i !== n;
  [...$("progress").children].forEach((li, i) => {
    li.classList.toggle("now", i + 1 === n); li.classList.toggle("done", i + 1 < n);
    li.toggleAttribute("aria-current", i + 1 === n);
  });
  if (focus) { $("h" + n).focus({ preventScroll: true }); window.scrollTo({ top: 0 }); }
  try { sessionStorage.setItem("lc.step", String(n)); } catch { /* sin almacenamiento de sesión */ }
  render();
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-go]"); if (b && !b.disabled) go(Number(b.dataset.go)); });

// ---- pantalla 1: mi letra ---------------------------------------------------
function renderProfiles() {
  const list = Object.values(store.profiles);
  $("saved").hidden = !list.length;
  const cards = $("cards"); clear(cards);
  for (const p of list) {
    const c = coverage(p);
    const sub = !p.sheets.length ? "Aún sin hojas" : c.ready ? `Lista para escribir · ${p.sheets.length} hoja(s)` : `Faltan letras · ${p.sheets.length} hoja(s)`;
    cards.appendChild(el("div", { className: "card" + (p.id === store.current ? " sel" : "") },
      el("div", {}, el("div", { className: "nm", textContent: p.name }), el("div", { className: "sub", textContent: sub })),
      el("div", { className: "row" },
        el("button", { type: "button", className: "primary", textContent: "Usar esta letra", onclick: () => { store.current = p.id; saveStore(); go(c.ready ? 4 : p.sheets.length ? 3 : 2); } }),
        el("button", { type: "button", className: "link danger", textContent: "Borrar", onclick: () => removeProfile(p) }))));
  }
}
async function removeProfile(p) {
  const ok = await dialog({ title: "¿Borrar esta letra?", body: `Se borrará «${p.name}» de este dispositivo. Si no guardaste una copia en un archivo, tendrás que volver a subir las fotos.`, ok: "Sí, borrar" });
  if (!ok) return;
  delete store.profiles[p.id];
  if (store.current === p.id) store.current = Object.keys(store.profiles)[0] || null;
  saveStore(); render();
}
$("createBtn").addEventListener("click", () => {
  const msg = $("nameMsg"); clear(msg);
  const name = $("newName").value.trim();
  if (!name) { notice(msg, "Escribe un nombre para empezar. Ejemplo: Ana.", "warn"); $("newName").focus(); return; }
  const id = newId();
  store.profiles[id] = { id, name, ink_rgb: null, sheets: [], glyphs: [] };
  store.current = id; saveStore();
  $("newName").value = "";
  go(2);
});
$("newName").addEventListener("keydown", (e) => { if (e.key === "Enter") $("createBtn").click(); });

$("exportBtn").addEventListener("click", async () => {
  const p = profile();
  if (!p) { await dialog({ title: "Todavía no hay nada que guardar", body: "Primero crea una letra y sube las fotos de tus hojas.", ok: "Entendido", cancel: null }); return; }
  const blob = new Blob([JSON.stringify({ app: "letracrack", v: 1, ...p })], { type: "application/json" });
  const a = el("a", { href: URL.createObjectURL(blob), download: p.name.replace(/[^\w\-]+/g, "_") + ".letracrack.json" });
  document.body.appendChild(a); a.click(); a.remove();
});
$("importBtn").addEventListener("click", () => $("importFile").click());
$("importFile").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  try {
    const d = JSON.parse(await f.text());
    if (d.app !== "letracrack" || !Array.isArray(d.glyphs) || !Array.isArray(d.sheets)) throw new Error("x");
    const id = newId();
    store.profiles[id] = { id, name: String(d.name || "Letra importada").slice(0, 40), ink_rgb: d.ink_rgb || null, sheets: d.sheets, glyphs: d.glyphs };
    store.current = id; saveStore(); render();
    await dialog({ title: "Listo", body: "Tu letra se abrió correctamente.", ok: "Seguir", cancel: null });
    go(coverage(store.profiles[id]).ready ? 4 : 3);
  } catch { await dialog({ title: "No pude abrir ese archivo", body: "Debe ser un archivo de letra guardado con este programa (termina en .letracrack.json).", ok: "Entendido", cancel: null }); }
});

// ---- pantalla 3: fotos ------------------------------------------------------
let queue = [];  // [{file, state: 'pend'|'work'|'ok'|'bad', text}]
function addFiles(files) {
  for (const f of files) if (f.type.startsWith("image/")) queue.push({ file: f, state: "pend", text: "Esperando", url: URL.createObjectURL(f) });
  clear($("scanMsg")); renderQueue();
}
function renderQueue() {
  const box = $("thumbs"); clear(box);
  for (const q of queue) {
    box.appendChild(el("div", { className: "thumb " + (q.state === "ok" ? "ok" : q.state === "bad" ? "bad" : "") },
      el("img", { src: q.url, alt: "" }),
      el("div", {}, el("div", { textContent: q.file.name, style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600" }),
        el("div", { className: "st", textContent: q.state === "work" ? "Revisando…" : q.text }))));
  }
  const pending = queue.some((q) => q.state === "pend");
  $("scanBtn").disabled = !pending || !profile();
  $("clearBtn").hidden = !queue.length;
}
$("camBtn").addEventListener("click", () => $("camFile").click());
$("galBtn").addEventListener("click", () => $("galFile").click());
for (const id of ["camFile", "galFile"]) $(id).addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
$("clearBtn").addEventListener("click", () => { queue = []; clear($("scanMsg")); renderQueue(); });
for (const b of [$("galBtn")]) {
  b.addEventListener("dragover", (e) => { e.preventDefault(); b.classList.add("over"); });
  b.addEventListener("dragleave", () => b.classList.remove("over"));
  b.addEventListener("drop", (e) => { e.preventDefault(); b.classList.remove("over"); addFiles(e.dataTransfer.files); });
}

// reduce fotos de celular muy grandes antes de subirlas (más rápido y sin pasar límites)
async function shrink(file) {
  if (file.size < 3 * 1024 * 1024) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, 3200 / Math.max(bmp.width, bmp.height));
    const c = el("canvas", { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.92));
    return blob || file;
  } catch { return file; }
}

function friendlyScanError(msg) {
  if (/marcas/i.test(msg)) return "No pude ver los 4 cuadrados negros de las esquinas. Toma la foto de nuevo con la hoja completa y buena luz.";
  if (/ninguna escritura|no encontré escritura/i.test(msg)) return "Esa hoja parece estar vacía. ¿Es la hoja de práctica ya escrita?";
  return msg;
}

$("scanBtn").addEventListener("click", async () => {
  const p = profile(); if (!p) return;
  const msg = $("scanMsg"); clear(msg);
  $("scanBtn").disabled = true;
  let good = 0, bad = 0;
  for (const q of queue) {
    if (q.state !== "pend") continue;
    q.state = "work"; renderQueue();
    try {
      const fd = new FormData(); fd.append("file", await shrink(q.file), "hoja.jpg");
      const r = await api("/api/scan", { method: "POST", body: fd });
      if (p.sheets.some((s) => s.sha1 === r.sha1)) { q.state = "bad"; q.text = "Esta foto ya estaba agregada."; bad++; continue; }
      const counts = {};
      for (const g of p.glyphs) counts[g.char] = (counts[g.char] || 0) + 1;
      for (const g of r.glyphs) { p.glyphs.push({ char: g.char, variant: counts[g.char] || 0, bottom_offset: g.bottom_offset, w: g.w, h: g.h, png: g.png }); counts[g.char] = (counts[g.char] || 0) + 1; }
      if (r.ink_rgb) { const n = p.sheets.length; p.ink_rgb = p.ink_rgb ? p.ink_rgb.map((v, i) => Math.round((v * n + r.ink_rgb[i]) / (n + 1))) : r.ink_rgb; }
      p.sheets.push({ sha1: r.sha1, found: r.found });
      q.state = "ok"; q.text = `✓ Aprendí ${r.found} letras de esta hoja`; good++;
      if (r.warnings && r.warnings.length) notice(msg, r.warnings.join(" "), "warn");
    } catch (e) { q.state = "bad"; q.text = friendlyScanError(e.message); bad++; }
    renderQueue();
  }
  if (!saveStore()) notice(msg, "No pude guardar tu letra en este navegador (¿está en modo privado?). Usa «Guardar mi letra en un archivo» para no perderla.", "warn");
  if (good) notice(msg, bad ? `${good} foto(s) revisada(s) bien y ${bad} con problemas (mira cada foto).` : "¡Muy bien! Las fotos se revisaron correctamente.", bad ? "warn" : "ok");
  else if (bad) notice(msg, "Ninguna foto sirvió. Lee el mensaje de cada foto y vuelve a intentarlo.", "bad");
  render();
});

function renderLearned() {
  const p = profile(); const box = $("learned");
  box.hidden = !p || !p.sheets.length;
  $("toWrite").disabled = !p || !coverage(p).ready;
  if (box.hidden) return;
  const c = coverage(p);
  $("learnedTitle").textContent = `Letras aprendidas: ${c.total} de ${CHARSET.length}`;
  $("meterBar").style.width = Math.round((100 * c.total) / CHARSET.length) + "%";
  const m = $("learnedMsg"); clear(m);
  if (!c.ready) notice(m, `Todavía faltan letras minúsculas (${c.lower} de 26). Sube las fotos de las 3 hojas.`, "warn");
  else if (c.missing.length) notice(m, `Ya puedes escribir. No aprendí: ${c.missing.join(" ")} (si tu texto las usa, se saltarán o se cambiarán por parecidas). Puedes subir otra hoja con esos cuadros bien llenos.`, "info");
  else notice(m, "¡Todo listo! Aprendí todas las letras. Puedes seguir.", "ok");
  if (p.sheets.length < 3) notice(m, `Subiste ${p.sheets.length} hoja(s). Con 3 hojas el resultado se ve más natural.`, "info");
  const g = $("glyphs"); clear(g);
  const k = 0.5;
  for (const ch of CHARSET) {
    const vs = p.glyphs.filter((x) => x.char === ch);
    if (!vs.length) continue;
    const cell = el("div", { className: "gl" }, el("b", { textContent: ch }));
    for (const v of vs.slice(0, 3)) cell.appendChild(el("img", { src: "data:image/png;base64," + v.png, alt: "", style: `height:${v.h * k}px;top:${v.bottom_offset * k}px` }));
    g.appendChild(cell);
  }
}
$("resetBtn").addEventListener("click", async () => {
  const p = profile(); if (!p) return;
  if (!await dialog({ title: "¿Empezar de nuevo?", body: "Se borrarán las letras aprendidas de esta persona y tendrás que subir las fotos otra vez.", ok: "Sí, borrar" })) return;
  p.glyphs = []; p.sheets = []; p.ink_rgb = null; saveStore(); queue = []; clear($("scanMsg")); render();
});

// ---- pantalla 4: escribir -----------------------------------------------------
$("sampleBtn").addEventListener("click", () => { $("text").value = SAMPLE; $("text").focus(); });

function buildPdf(pages) {
  const enc = new TextEncoder(); const chunks = []; let len = 0; const offs = [];
  const add = (s) => { const b = typeof s === "string" ? enc.encode(s) : s; chunks.push(b); len += b.length; };
  const obj = (n, body) => { offs[n] = len; add(`${n} 0 obj\n${body}\nendobj\n`); };
  add("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, `<< /Type /Pages /Kids [${pages.map((_, i) => `${3 + 3 * i} 0 R`).join(" ")}] /Count ${pages.length} >>`);
  pages.forEach((p, i) => {
    const pg = 3 + 3 * i, ct = pg + 1, im = pg + 2;
    obj(pg, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /XObject << /Im0 ${im} 0 R >> >> /Contents ${ct} 0 R >>`);
    const c = "q 595.28 0 0 841.89 0 0 cm /Im0 Do Q";
    obj(ct, `<< /Length ${c.length} >>\nstream\n${c}\nendstream`);
    offs[im] = len;
    add(`${im} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${p.w} /Height ${p.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.bytes.length} >>\nstream\n`);
    add(p.bytes); add("\nendstream\nendobj\n");
  });
  const total = 3 + 3 * pages.length, xref = len;
  let x = `xref\n0 ${total}\n0000000000 65535 f \n`;
  for (let i = 1; i < total; i++) x += String(offs[i]).padStart(10, "0") + " 00000 n \n";
  add(x + `trailer\n<< /Size ${total} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(chunks, { type: "application/pdf" });
}
const b64ToBytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
function download(blob, name) {
  const a = el("a", { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

let generating = false;
$("genBtn").addEventListener("click", async () => {
  if (generating) return;
  const p = profile(); const msg = $("genMsg"); clear(msg);
  const text = $("text").value;
  if (!text.trim()) { notice(msg, "Escribe o pega primero el texto que quieres pasar a mano.", "warn"); $("text").focus(); return; }
  if (!p || !coverage(p).ready) { notice(msg, "Aún faltan letras por aprender. Vuelve al paso de las fotos.", "warn"); return; }
  generating = true;
  const btn = $("genBtn"); btn.disabled = true; btn.replaceChildren(el("i", { className: "spin" }), " Escribiendo…");
  $("result").hidden = true; clear($("pages")); clear($("downloads"));
  const paper = radio("paper");
  const base = {
    profile: { ink_rgb: p.ink_rgb, glyphs: p.glyphs.map(({ char, bottom_offset, png }) => ({ char, bottom_offset, png })) },
    text, paper, size_mm: SIZE_DEFAULT[paper] * Number(radio("size")), spacing: radio("space"),
    naturalness: radio("nat"), ink: radio("ink"), seed: Math.floor(Math.random() * 2 ** 31),
  };
  const done = []; let total = 1, report = null;
  try {
    for (let i = 0; i < total; i++) {
      clear(msg); notice(msg, total > 1 ? `Escribiendo la página ${i + 1} de ${total}…` : "Escribiendo…", "info");
      const r = await postJson("/api/render", { ...base, page: i });
      total = r.total; report = report || r.report;
      done.push({ bytes: b64ToBytes(r.jpeg), w: r.width, h: r.height });
      $("result").hidden = false;
      $("pages").appendChild(el("img", { src: "data:image/jpeg;base64," + r.jpeg, alt: `Página ${i + 1} escrita con tu letra` }));
    }
    clear(msg);
    notice(msg, total === 1 ? "¡Listo! Tu hoja está lista." : `¡Listo! Son ${total} páginas.`, "ok");
    if (report.missing.length) notice(msg, `Estos signos no los aprendí y no se escribieron: ${report.missing.join(" ")}`, "warn");
    const dl = $("downloads");
    dl.appendChild(el("button", { type: "button", className: "primary big", textContent: "⬇ Descargar en PDF", onclick: () => download(buildPdf(done), "mi-letra.pdf") }));
    done.forEach((d, i) => dl.appendChild(el("button", { type: "button", textContent: `Imagen de la página ${i + 1}`, onclick: () => download(new Blob([d.bytes], { type: "image/jpeg" }), `pagina-${i + 1}.jpg`) })));
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    clear(msg); notice(msg, e.message, "bad");
  }
  generating = false; btn.disabled = false; btn.textContent = "✍️ Pasar a mano";
});

// ---- ayuda y arranque ------------------------------------------------------------
$("helpBtn").addEventListener("click", () => $("help").showModal());
$("helpClose").addEventListener("click", () => $("help").close());

function render() { renderProfiles(); renderQueue(); renderLearned(); }

loadStore();
if (!storeOk) notice($("nameMsg"), "Este navegador no deja guardar datos. Podrás usar el programa, pero guarda tu letra en un archivo al terminar.", "warn");
let start = 1;
try { start = Number(sessionStorage.getItem("lc.step")) || 1; } catch { /* nada */ }
if (!start || !profile()) start = profile() ? (coverage(profile()).ready ? 4 : 2) : 1;
go(start, false);
