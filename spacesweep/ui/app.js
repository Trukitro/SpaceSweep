"use strict";

/* ================================================================ basics */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ESC[c]);
const icon = (name, cls = "ic") => `<svg class="${cls}"><use href="#i-${name}"/></svg>`;

const S = {
  info: null, lang: "es", theme: "system", drives: [], page: "home",
  cl: { drive: null, result: null, sel: new Set(), open: new Set(), report: null, busy: false },
  ex: { root: null, summary: null, rel: "", node: null, tab: "folders" },
  dl: { folder: null, res: null, sel: new Set(), sizes: new Map(), perm: false, undo: null, list: false },
  fo: { key: "documents", folder: null, res: null, sel: new Set(), sizes: new Map(), perm: false, media: null, undo: null },
  du: { folders: [], min: "1", res: null, sel: new Set(), sizes: new Map(), keep: "oldest", shown: 60, perm: false, refOn: false, ref: [] },
};

/* i18n: static strings are trusted; interpolated values are escaped. */
function t(key, vars) {
  const get = lang => key.split(".").reduce((o, k) => (o ? o[k] : undefined), I18N[lang]);
  let s = get(S.lang) ?? get("es") ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => esc(vars[k] ?? ""));
  return s;
}
const L = obj => esc(obj ? (obj[S.lang] ?? obj.es ?? "") : "");

function size(b) {
  if (b == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let n = b, i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(n < 10 ? 2 : n < 100 ? 1 : 0)) + " " + u[i];
}
const num = n => Number(n || 0).toLocaleString(S.lang === "es" ? "es-PR" : "en-US");
const date = sec => new Date(sec * 1000).toLocaleDateString(S.lang === "es" ? "es-PR" : "en-US", { year: "numeric", month: "short", day: "numeric" });
const base = p => p.split(/[\\/]/).filter(Boolean).pop() || p;
/* Show paths shorter and without the user name: C:\Users\me\AppData -> ~\AppData */
const pp = p => {
  const home = S.info && S.info.home;
  return home && p && p.toLowerCase().startsWith(home.toLowerCase()) ? "~" + p.slice(home.length) : p;
};
const rel = (p, root) => (root && p.toLowerCase().startsWith(root.toLowerCase()) ? p.slice(root.length).replace(/^[\\/]/, "") : p) || p;

/* ================================================================ backend bridge */
const TOKEN = $('meta[name="ss-token"]').content;
const NATIVE = TOKEN === "__SS_TOKEN__";

async function api(name, ...args) {
  if (NATIVE) return window.pywebview.api[name](...args);
  const r = await fetch("/api/" + name, {
    method: "POST", headers: { "Content-Type": "application/json", "X-SS-Token": TOKEN }, body: JSON.stringify(args),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || r.status);
  return j.result;
}

/* Run a background job, showing progress in `box`. Resolves with the result, or null if cancelled. */
async function runJob(start, box, label) {
  const id = await start;
  box.classList.remove("hidden");
  box.innerHTML = `<div class="spinner"></div><div class="grow"><div class="msg"></div><div class="cur"></div>
    <div class="bar indet"><i></i></div></div><button class="btn sm" data-cancel>${t("common.cancel")}</button>`;
  box.querySelector("[data-cancel]").onclick = () => api("cancel", id);
  try {
    for (;;) {
      const s = await api("job", id);
      if (!s) throw new Error("job lost");
      const msg = typeof label === "function" ? label(s) : label;
      box.querySelector(".msg").textContent = msg + (s.count ? ` · ${num(s.count)} ${I18N[S.lang].common.files}` : "");
      box.querySelector(".cur").textContent = s.current || "";
      const bar = box.querySelector(".bar");
      bar.classList.toggle("indet", !(s.progress >= 0));
      bar.firstElementChild.style.width = s.progress >= 0 ? Math.round(s.progress * 100) + "%" : "";
      if (s.status === "done") return s.result;
      if (s.status === "cancelled") { toast(t("common.cancelled")); return null; }
      if (s.status === "error") throw new Error(s.error);
      await sleep(250);
    }
  } finally {
    box.classList.add("hidden");
    box.innerHTML = "";
  }
}

/* ================================================================ UI helpers */
function toast(msg, err = false) {
  const el = document.createElement("div");
  el.className = "toast" + (err ? " err" : "");
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), err ? 7000 : 4000);
}
const fail = e => { console.error(e); toast(`${t("common.error")}: ${e.message || e}`, true); };

function modal({ title, body = "", ok = t("common.confirm"), okClass = "primary", cancel = true, input = null }) {
  return new Promise(resolve => {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><header>${title}</header><div class="body">${body}
      ${input !== null ? `<input type="text" class="mono" style="width:100%" value="${esc(input)}">` : ""}</div>
      <footer>${cancel ? `<button class="btn" data-no>${t("common.cancel")}</button>` : ""}<button class="btn ${okClass}" data-yes>${ok}</button></footer></div>`;
    document.body.appendChild(back);
    const field = back.querySelector("input");
    const done = v => { back.remove(); document.removeEventListener("keydown", key); resolve(v); };
    const key = e => { if (e.key === "Escape") done(input !== null ? null : false); if (e.key === "Enter" && field) done(field.value.trim()); };
    document.addEventListener("keydown", key);
    back.querySelector("[data-yes]").onclick = () => done(field ? field.value.trim() : true);
    const no = back.querySelector("[data-no]");
    if (no) no.onclick = () => done(input !== null ? null : false);
    (field || back.querySelector("[data-yes]")).focus();
  });
}

async function pickFolder(start) {
  if (S.info.native) return api("pick_folder", start || null);
  const p = await modal({ title: t("common.other"), body: `<p class="muted">${t("common.type_path")}</p>`, input: start || "" });
  if (!p) return null;
  if (!(await api("path_exists", p))) { toast(`${t("common.error")}: ${p}`, true); return null; }
  return p;
}

const head = (title, sub, right = "") => `<div class="page-head"><div><h1>${title}</h1><p>${sub}</p></div>${right}</div>`;
const stat = (k, v, cls = "", ic = "") => `<div class="stat ${cls}"><div class="k">${ic ? icon(ic) : ""}${k}</div><div class="v">${v}</div></div>`;
const empty = (msg, ic = "check") => `<div class="empty">${icon(ic)}<div>${msg}</div></div>`;
const openBtn = p => `<button class="icon-btn" title="${esc(I18N[S.lang].common.open)}" data-act="open" data-path="${esc(p)}">${icon("open")}</button>`;
const trashBtn = (p, scope) => `<button class="icon-btn" title="${esc(I18N[S.lang].common.recycle)}" data-act="del-one" data-scope="${scope}" data-path="${esc(p)}">${icon("trash")}</button>`;
const CAT_COLORS = { installers: "#f59e0b", archives: "#a855f7", diskimages: "#64748b", documents: "#3b82f6", images: "#10b981", videos: "#ef4444",
  audio: "#ec4899", code: "#06b6d4", fonts: "#84cc16", torrents: "#f97316", backups: "#eab308", other: "#94a3b8", dev: "#8b5cf6" };
const RULE_ICONS = { temp: "clock", gpu: "chip", driver: "package", update: "refresh", bug: "bug", image: "image", globe: "globe", app: "app",
  code: "code", trash: "trash", game: "game", phone: "phone", download: "download", music: "music", disk: "disk", brain: "brain",
  windows: "windows", memory: "memory", moon: "moon", history: "history", shield: "shield" };
const appName = exe => exe.replace(/\.exe$/i, "").replace(/^./, c => c.toUpperCase());

/* ---------- selection bars (Downloads, My folders, Duplicates share them) */
function selectionBar(scope) {
  const st = S[scope];
  let bytes = 0;
  st.sel.forEach(p => { bytes += st.sizes.get(p) || 0; });
  return `<span class="grow"><b>${num(st.sel.size)}</b> · ${size(bytes)}</span>
    <label class="row small muted"><input type="checkbox" data-perm="${scope}" ${st.perm ? "checked" : ""}> ${t("common.permanent")}</label>
    <button class="btn ${st.perm ? "danger" : "primary"}" data-act="del-sel" data-scope="${scope}" ${st.sel.size ? "" : "disabled"}>${icon("trash")}${st.perm ? t("common.delete_perm") : t("common.recycle")}</button>`;
}
function refreshBar(scope) {
  const bar = $(`#${scope}Bar`);
  if (bar) bar.innerHTML = (BARS[scope] || selectionBar)(scope);
}
const checkbox = (scope, p, extra = "") => `<input type="checkbox" data-sel="${scope}" data-path="${esc(p)}" ${S[scope].sel.has(p) ? "checked" : ""} ${extra}>`;

async function deletePaths(scope, paths, box) {
  const st = S[scope] || { perm: false };
  const perm = !!st.perm;
  const list = paths.slice(0, 12).map(p => `<li class="path">${esc(p)}</li>`).join("") +
    (paths.length > 12 ? `<li class="muted">${t("explorer.more", { n: num(paths.length - 12) })}</li>` : "");
  const ok = await modal({
    title: `${perm ? t("common.delete_perm") : t("common.recycle")} — ${num(paths.length)}`,
    body: `<ul>${list}</ul><div class="note ${perm ? "warn" : ""}">${icon(perm ? "alert" : "infoc")}<div>${perm ? t("common.perm_note") : t("common.recycle_note")}</div></div>`,
    ok: perm ? t("common.delete_perm") : t("common.recycle"), okClass: perm ? "danger" : "primary",
  });
  if (!ok) return null;
  const res = await runJob(api("delete", paths, perm), box, t("common.deleting"));
  if (!res) return null;
  const gone = new Set(res.results.filter(r => r.ok).map(r => r.path));
  if (res.ok) toast(t(perm ? "common.deleted_ok" : "common.recycled_ok", { n: num(res.ok), size: size(res.freed) }));
  const failed = res.results.length - res.ok;
  if (failed) toast(t("common.failed", { n: failed }), true);
  if (S[scope]) gone.forEach(p => { S[scope].sel.delete(p); });
  loadDrives();
  return gone;
}

/* ================================================================ shell */
function applyStatic() {
  $$("[data-t]").forEach(el => { el.innerHTML = t(el.dataset.t); });
  $("#version").textContent = `v${S.info.version}`;
  document.documentElement.lang = S.lang;
  $("#adminPill").classList.toggle("on", S.info.admin);
  $("#adminText").textContent = S.info.admin ? I18N[S.lang].admin.on : I18N[S.lang].admin.off;
  $("#btnAdmin").classList.toggle("hidden", S.info.admin || !S.info.windows);
  $("#btnAdmin").title = I18N[S.lang].admin.why;
  $$("#langSeg button").forEach(b => b.classList.toggle("on", b.dataset.lang === S.lang));
  $$("#themeSeg button").forEach(b => b.classList.toggle("on", b.dataset.theme === S.theme));
}
function applyTheme() {
  if (S.theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = S.theme;
}
/* Pages added in ui/pages/*.js push their renderer here; scopes register re-render / forget hooks. */
const PAGE_RENDERERS = [];
const BARS = {};
const SCOPE_RENDER = {};
const FORGET = {};
const CHANGE_HOOKS = [];
function renderAll() {
  applyStatic();
  renderHome(); renderCleanup(); renderExplorer(); renderDownloads(); renderFolders(); renderDuplicates();
  PAGE_RENDERERS.forEach(fn => fn());
  if (PAGE_ENTER[S.page]) PAGE_ENTER[S.page]();
}
function go(page) {
  S.page = page;
  $$(".nav").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + page));
  $(".main").scrollTop = 0;
  if (PAGE_ENTER[page]) PAGE_ENTER[page]();
}
const PAGE_ENTER = {};
async function loadDrives() {
  try {
    S.drives = await api("drives");
    renderHome();
    const sel = $("#clDrive");
    if (sel) renderCleanupStats();
  } catch (e) { fail(e); }
}

/* ================================================================ Home */
function driveCard(d) {
  const usedPct = d.total ? d.used / d.total : 0;
  const freePct = 1 - usedPct;
  const lvl = freePct < 0.1 ? "low" : freePct < 0.2 ? "mid" : "";
  const kind = d.system ? t("home.system") : t("home." + (d.type === "removable" ? "removable" : d.type === "network" ? "network" : "fixed"));
  return `<div class="drive ${d.system ? "sys" : ""}">
    <div class="drive-top"><div class="drive-letter">${esc(d.letter)}:</div>
      <div class="grow"><div class="drive-name">${esc(d.label || kind)}</div><div class="row small">
        <span class="badge ${d.system ? "b-info" : "b-muted"}">${kind}</span>${esc(d.fs ? " " + d.fs : "")}
        ${lvl === "low" ? `<span class="badge b-danger">${t("home.low")}</span>` : ""}</div></div></div>
    <div class="bar ${lvl}"><i style="width:${(usedPct * 100).toFixed(1)}%"></i></div>
    <div class="free"><b>${size(d.free)}</b> ${t("common.free")} ${t("common.of")} ${size(d.total)}</div>
    <div class="row"><button class="btn sm primary" data-act="home-clean" data-root="${esc(d.root)}">${icon("sweep")}${t("home.clean")}</button>
      <button class="btn sm" data-act="home-explore" data-root="${esc(d.root)}">${icon("pie")}${t("home.explore")}</button></div></div>`;
}
function renderHome() {
  const feats = [["cleanup", "sweep"], ["explorer", "pie"], ["downloads", "download"], ["folders", "folder"], ["duplicates", "copy"]];
  $("#page-home").innerHTML = head(t("home.title"), t("home.sub")) + `<div id="homeHint"></div>` +
    `<div class="section-title"><h3>${t("home.drives")}</h3></div><div class="drives">${S.drives.map(driveCard).join("")}</div>
     <div class="section-title"><h3>${t("home.sections")}</h3></div>
     <div class="features">${feats.map(([p, ic]) => `<button class="feature" data-act="nav" data-page="${p}">${icon(ic)}
       <div><b>${t("nav." + p)}</b><span>${t("home.f_" + p)}</span></div></button>`).join("")}</div>`;
}

/* ================================================================ Cleanup */
const GROUPS = ["safe", "review", "space", "system", "never"];
const GROUP_BADGE = { safe: "b-safe", review: "b-warn", space: "b-info", system: "b-muted", never: "b-never" };

function clSelectable(it) {
  return (it.group === "safe" || it.group === "review") && !(it.admin && !S.info.admin) && it.exists && it.measured && it.size > 0;
}
function renderCleanup() {
  const c = S.cl;
  const sys = S.drives.find(d => d.system);
  if (!c.drive) c.drive = sys ? sys.root : (S.drives[0] || {}).root;
  const opts = S.drives.map(d => `<option value="${esc(d.root)}" ${d.root === c.drive ? "selected" : ""}>${esc(d.letter)}: ${esc(d.label)} — ${size(d.free)} ${t("common.free")}</option>`).join("");
  $("#page-cleanup").innerHTML = head(t("cleanup.title"), t("cleanup.sub")) +
    `<div class="card"><div class="row"><label class="muted">${t("cleanup.drive")}</label><select id="clDrive">${opts}</select>
      <button class="btn primary" data-act="cl-scan">${icon("sweep")}${c.result ? t("common.reanalyze") : t("common.analyze")}</button>
      <span class="grow"></span>${!S.info.admin && S.info.windows ? `<span class="small muted">${t("admin.why")}</span>` : ""}</div></div>
     <div class="task hidden" id="clTask"></div><div id="clReport"></div><div id="clBody"></div>`;
  renderCleanupBody();
  renderCleanupReport();
}
function clRow(it) {
  const selectable = it.group === "safe" || it.group === "review";
  const blocked = it.admin && !S.info.admin;
  const ok = clSelectable(it);
  const badges = [];
  if (blocked) badges.push(`<span class="badge b-warn">${icon("shield")}${t("cleanup.needs_admin")}</span>`);
  if (it.running && it.running.length) badges.push(`<span class="badge b-warn">${t("cleanup.close_app", { app: it.running.map(appName).join(", ") })}</span>`);
  if (!it.exists) badges.push(`<span class="badge b-muted">${t("cleanup.not_found")}</span>`);
  const sizeCell = !it.measured ? (it.mode === "shadow" ? `<span class="badge b-muted">${t("cleanup.unmeasured")}</span>` : "—") :
    `<span class="${it.size > 1 << 30 ? "size-big" : ""}">${size(it.size)}</span>`;
  const first = it.paths[0];
  const where = first ? `<div class="path" title="${esc(first.path)}">${esc(pp(first.path))}</div>` : `<span class="muted">—</span>`;
  const acts = [];
  if (it.paths.length > 1 || (selectable && it.paths.length)) acts.push(`<button class="btn ghost sm" data-act="cl-details" data-id="${it.id}">${c_open(it.id) ? t("cleanup.hide") : t("cleanup.details")}${it.paths.length > 1 ? ` (${it.paths.length})` : ""}</button>`);
  if (!selectable && first) acts.push(openBtn(first.path));
  if (it.tool) acts.push(`<button class="btn sm" data-act="tool" data-tool="${it.tool}">${icon("open")}${t("cleanup.open_settings")}</button>`);
  let html = `<tr class="${selectable && !ok ? "disabled" : ""}">
    <td class="chk">${selectable ? `<input type="checkbox" data-clsel="${it.id}" ${ok ? "" : "disabled"} ${ok && S.cl.sel.has(it.id) ? "checked" : ""}>` : icon(RULE_ICONS[it.icon] || "file")}</td>
    <td class="what"><b>${L(it.name)}</b><span>${L(it.what)}</span>${badges.length ? `<div class="row" style="margin-top:6px">${badges.join("")}</div>` : ""}</td>
    <td class="num">${sizeCell}</td><td style="max-width:260px">${where}</td><td class="effect">${mdCode(L(it.effect))}</td><td class="act">${acts.join("")}</td></tr>`;
  if (c_open(it.id) && it.paths.length) {
    html += `<tr class="details-row"><td></td><td colspan="5"><div class="subpaths">${it.paths.map(p =>
      `<div><span class="path">${esc(pp(p.path))}</span><span class="num small">${size(p.size)}</span>${openBtn(p.path)}</div>`).join("")}</div></td></tr>`;
  }
  return html;
}
const c_open = id => S.cl.open.has(id);
const mdCode = s => s.replace(/`([^`]+)`/g, "<code>$1</code>");

function renderCleanupStats() {
  const c = S.cl, el = $("#clStats");
  if (!el || !c.result) return;
  const safeTotal = c.result.items.filter(i => i.group === "safe" && clSelectable(i)).reduce((a, i) => a + i.size, 0);
  const selTotal = c.result.items.filter(i => c.sel.has(i.id) && clSelectable(i)).reduce((a, i) => a + i.size, 0);
  const drive = S.drives.find(d => d.root === c.drive);
  el.innerHTML = stat(t("cleanup.safe_total"), size(safeTotal), "accent", "shield") + stat(t("cleanup.selected"), size(selTotal), "", "check") +
    stat(t("cleanup.free_now"), size(drive ? drive.free : c.result.free), "", "disk");
  const btn = $("#clFree");
  if (btn) { btn.disabled = !selTotal; btn.innerHTML = icon("sweep") + t("cleanup.free_btn", { size: size(selTotal) }); }
}
function renderCleanupBody() {
  const c = S.cl, el = $("#clBody");
  if (!el) return;
  if (!c.result) { el.innerHTML = `<div class="card">${empty(t("cleanup.sub"), "sweep")}</div>`; return; }
  let html = `<div class="stats" id="clStats"></div>`;
  if (!c.result.is_system) html += `<div class="note">${icon("infoc")}<div>${t("cleanup.nonc")}</div></div>`;
  for (const g of GROUPS) {
    const items = c.result.items.filter(i => i.group === g);
    if (!items.length) continue;
    const sum = items.reduce((a, i) => a + (i.size || 0), 0);
    html += `<div class="section-title"><span class="badge ${GROUP_BADGE[g]}">${t("cleanup.g_" + g)}</span><p>${t("cleanup.g_" + g + "_d")}</p>
      <span class="grow"></span><span class="small muted">${g === "never" ? "" : size(sum)}</span></div>
      <div class="tbl-wrap"><table><thead><tr><th class="chk"></th><th>${t("common.what")}</th><th class="num">${t("common.size")}</th>
      <th>${t("common.where")}</th><th>${t("common.effect")}</th><th></th></tr></thead><tbody>${items.map(clRow).join("")}</tbody></table></div>`;
  }
  if (c.result.is_system) html += `<div id="dismCard"></div>`;
  html += `<div class="sticky-actions"><span class="grow small muted">${t("cleanup.confirm_note")}</span>
    <button class="btn primary" id="clFree" data-act="cl-free" disabled></button></div>`;
  el.innerHTML = html;
  renderCleanupStats();
  if (typeof renderDismCard === "function") renderDismCard();
}
function renderCleanupReport() {
  const r = S.cl.report, el = $("#clReport");
  if (!el) return;
  if (!r) { el.innerHTML = ""; return; }
  const diff = Math.max(0, r.free_after - r.free_before);
  el.innerHTML = `<div class="card"><h2>${icon("check")}${t("cleanup.result_t")}</h2>
    <p class="lead">${t("cleanup.before_after", { before: size(r.free_before), after: size(r.free_after), diff: size(diff) })}</p>
    <div class="tbl-wrap"><table><thead><tr><th>${t("common.what")}</th><th class="num">${t("cleanup.freed")}</th><th class="num">${t("cleanup.deleted")}</th>
    <th class="num">${t("cleanup.skipped")}</th><th>${t("cleanup.note")}</th></tr></thead><tbody>${r.items.map(i => `<tr><td>${L(i.name)}</td>
    <td class="num">${size(i.freed)}</td><td class="num">${num(i.deleted)}</td><td class="num">${num(i.skipped)}</td><td class="small muted">${L(i.note)}</td></tr>`).join("")}
    </tbody></table></div><div class="row" style="margin-top:10px"><span class="grow"></span><button class="btn ghost sm" data-act="cl-hide-report">${t("common.close")}</button></div></div>`;
}
async function cleanupScan() {
  const c = S.cl;
  c.drive = $("#clDrive").value;
  try {
    const res = await runJob(api("cleanup_scan", c.drive), $("#clTask"), t("cleanup.scanning"));
    if (!res) return;
    c.result = res;
    c.sel = new Set(res.items.filter(i => i.group === "safe" && clSelectable(i)).map(i => i.id));
    c.open.clear();
    renderCleanup();
  } catch (e) { fail(e); }
}
async function cleanupFree() {
  const c = S.cl;
  const items = c.result.items.filter(i => c.sel.has(i.id) && clSelectable(i));
  if (!items.length) return toast(t("common.nothing_selected"));
  const total = items.reduce((a, i) => a + i.size, 0);
  const rb = items.some(i => i.mode === "recyclebin");
  const ok = await modal({
    title: t("cleanup.confirm_t", { size: size(total) }),
    body: `<p>${t("cleanup.confirm_b")}</p><ul>${items.map(i => `<li><b>${L(i.name)}</b> — ${size(i.size)}</li>`).join("")}</ul>
      <div class="note">${icon("infoc")}<div>${t("cleanup.confirm_note")}</div></div>
      ${rb ? `<div class="note warn">${icon("alert")}<div>${t("cleanup.confirm_rb")}</div></div>` : ""}`,
    ok: t("cleanup.free_btn", { size: size(total) }),
  });
  if (!ok) return;
  try {
    const rep = await runJob(api("cleanup_run", items.map(i => i.id), c.drive), $("#clTask"), I18N[S.lang].common.working);
    if (!rep) return;
    c.report = rep;
    renderCleanupReport();
    await loadDrives();
    await cleanupScan();
    renderCleanupReport();
  } catch (e) { fail(e); }
}

/* ================================================================ Disk explorer */
function renderExplorer() {
  const x = S.ex;
  if (!x.root) { const sys = S.drives.find(d => d.system); x.root = sys ? sys.root : (S.drives[0] || {}).root; }
  const chips = S.drives.map(d => `<button class="chip ${x.root === d.root ? "on" : ""}" data-act="ex-root" data-root="${esc(d.root)}">${icon("disk")}${esc(d.letter)}:</button>`).join("");
  const custom = x.root && !S.drives.some(d => d.root === x.root) ? `<button class="chip on">${icon("folder")}${esc(x.root)}</button>` : "";
  $("#page-explorer").innerHTML = head(t("explorer.title"), t("explorer.sub")) +
    `<div class="card"><div class="row">${chips}${custom}<button class="chip" data-act="ex-other">${icon("plus")}${t("common.other")}</button>
      <span class="grow"></span><button class="btn primary" data-act="ex-scan">${icon("pie")}${x.summary ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="exTask"></div><div id="exBody"></div>`;
  renderExplorerBody();
}
function renderExplorerBody() {
  const x = S.ex, el = $("#exBody");
  if (!el) return;
  const s = x.summary;
  if (!s) { el.innerHTML = `<div class="card">${empty(t("explorer.sub"), "pie")}</div>`; return; }
  let html = `<div class="stats">${stat(t("explorer.scanned"), size(s.total), "accent", "pie")}
    ${stat(t("common.files_t"), num(s.files), "", "file")}
    ${s.unaccounted != null ? stat(t("explorer.unaccounted"), size(s.unaccounted), s.unaccounted > 5 * 2 ** 30 ? "warn" : "", "shield") : ""}
    ${stat(t("cleanup.free_now"), size(s.free), "", "disk")}</div>
    ${s.unaccounted != null && s.unaccounted > 2 ** 30 ? `<div class="note">${icon("infoc")}<div>${t("explorer.unaccounted_d")}</div></div>` : ""}
    <div class="card"><div class="tabs">${["folders", "largest", "types"].map(k => `<button class="${x.tab === k ? "on" : ""}" data-act="ex-tab" data-tab="${k}">${t("explorer." + k)}</button>`).join("")}
    <span class="grow"></span><span class="small muted" style="align-self:center">${s.seconds}s</span></div>`;
  if (x.tab === "folders") html += explorerFolders();
  if (x.tab === "largest") html += `<div>${s.largest.map(f => `<div class="lrow">${icon("file")}<span class="name" title="${esc(f.path)}">${esc(base(f.path))}<div class="path">${esc(pp(f.path))}</div></span>
      <span></span><span class="num">${size(f.size)}</span><span></span><span class="act">${openBtn(f.path)}${trashBtn(f.path, "ex")}</span></div>`).join("")}</div>`;
  if (x.tab === "types") {
    const max = Math.max(1, ...s.exts.map(e => e.size));
    html += s.exts.map(e => `<div class="lrow">${icon("file")}<span class="name">${e.ext ? "." + esc(e.ext) : t("explorer.noext")}</span>
      <div class="bar"><i style="width:${(e.size / max * 100).toFixed(1)}%"></i></div><span class="num">${size(e.size)}</span><span class="num small muted files">${num(e.files)}</span><span></span></div>`).join("");
  }
  el.innerHTML = html + "</div>";
}
function explorerFolders() {
  const x = S.ex, n = x.node;
  if (!n) return "";
  const parts = x.rel ? x.rel.split("\\") : [];
  let crumbs = `<div class="crumbs"><button data-act="ex-crumb" data-i="0">${esc(x.summary.root)}</button>`;
  parts.forEach((p, i) => { crumbs += `<span>›</span><button data-act="ex-crumb" data-i="${i + 1}">${esc(p)}</button>`; });
  crumbs += `<span class="grow"></span>${openBtn(n.path)}</div>`;
  const total = Math.max(1, n.size);
  const dirs = n.dirs.map(d => `<div class="lrow dir">${icon("folder")}<span class="name link" data-act="ex-in" data-name="${esc(d.name)}" title="${esc(d.path)}">${esc(d.name)}${d.denied ? ` <span class="badge b-muted">${t("explorer.denied")}</span>` : ""}</span>
    <div class="bar"><i style="width:${(d.size / total * 100).toFixed(1)}%"></i></div><span class="num">${size(d.size)}</span>
    <span class="num small muted files">${(d.size / total * 100).toFixed(1)}%</span><span class="act">${openBtn(d.path)}
    <button class="icon-btn" title="${esc((I18N[S.lang].mv || {}).nav || "")}" data-act="ex-move" data-path="${esc(d.path)}">${icon("disk")}</button>${trashBtn(d.path, "ex")}</span></div>`).join("");
  const files = n.files.length ? `<div class="section-title"><h3>${t("explorer.loose")}</h3></div>` + n.files.map(f => `<div class="lrow">${icon("file")}
    <span class="name" title="${esc(f.path)}">${esc(f.name)}</span><div class="bar"><i style="width:${(f.size / total * 100).toFixed(1)}%"></i></div>
    <span class="num">${size(f.size)}</span><span class="num small muted files">${date(f.mtime)}</span><span class="act">${openBtn(f.path)}${trashBtn(f.path, "ex")}</span></div>`).join("") +
    (n.more_files ? `<p class="small muted">${t("explorer.more", { n: num(n.more_files) })}</p>` : "") : "";
  return crumbs + (dirs || files ? dirs + files : empty(t("common.none"), "folder"));
}
async function explorerScan() {
  const x = S.ex;
  try {
    const res = await runJob(api("disk_scan", x.root), $("#exTask"), t("explorer.scanning"));
    if (!res) return;
    x.summary = res; x.rel = ""; x.tab = "folders";
    x.node = await api("disk_children", res.scan_id, "");
    renderExplorer();
  } catch (e) { fail(e); }
}
async function explorerGo(relPath) {
  try {
    S.ex.node = await api("disk_children", S.ex.summary.scan_id, relPath);
    S.ex.rel = relPath;
    renderExplorerBody();
  } catch (e) { fail(e); }
}

/* ================================================================ Downloads */
function renderDownloads() {
  const d = S.dl;
  if (!d.folder) d.folder = S.info.folders.downloads;
  $("#page-downloads").innerHTML = head(t("downloads.title"), t("downloads.sub")) +
    `<div class="card"><div class="row">${icon("download")}<span class="mono grow">${esc(d.folder)}</span>
      <button class="btn" data-act="dl-change">${t("common.change")}</button>
      <button class="btn primary" data-act="dl-scan">${icon("sweep")}${d.res ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="dlTask"></div><div id="dlBody"></div>`;
  renderDownloadsBody();
}
function dlReason(s) {
  return t("downloads.r_" + s.reason, { keep: s.keep, age: num(s.age) });
}
function renderDownloadsBody() {
  const d = S.dl, el = $("#dlBody");
  if (!el) return;
  const undo = d.undo ? `<button class="btn" data-act="undo" data-name="${esc(d.undo.name)}" data-scope="dl">${icon("undo")}${t("downloads.undo", { n: num(d.undo.files), date: new Date(d.undo.time * 1000).toLocaleString() })}</button>` : "";
  if (!d.res) { el.innerHTML = `<div class="card">${empty(t("downloads.sub"), "download")}${undo ? `<div class="row" style="justify-content:center">${undo}</div>` : ""}</div>`; return; }
  const r = d.res;
  const sugTotal = r.suggestions.reduce((a, s) => a + s.size, 0);
  let html = `<div class="stats">${stat(t("downloads.total"), size(r.total), "", "download")}${stat(t("common.files_t"), num(r.files), "", "file")}
    ${stat(t("downloads.suggest"), size(sugTotal), sugTotal ? "accent" : "", "trash")}</div>`;
  html += `<div class="card"><h2>${icon("trash")}${t("downloads.suggest")}</h2><p class="lead">${t("downloads.suggest_d")}</p>`;
  if (!r.suggestions.length) html += empty(t("downloads.nothing"));
  else {
    html += `<div class="row" style="margin-bottom:8px"><button class="btn ghost sm" data-act="sel-all" data-scope="dl">${t("common.select_all")}</button>
      <button class="btn ghost sm" data-act="sel-none" data-scope="dl">${t("common.select_none")}</button></div>
      <div class="tbl-wrap"><table><thead><tr><th class="chk"></th><th>${t("common.name")}</th><th class="num">${t("common.size")}</th>
      <th class="num">${t("downloads.age")}</th><th>${t("common.reason")}</th><th></th></tr></thead><tbody>
      ${r.suggestions.map(s => `<tr><td class="chk">${checkbox("dl", s.path)}</td><td><b>${esc(s.name)}</b></td><td class="num">${size(s.size)}</td>
        <td class="num">${num(s.age)} ${t("common.days")}</td><td><span class="badge wrap ${s.reason === "duplicate" || s.reason === "partial" ? "b-safe" : "b-warn"}">${dlReason(s)}</span></td>
        <td class="act">${openBtn(s.path)}</td></tr>`).join("")}</tbody></table></div>
      <div class="sticky-actions" id="dlBar">${selectionBar("dl")}</div>`;
  }
  html += `</div><div class="card"><h2>${icon("folder")}${t("downloads.organize")}</h2><p class="lead">${t("downloads.organize_d")}</p>
    <div class="plan-grid">${r.plan.map(p => `<div class="plan-item"><b>${icon("folder")}${esc(p.folder)}</b><span class="small muted">${num(p.files)} ${t("common.files")} · ${size(p.size)}</span></div>`).join("")}</div>
    <div class="row"><button class="btn primary" data-act="dl-organize" ${r.moves.length ? "" : "disabled"}>${icon("check")}${t("downloads.organize_btn", { n: num(r.moves.length) })}</button>
    <button class="btn ghost" data-act="dl-list">${t("downloads.list")}</button><span class="grow"></span>${undo}</div>
    ${d.list ? `<div class="tbl-wrap" style="margin-top:12px"><table><tbody>${r.moves.map(m => `<tr><td>${esc(m.name)}</td><td class="num">${size(m.size)}</td><td>→ <b>${esc(m.folder)}</b></td></tr>`).join("")}</tbody></table></div>` : ""}</div>`;
  el.innerHTML = html;
}
async function downloadsScan() {
  const d = S.dl;
  try {
    const res = await runJob(api("downloads_analyze", d.folder, S.lang), $("#dlTask"), t("downloads.analyzing"));
    if (!res) return;
    d.res = res;
    d.sizes = new Map(res.suggestions.map(s => [s.path, s.size]));
    d.sel = new Set(res.suggestions.filter(s => s.reason === "duplicate" || s.reason === "partial").map(s => s.path));
    d.undo = await api("undo_info", "downloads");
    renderDownloads();
  } catch (e) { fail(e); }
}

/* ================================================================ My folders */
const FOLDER_KEYS = [["documents", "file"], ["pictures", "image"], ["videos", "game"], ["music", "music"], ["desktop", "app"]];
function renderFolders() {
  const f = S.fo;
  if (!f.folder) f.folder = S.info.folders[f.key];
  const chips = FOLDER_KEYS.map(([k, ic]) => `<button class="chip ${f.key === k ? "on" : ""}" data-act="fo-key" data-key="${k}">${icon(ic)}${t("folders." + k)}</button>`).join("");
  $("#page-folders").innerHTML = head(t("folders.title"), t("folders.sub")) +
    `<div class="card"><div class="row">${chips}<button class="chip ${f.key === "custom" ? "on" : ""}" data-act="fo-other">${icon("plus")}${t("common.other")}</button></div>
      <div class="row" style="margin-top:12px"><span class="mono grow">${esc(f.folder)}</span>
      <button class="btn" data-act="fo-dups">${icon("copy")}${t("folders.dups")}</button>
      <button class="btn primary" data-act="fo-scan">${icon("sweep")}${f.res ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="foTask"></div><div id="foBody"></div>`;
  renderFoldersBody();
}
function fileTable(scope, rows, root, cols) {
  if (!rows.length) return empty(t("common.none"));
  return `<div class="tbl-wrap"><table><thead><tr><th class="chk"></th><th>${t("common.path")}</th><th class="num">${t("common.size")}</th>${cols.map(c => `<th>${c.h}</th>`).join("")}<th></th></tr></thead>
    <tbody>${rows.map(r => `<tr><td class="chk">${checkbox(scope, r.path)}</td><td><div class="path" style="color:var(--text)">${esc(rel(r.path, root))}</div></td>
    <td class="num">${size(r.size)}</td>${cols.map(c => `<td class="small">${c.f(r)}</td>`).join("")}<td class="act">${openBtn(r.path)}</td></tr>`).join("")}</tbody></table></div>`;
}
function foReason(r) {
  const key = r.reason === "node_modules" ? "node_modules" : r.reason;
  return t("folders.r_" + key, { keep: r.keep });
}
function renderFoldersBody() {
  const f = S.fo, el = $("#foBody");
  if (!el) return;
  const mediaCard = foMediaCard();
  if (!f.res) { el.innerHTML = `<div class="card">${empty(t("folders.sub"), "folder")}</div>` + mediaCard; return; }
  const r = f.res, root = r.folder;
  const total = Math.max(1, r.total);
  let html = `<div class="stats">${stat(t("folders.total"), size(r.total), "", "folder")}${stat(t("common.files_t"), num(r.files), "", "file")}
    ${stat(t("folders.maybe"), size(r.findings_size), r.findings_size ? "accent" : "", "trash")}</div>`;
  html += `<div class="card"><h2>${icon("pie")}${t("folders.by_type")}</h2>
    <div class="catbar">${r.categories.map(c => `<i style="width:${(c.size / total * 100).toFixed(2)}%;background:${CAT_COLORS[c.cat] || "#94a3b8"}" title="${esc(I18N[S.lang].cat[c.cat] || c.cat)}"></i>`).join("")}</div>
    <div class="legend">${r.categories.map(c => `<span><i style="background:${CAT_COLORS[c.cat] || "#94a3b8"}"></i>${t("cat." + c.cat)} <b>${size(c.size)}</b> <span class="muted">(${num(c.files)})</span></span>`).join("")}</div></div>`;
  html += `<div class="card"><h2>${icon("alert")}${t("folders.findings")}</h2><p class="lead">${t("folders.findings_d")}</p>
    ${fileTable("fo", r.findings, root, [{ h: t("common.reason"), f: x => `<span class="badge wrap ${x.dir ? "b-safe" : "b-warn"}">${foReason(x)}</span>` }])}</div>`;
  html += `<div class="card"><h2>${icon("folder")}${t("folders.subfolders")}</h2>${r.subfolders.map(s => `<div class="lrow dir">${icon("folder")}
    <span class="name">${esc(s.name)}</span><div class="bar"><i style="width:${(s.size / total * 100).toFixed(1)}%"></i></div><span class="num">${size(s.size)}</span>
    <span class="num small muted files">${(s.size / total * 100).toFixed(1)}%</span><span class="act">${openBtn(s.path)}</span></div>`).join("") || empty(t("common.none"))}</div>`;
  html += `<div class="card"><h2>${icon("file")}${t("folders.largest")}</h2>${fileTable("fo", r.largest, root, [{ h: t("common.date"), f: x => date(x.mtime) }])}</div>`;
  html += `<div class="card"><h2>${icon("clock")}${t("folders.old")}</h2><p class="lead">${t("folders.old_d")}</p>${fileTable("fo", r.old_big, root, [{ h: t("common.date"), f: x => date(x.mtime) }])}</div>`;
  html += mediaCard + `<div class="sticky-actions" id="foBar">${selectionBar("fo")}</div>`;
  el.innerHTML = html;
}
function foMediaCard() {
  const f = S.fo, m = f.media;
  const undo = f.undo ? `<button class="btn" data-act="undo" data-name="${esc(f.undo.name)}" data-scope="fo">${icon("undo")}${t("downloads.undo", { n: num(f.undo.files), date: new Date(f.undo.time * 1000).toLocaleString() })}</button>` : "";
  let body = "";
  if (m) {
    body = m.files ? `<div class="plan-grid" style="margin-top:12px">${m.plan.map(p => `<div class="plan-item"><b>${icon("calendar")}${esc(p.folder)}</b><span class="small muted">${num(p.files)} ${t("common.files")} · ${size(p.size)}</span></div>`).join("")}</div>
      <p class="small muted">${t("folders.exif", { n: num(m.exif) })}</p>
      <button class="btn primary" data-act="fo-media-apply">${icon("check")}${t("folders.apply_btn", { n: num(m.files) })}</button>` : `<p class="muted">${t("folders.no_media")}</p>`;
  }
  return `<div class="card"><h2>${icon("calendar")}${t("folders.by_date")}</h2><p class="lead">${t("folders.by_date_d")}</p>
    <div class="row"><button class="btn" data-act="fo-media-plan">${icon("calendar")}${t("folders.plan_btn")}</button><span class="grow"></span>${undo}</div>${body}</div>`;
}
async function foldersScan() {
  const f = S.fo;
  try {
    const res = await runJob(api("folder_analyze", f.folder), $("#foTask"), t("folders.analyzing"));
    if (!res) return;
    f.res = res;
    f.sel.clear();
    f.sizes = new Map([...res.findings, ...res.largest, ...res.old_big].map(x => [x.path, x.size]));
    f.undo = await api("undo_info", "media");
    renderFolders();
  } catch (e) { fail(e); }
}

/* ================================================================ Duplicates */
function renderDuplicates() {
  const u = S.du;
  if (!u.folders.length && S.info) u.folders = [S.info.folders.downloads, S.info.folders.documents];
  const known = FOLDER_KEYS.map(([k]) => [k, S.info.folders[k]]).concat([["downloads", S.info.folders.downloads]])
    .filter(([, p]) => p && !u.folders.includes(p));
  const mins = [["0.1", "100 KB"], ["1", "1 MB"], ["10", "10 MB"], ["100", "100 MB"]];
  $("#page-duplicates").innerHTML = head(t("dup.title"), t("dup.sub")) +
    `<div class="card"><h2>${t("dup.folders")}</h2>
      <div class="row" style="margin:8px 0 12px">${u.folders.map((p, i) => `<span class="chip on">${icon("folder")}<span class="mono">${esc(p)}</span>
        <span class="x" data-act="du-rm" data-i="${i}">${icon("x")}</span></span>`).join("")}</div>
      <div class="row">${known.map(([k, p]) => `<button class="chip" data-act="du-add" data-path="${esc(p)}">${icon("plus")}${t(k === "downloads" ? "nav.downloads" : "folders." + k)}</button>`).join("")}
        <button class="chip" data-act="du-pick">${icon("plus")}${t("dup.add")}</button></div>
      <div class="row" style="margin-top:14px"><label class="muted">${t("dup.min")}</label><select id="duMin">${mins.map(([v, l]) => `<option value="${v}" ${u.min === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span class="grow"></span><button class="btn primary" data-act="du-scan">${icon("copy")}${t("dup.search")}</button></div>
      <div class="note">${icon("infoc")}<div>${t("dup.how")}</div></div></div>
     <div class="card"><div class="row"><h2 class="grow">${icon("shield")}${t("dup.backup")}</h2>
       <label class="switch"><input type="checkbox" id="duRefOn" ${u.refOn ? "checked" : ""}><span></span></label></div>
       <p class="lead">${t("dup.backup_d")}</p>
       ${u.refOn ? `<div class="row">${u.ref.map((p, i) => `<span class="chip on">${icon("shield")}<span class="mono">${esc(p)}</span>
         <span class="x" data-act="du-ref-rm" data-i="${i}">${icon("x")}</span></span>`).join("")}
         <button class="chip" data-act="du-ref-add">${icon("plus")}${t("dup.backup_add")}</button></div>` : ""}</div>
     <div class="task hidden" id="duTask"></div><div id="duBody"></div>`;
  renderDuplicatesBody();
}
function renderDuplicatesBody() {
  const u = S.du, el = $("#duBody");
  if (!el || !u.res) { if (el) el.innerHTML = ""; return; }
  const r = u.res;
  let html = `<div class="stats">${stat(t("dup.groups"), num(r.groups.length), "", "copy")}${stat(t("dup.wasted"), size(r.wasted), r.wasted ? "accent" : "", "trash")}
    ${stat(t("dup.scanned"), num(r.scanned), "", "file")}</div>`;
  if (!r.groups.length) { el.innerHTML = html + `<div class="card">${empty(t("dup.none"))}</div>`; return; }
  html += `<div class="card"><div class="row" style="margin-bottom:12px"><label class="muted">${t("dup.keep")}</label>
    <select id="duKeep">${["oldest", "newest", "shortest"].map(k => `<option value="${k}" ${u.keep === k ? "selected" : ""}>${t("dup.k_" + k)}</option>`).join("")}</select>
    <button class="btn sm" data-act="du-auto">${t("dup.auto")}</button><button class="btn ghost sm" data-act="sel-none" data-scope="du">${t("common.select_none")}</button>
    <span class="small muted">${t("dup.auto_d")}</span></div>`;
  html += r.groups.slice(0, u.shown).map((g, gi) => `<div class="group"><div class="group-head">${icon("copy")}<b>${t("dup.copies", { n: g.files.length, size: size(g.size) })}</b>
      <span class="grow"></span><span class="muted small">${size(g.wasted)}</span></div>
      ${g.files.map(f => f.ref
        ? `<div class="group-row keep">${icon("shield")}<span class="path">${esc(pp(f.path))}</span><span class="badge b-info">${t("dup.backup_copy")}</span>
            <span class="small muted">${date(f.mtime)}</span>${openBtn(f.path)}</div>`
        : `<div class="group-row ${u.sel.has(f.path) ? "" : "keep"}">${checkbox("du", f.path, `data-group="${gi}"`)}<span class="path">${esc(pp(f.path))}</span>
        ${u.sel.has(f.path) ? "" : `<span class="badge b-safe">${t("dup.kept")}</span>`}<span class="small muted">${date(f.mtime)}</span>${openBtn(f.path)}</div>`).join("")}</div>`).join("");
  if (r.groups.length > u.shown) html += `<button class="btn" data-act="du-more">${t("common.show_more")} (${num(r.groups.length - u.shown)})</button>`;
  html += `<div class="sticky-actions" id="duBar">${selectionBar("du")}</div></div>`;
  el.innerHTML = html;
}
function duAuto() {
  const u = S.du;
  u.sel.clear();
  for (const g of u.res.groups) {
    if (g.files.some(f => f.ref)) {  // backup mode: everything outside the backup can go
      g.files.forEach(f => { if (!f.ref) u.sel.add(f.path); });
      continue;
    }
    let keep = 0;
    if (u.keep === "newest") keep = g.files.length - 1;
    if (u.keep === "shortest") keep = g.files.reduce((b, f, i) => (f.path.length < g.files[b].path.length ? i : b), 0);
    g.files.forEach((f, i) => { if (i !== keep) u.sel.add(f.path); });
  }
}
async function duplicatesScan() {
  const u = S.du;
  if (!u.folders.length) return toast(t("dup.choose"));
  u.min = $("#duMin").value;
  const label = s => ({ "quick-hash": t("dup.quick"), "full-hash": t("dup.full") }[s.message] || t("dup.listing"));
  try {
    if (u.refOn && !u.ref.length) return toast(t("dup.backup_choose"), true);
    const res = await runJob(api("duplicates_find", u.folders, u.min, u.refOn ? u.ref : []), $("#duTask"), label);
    if (!res) return;
    u.res = res;
    u.shown = 60;
    u.sizes = new Map();
    res.groups.forEach(g => g.files.forEach(f => u.sizes.set(f.path, g.size)));
    u.sel.clear();  // nothing pre-selected: the user decides with "Auto-select" or by hand
    renderDuplicatesBody();
  } catch (e) { fail(e); }
}

/* ================================================================ removing deleted items from views */
function forgetPaths(scope, gone) {
  if (!gone || !gone.size) return;
  if (scope === "dl" && S.dl.res) {
    S.dl.res.suggestions = S.dl.res.suggestions.filter(s => !gone.has(s.path));
    S.dl.res.moves = S.dl.res.moves.filter(m => !gone.has(m.src));
    renderDownloadsBody();
  } else if (scope === "fo" && S.fo.res) {
    for (const k of ["findings", "largest", "old_big"]) S.fo.res[k] = S.fo.res[k].filter(x => !gone.has(x.path));
    S.fo.res.findings_size = S.fo.res.findings.reduce((a, x) => a + x.size, 0);
    renderFoldersBody();
  } else if (scope === "du" && S.du.res) {
    const r = S.du.res;
    r.groups = r.groups.map(g => ({ ...g, files: g.files.filter(f => !gone.has(f.path)) })).filter(g => g.files.length > 1);
    r.groups.forEach(g => { g.wasted = g.size * (g.files.length - 1); });
    r.wasted = r.groups.reduce((a, g) => a + g.wasted, 0);
    renderDuplicatesBody();
  } else if (scope === "ex" && S.ex.summary) {
    S.ex.summary.largest = S.ex.summary.largest.filter(f => !gone.has(f.path));
    explorerGo(S.ex.rel);
  } else if (FORGET[scope]) FORGET[scope](gone);
}

/* ================================================================ events */
const ACTIONS = {
  nav: el => go(el.dataset.page),
  open: el => api("open_path", el.dataset.path).catch(fail),
  tool: el => api("open_tool", el.dataset.tool).catch(fail),
  "home-clean": el => { S.cl.drive = el.dataset.root; renderCleanup(); go("cleanup"); cleanupScan(); },
  "home-explore": el => { S.ex.root = el.dataset.root; S.ex.summary = null; renderExplorer(); go("explorer"); explorerScan(); },

  "cl-scan": () => cleanupScan(),
  "cl-free": () => cleanupFree(),
  "cl-details": el => { const id = el.dataset.id; S.cl.open.has(id) ? S.cl.open.delete(id) : S.cl.open.add(id); renderCleanupBody(); },
  "cl-hide-report": () => { S.cl.report = null; renderCleanupReport(); },

  "ex-root": el => { S.ex.root = el.dataset.root; S.ex.summary = null; renderExplorer(); },
  "ex-other": async () => { const p = await pickFolder(S.ex.root); if (p) { S.ex.root = p; S.ex.summary = null; renderExplorer(); explorerScan(); } },
  "ex-scan": () => explorerScan(),
  "ex-tab": el => { S.ex.tab = el.dataset.tab; renderExplorerBody(); },
  "ex-in": el => explorerGo(S.ex.rel ? S.ex.rel + "\\" + el.dataset.name : el.dataset.name),
  "ex-crumb": el => explorerGo((S.ex.rel ? S.ex.rel.split("\\") : []).slice(0, +el.dataset.i).join("\\")),

  "dl-change": async () => { const p = await pickFolder(S.dl.folder); if (p) { S.dl.folder = p; S.dl.res = null; renderDownloads(); } },
  "dl-scan": () => downloadsScan(),
  "dl-list": () => { S.dl.list = !S.dl.list; renderDownloadsBody(); },
  "dl-organize": async () => {
    const r = S.dl.res;
    const ok = await modal({ title: t("downloads.organize_btn", { n: num(r.moves.length) }), body: `<p>${t("downloads.organize_d")}</p>` });
    if (!ok) return;
    try {
      const res = await runJob(api("plan_apply", r.plan_id, []), $("#dlTask"), I18N[S.lang].common.working);
      if (!res) return;
      toast(t("downloads.moved", { n: num(res.moved) }));
      if (res.failed.length) toast(t("common.failed", { n: res.failed.length }), true);
      downloadsScan();
    } catch (e) { fail(e); }
  },
  undo: async el => {
    const scope = el.dataset.scope;
    try {
      const res = await runJob(api("undo_run", el.dataset.name), $(`#${scope}Task`), I18N[S.lang].common.working);
      if (!res) return;
      toast(t("downloads.undone", { n: num(res.restored) }));
      if (res.failed.length) toast(t("common.failed", { n: res.failed.length }), true);
      if (scope === "dl") downloadsScan();
      else { S.fo.media = null; S.fo.undo = await api("undo_info", "media"); renderFoldersBody(); }
    } catch (e) { fail(e); }
  },

  "fo-key": el => { S.fo.key = el.dataset.key; S.fo.folder = S.info.folders[el.dataset.key]; S.fo.res = null; S.fo.media = null; renderFolders(); },
  "fo-other": async () => { const p = await pickFolder(S.fo.folder); if (p) { S.fo.key = "custom"; S.fo.folder = p; S.fo.res = null; S.fo.media = null; renderFolders(); } },
  "fo-scan": () => foldersScan(),
  "fo-dups": () => { S.du.folders = [S.fo.folder]; S.du.res = null; renderDuplicates(); go("duplicates"); },
  "fo-media-plan": async () => {
    try {
      const res = await runJob(api("media_plan", S.fo.folder, S.lang), $("#foTask"), I18N[S.lang].common.working);
      if (res) { S.fo.media = res; renderFoldersBody(); }
    } catch (e) { fail(e); }
  },
  "fo-media-apply": async () => {
    const m = S.fo.media;
    const ok = await modal({ title: t("folders.apply_btn", { n: num(m.files) }), body: `<p>${t("folders.by_date_d")}</p>` });
    if (!ok) return;
    try {
      const res = await runJob(api("plan_apply", m.plan_id, []), $("#foTask"), I18N[S.lang].common.working);
      if (!res) return;
      toast(t("downloads.moved", { n: num(res.moved) }));
      S.fo.media = null;
      S.fo.undo = await api("undo_info", "media");
      renderFoldersBody();
    } catch (e) { fail(e); }
  },

  "du-add": el => { if (!S.du.folders.includes(el.dataset.path)) S.du.folders.push(el.dataset.path); renderDuplicates(); },
  "du-pick": async () => { const p = await pickFolder(); if (p && !S.du.folders.includes(p)) { S.du.folders.push(p); renderDuplicates(); } },
  "du-rm": el => { S.du.folders.splice(+el.dataset.i, 1); renderDuplicates(); },
  "du-scan": () => duplicatesScan(),
  "du-ref-add": async () => { const p = await pickFolder(); if (p && !S.du.ref.includes(p)) { S.du.ref.push(p); renderDuplicates(); } },
  "du-ref-rm": el => { S.du.ref.splice(+el.dataset.i, 1); renderDuplicates(); },
  "du-auto": () => { S.du.keep = $("#duKeep").value; duAuto(); renderDuplicatesBody(); },
  "du-more": () => { S.du.shown += 60; renderDuplicatesBody(); },

  "sel-all": el => { const st = S[el.dataset.scope]; st.sizes.forEach((_, p) => st.sel.add(p)); rerenderScope(el.dataset.scope); },
  "sel-none": el => { S[el.dataset.scope].sel.clear(); rerenderScope(el.dataset.scope); },
  "del-sel": async el => {
    const scope = el.dataset.scope;
    try {
      const gone = await deletePaths(scope, [...S[scope].sel], $(`#${scope}Task`));
      forgetPaths(scope, gone);
    } catch (e) { fail(e); }
  },
  "del-one": async el => {
    const scope = el.dataset.scope;
    try {
      const gone = await deletePaths(scope, [el.dataset.path], $(`#${scope}Task`));
      forgetPaths(scope, gone);
    } catch (e) { fail(e); }
  },
};
function rerenderScope(scope) {
  ({ dl: renderDownloadsBody, fo: renderFoldersBody, du: renderDuplicatesBody, ...SCOPE_RENDER })[scope]();
}

document.addEventListener("click", e => {
  const nav = e.target.closest(".nav");
  if (nav) return go(nav.dataset.page);
  const lang = e.target.closest("[data-lang]");
  if (lang) { S.lang = lang.dataset.lang; api("save_settings", { lang: S.lang }).catch(fail); return renderAll(); }
  const th = e.target.closest("#themeSeg [data-theme]");
  if (th) { S.theme = th.dataset.theme; applyTheme(); applyStatic(); api("save_settings", { theme: S.theme }).catch(fail); return; }
  if (e.target.closest("#btnAdmin")) return api("relaunch_admin").then(ok => { if (!ok) toast(I18N[S.lang].admin.why, true); }).catch(fail);
  const act = e.target.closest("[data-act]");
  if (act && ACTIONS[act.dataset.act]) { e.preventDefault(); ACTIONS[act.dataset.act](act, e); }
});

document.addEventListener("change", e => {
  const el = e.target;
  if (el.dataset.clsel) {
    el.checked ? S.cl.sel.add(el.dataset.clsel) : S.cl.sel.delete(el.dataset.clsel);
    return renderCleanupStats();
  }
  if (el.dataset.perm) {
    S[el.dataset.perm].perm = el.checked;
    return refreshBar(el.dataset.perm);
  }
  if (el.dataset.sel) {
    const scope = el.dataset.sel, st = S[scope], p = el.dataset.path;
    if (el.checked) {
      if (scope === "du") {
        const g = S.du.res.groups[+el.dataset.group];
        if (!g.files.some(f => f.ref) && g.files.every(f => f.path === p || st.sel.has(f.path))) { el.checked = false; return toast(t("dup.need_one"), true); }
      }
      st.sel.add(p);
    } else st.sel.delete(p);
    if (scope === "du") return renderDuplicatesBody();
    return refreshBar(scope);
  }
  if (el.id === "clDrive") { S.cl.drive = el.value; S.cl.result = null; S.cl.report = null; renderCleanup(); }
  if (el.id === "duKeep") S.du.keep = el.value;
  if (el.id === "duRefOn") { S.du.refOn = el.checked; S.du.res = null; renderDuplicates(); }
  CHANGE_HOOKS.forEach(fn => fn(el, e));
});

/* ================================================================ boot */
async function boot() {
  try {
    S.info = await api("info");
    S.lang = S.info.lang;
    S.theme = S.info.theme || "system";
    applyTheme();
    S.drives = await api("drives");
    renderAll();
  } catch (e) {
    document.body.innerHTML = `<pre style="padding:20px">${esc(e.stack || e)}</pre>`;
  }
}
if (NATIVE) window.addEventListener("pywebviewready", boot);
else boot();
