// AMT PAS Generator — wizard front end
let SECTIONS = [];          // [{no,en,kind,optional}]
let ITEMS = [];             // [{file, name, size, section}]
let SESSION = null;
let lastSig = "";           // signature of files+sections at last session build

const $ = (id) => document.getElementById(id);

// ---- load the authoritative section list from the compiler ----
fetch("/api/template").then(r => r.json()).then(d => { SECTIONS = d.sections; });

// ---- stepper ----
function go(n) {
  if (n === 3 && !ITEMS.length) return;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  $("p" + n).classList.add("active");
  document.querySelectorAll(".step").forEach(s => {
    const i = +s.dataset.step;
    s.classList.toggle("active", i === n);
    s.classList.toggle("done", i < n);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (n === 3) startReview();
  if (n === 4) startGenerate();
}

// ---- file handling ----
function addFiles(fileList) {
  const names = [];
  const incoming = [];
  for (const f of fileList) {
    if (f.name.startsWith("~$") || f.name.endsWith(":Zone.Identifier")) continue;
    incoming.push(f);
    names.push(f.name);
  }
  if (!incoming.length) return;
  fetch("/api/classify", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names })
  }).then(r => r.json()).then(d => {
    d.suggestions.forEach((s, i) => {
      ITEMS.push({ file: incoming[i], name: s.name, size: incoming[i].size,
                   section: s.section, confident: s.confident, reason: s.reason });
    });
    renderFiles();
  });
}

$("files").addEventListener("change", e => addFiles(e.target.files));
$("folder").addEventListener("change", e => addFiles(e.target.files));

const drop = document.querySelector(".drop");
["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.style.borderColor = "var(--amt-red)";
}));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.style.borderColor = "";
}));
drop.addEventListener("drop", e => { if (e.dataTransfer.files) addFiles(e.dataTransfer.files); });

function humanSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(0) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function renderFiles() {
  const box = $("filelist");
  box.innerHTML = "";
  ITEMS.forEach((it, idx) => {
    const row = document.createElement("div");
    row.className = "filerow";
    const opts = SECTIONS.map(s =>
      `<option value="${s.no}" ${s.no === it.section ? "selected" : ""}>${s.no}. ${escapeHtml(s.en)}${s.optional ? " (optional)" : ""}</option>`
    ).join("");
    const nm = escapeHtml(it.name), reason = escapeHtml(it.reason);
    row.innerHTML = `
      <div class="nm" title="${nm}">${nm}${it.confident ? "" : `<span class="badge guess" title="${reason}">guess</span>`}</div>
      <div class="sz">${humanSize(it.size)}</div>
      <select data-i="${idx}">${opts}</select>
      <button class="x" data-rm="${idx}" title="remove">✕</button>`;
    box.appendChild(row);
  });
  box.querySelectorAll("select").forEach(sel =>
    sel.addEventListener("change", e => { ITEMS[+e.target.dataset.i].section = +e.target.value; renderCoverage(); }));
  box.querySelectorAll("[data-rm]").forEach(btn =>
    btn.addEventListener("click", e => { ITEMS.splice(+e.target.dataset.rm, 1); renderFiles(); }));
  renderCoverage();
}

function renderCoverage() {
  const cov = $("coverage");
  cov.innerHTML = "";
  const counts = {};
  ITEMS.forEach(it => counts[it.section] = (counts[it.section] || 0) + 1);
  SECTIONS.forEach(s => {
    const n = counts[s.no] || 0;
    const chip = document.createElement("span");
    let cls = "chip";
    if (n > 0) cls += " ok";
    else if (!s.optional) cls += " miss";
    else cls += " opt";
    chip.className = cls;
    chip.textContent = `§${s.no} ${s.en}: ${n || (s.optional ? "—" : "missing")}`;
    cov.appendChild(chip);
  });
  const requiredMissing = SECTIONS.some(s => !s.optional && !(counts[s.no] > 0));
  $("toReview").disabled = !ITEMS.length || requiredMissing;
}

// ---- collect config from step 1 ----
function buildConfig() {
  const v = id => ($(id).value || "").trim();
  let date = v("date");
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    const m = ["January","February","March","April","May","June","July",
               "August","September","October","November","December"];
    const [y, mo, d] = date.split("-");
    date = `${d}-${m[+mo - 1]}-${y}`;
  }
  return {
    ref_no: v("ref_no"), version: v("version") || "00", mts_ref_no: v("mts_ref_no"),
    date, project_title_en: v("project_title_en"), project_title_ar: v("project_title_ar"),
    company_name_ar: v("company_name_ar"), client: v("client"), building: v("building"),
    prepared_by: { role_en: v("prep_role"), initials: v("prep_init") },
    checked_by: { role_en: v("chk_role"), initials: v("chk_init") },
    approved_by: { role_en: v("app_role"), initials: v("app_init") },
    revision: { author: v("rev_author"), remarks: v("rev_remarks") || "Issued for approval" },
  };
}

// ---- step 3: build session + validate ----
function sig() { return ITEMS.map(i => i.name + ":" + i.section).join("|") + "::" + JSON.stringify(buildConfig()); }

async function ensureSession() {
  const current = sig();
  if (SESSION && current === lastSig) return SESSION;
  const fd = new FormData();
  fd.append("config", JSON.stringify(buildConfig()));
  ITEMS.forEach(it => { fd.append("files", it.file, it.name); fd.append("sections", it.section); });
  const r = await fetch("/api/session", { method: "POST", body: fd });
  if (!r.ok) throw new Error("upload failed (" + r.status + ")");
  const d = await r.json();
  SESSION = d.session; lastSig = current;
  return SESSION;
}

async function startReview() {
  const box = $("reviewBox");
  box.innerHTML = '<div class="spinner"></div>';
  $("toGen").disabled = true;
  try {
    const sid = await ensureSession();
    const r = await fetch(`/api/session/${sid}/validate`);
    const d = await r.json();
    let html = `<pre class="report">${escapeHtml(d.report)}</pre>`;
    if (d.errors && d.errors.length)
      html += `<div class="note err"><strong>Cannot generate yet:</strong><br>${d.errors.map(escapeHtml).join("<br>")}</div>`;
    if (d.warnings && d.warnings.length)
      html += `<div class="note warn">${d.warnings.map(escapeHtml).join("<br>")}</div>`;
    if (!d.errors || !d.errors.length)
      html += `<div class="note ok">All required sections present. Ready to generate.</div>`;
    box.innerHTML = html;
    $("toGen").disabled = !!(d.errors && d.errors.length);
  } catch (e) {
    box.innerHTML = `<div class="note err">${escapeHtml(e.message)}</div>`;
  }
}

// ---- step 4: compile + download ----
async function startGenerate() {
  const box = $("genBox");
  box.innerHTML = '<div class="spinner"></div><p class="center">Compiling… this can take a moment for large datasheets.</p>';
  try {
    const sid = await ensureSession();
    const r = await fetch(`/api/session/${sid}/compile`, { method: "POST" });
    const d = await r.json();
    if (!d.ok) {
      const msg = d.error || (d.errors || d.config_errors || ["Generation failed"]).join("<br>");
      box.innerHTML = `<div class="note err"><strong>Generation failed:</strong><br>${escapeHtml(msg)}</div>`;
      return;
    }
    const qa = d.qa;
    const engineNote = qa.engines.some(e => e.startsWith("reportlab"))
      ? `<div class="note warn">Rendered with the reportlab fallback (LibreOffice not installed on the server).
         Tables are readable but not pixel-faithful — install LibreOffice for best fidelity.</div>` : "";
    box.innerHTML = `
      <div class="note ok"><strong>Done.</strong> Your submittal PDF is ready.</div>
      <div class="qa">
        <div class="card"><div class="k">Pages</div><div class="v">${qa.pages}</div></div>
        <div class="card"><div class="k">Consistency</div><div class="v">${qa.consistent ? "OK" : "Check"}</div></div>
        <div class="card"><div class="k">Engine</div><div class="v" style="font-size:15px">${qa.engines.join(", ")}</div></div>
      </div>
      ${engineNote}
      <p class="center"><a class="btn primary lg" href="${d.download}">⬇ Download submittal PDF</a></p>`;
  } catch (e) {
    box.innerHTML = `<div class="note err">${escapeHtml(e.message)}</div>`;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
