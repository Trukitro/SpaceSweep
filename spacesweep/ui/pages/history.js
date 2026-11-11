"use strict";
/* History page: "what grew since last time?" */

Object.assign(I18N.es, { hist: {
  nav: "Historial", title: "Historial de espacio",
  sub: "Cada vez que analizas un disco o una carpeta, SpaceSweep guarda un resumen pequeño. Aquí comparas dos fechas y ves exactamente qué creció, para que el disco no se vuelva a llenar sin saber por qué.",
  tracked: "Disco o carpeta", older: "Desde", newer: "Hasta", new_scan: "Nuevo análisis de {d}", scanning: "Analizando para el historial…",
  empty: "Todavía no hay historial. Analiza un disco aquí o en «Explorar disco» y vuelve otro día: verás qué creció entre un análisis y otro.",
  one: "Solo hay un análisis de esta ubicación. Haz otro más adelante (o ahora mismo) para comparar.",
  before: "Antes", now: "Ahora", change: "Cambio", grew: "Lo que más creció", shrank: "Lo que se redujo",
  grew_d: "Se muestra la carpeta más específica que explica el cambio. Solo carpetas de 50 MB o más.",
  new: "nuevo", small: "< 50 MB", free_chart: "Espacio usado en {d}", points: "{n} mediciones desde {date}",
  caches: "Cachés que se vuelven a llenar", caches_d: "Crecimiento desde el análisis de Limpieza en que estaban más vacías ({date}).",
  no_caches: "Analiza la Limpieza un par de veces (días distintos) para ver qué cachés crecen más rápido.",
  home_card: "Desde el {date}, el espacio usado en {d} cambió {delta}.", home_link: "Ver qué creció" },
});
Object.assign(I18N.en, { hist: {
  nav: "History", title: "Space history",
  sub: "Every time you analyze a drive or folder, SpaceSweep keeps a small summary. Compare two dates here and see exactly what grew, so the drive never fills up again without you knowing why.",
  tracked: "Drive or folder", older: "From", newer: "To", new_scan: "New analysis of {d}", scanning: "Analyzing for history…",
  empty: "No history yet. Analyze a drive here or in Disk explorer and come back another day: you'll see what grew between analyses.",
  one: "There's only one analysis of this location. Run another later (or now) to compare.",
  before: "Before", now: "Now", change: "Change", grew: "What grew most", shrank: "What shrank",
  grew_d: "Shows the most specific folder that explains the change. Only folders of 50 MB or more.",
  new: "new", small: "< 50 MB", free_chart: "Used space on {d}", points: "{n} measurements since {date}",
  caches: "Caches that keep refilling", caches_d: "Growth since the Cleanup analysis where they were emptiest ({date}).",
  no_caches: "Run the Cleanup analysis a couple of times (on different days) to see which caches grow fastest.",
  home_card: "Since {date}, used space on {d} changed by {delta}.", home_link: "See what grew" },
});

S.hi = { roots: null, key: null, cmp: null, older: null, newer: null, free: [], rules: null };

const signed = b => (b > 0 ? "+" : b < 0 ? "−" : "") + size(Math.abs(b));
const hiDrive = root => (root && /^[A-Za-z]:\\?$/.test(root) ? root.slice(0, 2).toUpperCase() + "\\" : null);

function renderHistory() {
  const h = S.hi;
  const sys = S.drives.find(d => d.system);
  const rootOpts = (h.roots || []).map(r => `<option value="${r.key}" ${r.key === h.key ? "selected" : ""}>${esc(pp(r.root))} · ${num(r.count)}</option>`).join("");
  const snaps = h.cmp ? h.cmp.snapshots : [];
  const snapOpts = sel => snaps.map(s => `<option value="${s.id}" ${s.id === sel ? "selected" : ""}>${new Date(s.time * 1000).toLocaleString()} · ${size(s.total)}</option>`).join("");
  $("#page-history").innerHTML = head(t("hist.title"), t("hist.sub")) +
    `<div class="card"><div class="row">
      ${h.roots && h.roots.length ? `<label class="muted">${t("hist.tracked")}</label><select id="hiRoot">${rootOpts}</select>` : ""}
      ${snaps.length > 1 ? `<label class="muted">${t("hist.older")}</label><select id="hiOlder">${snapOpts(h.cmp.older && h.cmp.older.id)}</select>
        <label class="muted">${t("hist.newer")}</label><select id="hiNewer">${snapOpts(h.cmp.newer.id)}</select>` : ""}
      <span class="grow"></span>
      ${sys ? `<button class="btn primary" data-act="hi-scan" data-root="${esc(sys.root)}">${icon("pie")}${t("hist.new_scan", { d: sys.letter + ":" })}</button>` : ""}
      ${h.cmp && !hiDrive(h.cmp.root) ? `<button class="btn" data-act="hi-scan" data-root="${esc(h.cmp.root)}">${icon("refresh")}${t("hist.new_scan", { d: base(h.cmp.root) })}</button>` : ""}
    </div></div><div class="task hidden" id="hiTask"></div><div id="hiBody"></div>`;
  renderHistoryBody();
}

function sparkline(points) {
  if (points.length < 2) return "";
  const W = 640, H = 120, pad = 6;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = x => pad + (x - x0) / Math.max(1, x1 - x0) * (W - 2 * pad);
  const sy = y => H - pad - (y - y0) / Math.max(1, y1 - y0) * (H - 2 * pad);
  const line = points.map(p => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:120px" preserveAspectRatio="none" role="img">
    <polygon points="${sx(x0)},${H - pad} ${line} ${sx(x1)},${H - pad}" fill="var(--accent)" opacity=".12"/>
    <polyline points="${line}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>
    <div class="row small muted"><span>${date(x0)}</span><span class="grow"></span><span>${size(y0)} – ${size(y1)}</span><span class="grow"></span><span>${date(x1)}</span></div>`;
}

function historyTable(rows, root) {
  if (!rows.length) return empty(t("common.none"));
  const max = Math.max(...rows.map(r => Math.abs(r.delta)));
  return `<div class="tbl-wrap"><table><thead><tr><th>${t("common.path")}</th><th class="num">${t("hist.before")}</th><th class="num">${t("hist.now")}</th>
    <th class="num">${t("hist.change")}</th><th style="width:22%"></th><th></th></tr></thead><tbody>${rows.map(r => `<tr>
    <td><div class="path" style="color:var(--text)" title="${esc(r.full)}">${esc(pp(r.full))}</div></td>
    <td class="num">${r.before == null ? `<span class="badge b-muted">${r.after != null ? t("hist.new") : t("hist.small")}</span>` : size(r.before)}</td>
    <td class="num">${r.after == null ? `<span class="badge b-muted">${t("hist.small")}</span>` : size(r.after)}</td>
    <td class="num"><b style="color:${r.delta > 0 ? "var(--danger)" : "var(--safe)"}">${signed(r.delta)}</b></td>
    <td><div class="bar ${r.delta > 0 ? "low" : ""}"><i style="width:${(Math.abs(r.delta) / max * 100).toFixed(1)}%"></i></div></td>
    <td class="act">${openBtn(r.full)}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderHistoryBody() {
  const h = S.hi, el = $("#hiBody");
  if (!el) return;
  if (!h.roots) { el.innerHTML = ""; return; }
  if (!h.roots.length) { el.innerHTML = `<div class="card">${empty(t("hist.empty"), "history")}</div>`; return; }
  const c = h.cmp;
  let html = "";
  const drive = c && hiDrive(c.root);
  if (drive && h.free.length > 1) {
    html += `<div class="card"><h2>${icon("disk")}${t("hist.free_chart", { d: drive })}</h2>
      <p class="lead small">${t("hist.points", { n: num(h.free.length), date: date(h.free[0][0]) })}</p>${sparkline(h.free)}</div>`;
  }
  if (c && c.older) {
    html += `<div class="stats">${stat(t("hist.before") + " · " + date(c.older.time), size(c.older.total), "", "clock")}
      ${stat(t("hist.now") + " · " + date(c.newer.time), size(c.newer.total), "", "pie")}
      ${stat(t("hist.change"), signed(c.delta), c.delta > 0 ? "warn" : "accent", "history")}</div>
      <div class="card"><h2>${icon("alert")}${t("hist.grew")}</h2><p class="lead">${t("hist.grew_d")}</p>${historyTable(c.grew, c.root)}</div>
      ${c.shrank.length ? `<div class="card"><h2>${icon("check")}${t("hist.shrank")}</h2>${historyTable(c.shrank.slice(0, 30), c.root)}</div>` : ""}`;
  } else if (c) {
    html += `<div class="card">${empty(t("hist.one"), "history")}</div>`;
  }
  if (drive && h.rules) {
    const r = h.rules;
    html += `<div class="card"><h2>${icon("refresh")}${t("hist.caches")}</h2>` + (r.items.length
      ? `<p class="lead">${t("hist.caches_d", { date: date(r.since) })}</p><div class="tbl-wrap"><table><tbody>${r.items.map(i => `<tr>
          <td><b>${L(i.name)}</b></td><td class="num">${size(i.before)} → ${size(i.after)}</td>
          <td class="num"><b style="color:var(--danger)">${signed(i.delta)}</b></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">${t("hist.no_caches")}</p>`) + `</div>`;
  }
  el.innerHTML = html;
}

async function historyLoad(key) {
  const h = S.hi;
  try {
    h.roots = await api("history_roots");
    if (!h.roots.length) { h.cmp = null; return renderHistory(); }
    const sysRoot = (S.drives.find(d => d.system) || {}).root;
    h.key = key || h.key || (h.roots.find(r => r.root.toUpperCase() === (sysRoot || "").toUpperCase()) || h.roots[0]).key;
    if (!h.roots.some(r => r.key === h.key)) h.key = h.roots[0].key;
    h.cmp = await api("history_compare", h.key, h.older, h.newer);
    const drive = hiDrive(h.cmp.root);
    h.free = drive ? await api("history_free", drive) : [];
    h.rules = drive ? await api("history_rules", drive) : null;
    renderHistory();
  } catch (e) { fail(e); }
}

async function historyScan(root) {
  try {
    const res = await runJob(api("disk_scan", root), $("#hiTask"), t("hist.scanning"));
    if (!res) return;
    S.hi.older = S.hi.newer = null;
    S.hi.key = null;
    await historyLoad();
    const match = S.hi.roots.find(r => r.root.toUpperCase() === res.root.toUpperCase());
    if (match && match.key !== S.hi.key) await historyLoad(match.key);
  } catch (e) { fail(e); }
}

/* Home page hint: how much used space changed in the last week. */
async function historyHomeHint() {
  const sys = S.drives.find(d => d.system);
  if (!sys) return;
  try {
    const ch = await api("history_used_change", sys.root, 7);
    const box = $("#homeHint");
    if (!box || !ch || Math.abs(ch.delta) < 1 << 30) return;
    box.innerHTML = `<div class="note ${ch.delta > 0 ? "warn" : ""}">${icon("history")}<div class="grow">${t("hist.home_card", { date: date(ch.since), d: sys.letter + ":", delta: signed(ch.delta) })}</div>
      <button class="btn sm" data-act="nav" data-page="history">${t("hist.home_link")}</button></div>`;
  } catch (e) { /* the hint is optional */ }
}

PAGE_RENDERERS.push(renderHistory);
PAGE_ENTER.history = () => historyLoad();
PAGE_ENTER.home = historyHomeHint;
Object.assign(ACTIONS, {
  "hi-scan": el => historyScan(el.dataset.root),
});
CHANGE_HOOKS.push(el => {
  if (el.id === "hiRoot") { S.hi.older = S.hi.newer = null; historyLoad(el.value); }
  if (el.id === "hiOlder") { S.hi.older = +el.value; historyLoad(); }
  if (el.id === "hiNewer") { S.hi.newer = +el.value; historyLoad(); }
});
