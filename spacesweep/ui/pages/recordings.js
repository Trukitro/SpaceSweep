"use strict";
/* Game recordings / captures page + smart Recycle Bin card (shown inside Cleanup). */

Object.assign(I18N.es, { rec: {
  nav: "Grabaciones", title: "Grabaciones y capturas",
  sub: "Clips y grabaciones de Xbox Game Bar, NVIDIA (ShadowPlay / Instant Replay), OBS Studio y Steam. Se acumulan sin que te des cuenta: aquí ves cuánto ocupan, cuáles son viejas, y las mandas a la Papelera.",
  loading: "Buscando grabaciones…", total: "Grabaciones en total", old: "Con más de 90 días", none: "No se encontraron grabaciones en las carpetas de estas apps.",
  files: "{n} archivos", select_old: "Marcar las de más de 90 días", age: "hace {n} días" },
  rb: { title: "Papelera inteligente", sub: "Vacía solo lo que lleva tiempo en la Papelera y conserva lo que borraste hace poco (por si lo necesitas de vuelta).",
  loading: "Leyendo la Papelera…", total: "{n} elementos · {size}", older: "Más de {d} días", empty_btn: "Vaciar lo de más de {d} días ({size})",
  confirm_t: "¿Vaciar lo de más de {d} días?", confirm_b: "Se borrarán para siempre {n} elementos ({size}). Lo borrado en los últimos {d} días se queda en la Papelera.",
  done: "Liberados {size} ({n} elementos).", nothing: "No hay nada tan viejo en la Papelera.", recent: "Lo más reciente en la Papelera" },
});
Object.assign(I18N.en, { rec: {
  nav: "Recordings", title: "Recordings and captures",
  sub: "Clips and recordings from Xbox Game Bar, NVIDIA (ShadowPlay / Instant Replay), OBS Studio and Steam. They pile up unnoticed: see how much space they take and which are old, and send them to the Recycle Bin.",
  loading: "Looking for recordings…", total: "Recordings in total", old: "Older than 90 days", none: "No recordings found in these apps' folders.",
  files: "{n} files", select_old: "Select those older than 90 days", age: "{n} days ago" },
  rb: { title: "Smart Recycle Bin", sub: "Empties only what has been in the Recycle Bin for a while and keeps what you deleted recently (in case you want it back).",
  loading: "Reading the Recycle Bin…", total: "{n} items · {size}", older: "Older than {d} days", empty_btn: "Empty items older than {d} days ({size})",
  confirm_t: "Empty items older than {d} days?", confirm_b: "{n} items ({size}) will be deleted forever. Anything deleted in the last {d} days stays in the Recycle Bin.",
  done: "Freed {size} ({n} items).", nothing: "Nothing that old in the Recycle Bin.", recent: "Most recent in the Recycle Bin" },
});

S.rc = { res: null, sel: new Set(), sizes: new Map(), perm: false };
S.rbin = { res: null, days: "30" };

function renderRecordings() {
  $("#page-recordings").innerHTML = head(t("rec.title"), t("rec.sub")) +
    `<div class="card"><div class="row"><button class="btn primary" data-act="rc-scan">${icon("game")}${S.rc.res ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="rcTask"></div><div id="rcBody"></div>`;
  renderRecordingsBody();
}

function renderRecordingsBody() {
  const r = S.rc.res, el = $("#rcBody");
  if (!el) return;
  if (!r) { el.innerHTML = ""; return; }
  if (!r.sources.length) { el.innerHTML = `<div class="card">${empty(t("rec.none"))}</div>`; return; }
  let html = `<div class="stats">${stat(t("rec.total"), size(r.total), "", "game")}${stat(t("rec.old"), size(r.sources.reduce((a, s) => a + s.older_90, 0)), "accent", "clock")}</div>
    <div class="card"><div class="row" style="margin-bottom:8px"><button class="btn sm" data-act="rc-old">${t("rec.select_old")}</button>
      <button class="btn ghost sm" data-act="sel-none" data-scope="rc">${t("common.select_none")}</button></div>`;
  for (const s of r.sources) {
    html += `<div class="group"><div class="group-head"><span class="badge b-info">${esc(s.app)}</span><span class="path grow">${esc(pp(s.path))}</span>
      <span class="small muted">${t("rec.files", { n: num(s.count) })} · ${size(s.size)}</span>${openBtn(s.path)}</div>
      ${s.files.slice(0, 60).map(f => `<div class="group-row">${checkbox("rc", f.path)}<span class="path grow">${esc(rel(f.path, s.path))}</span>
        <span class="small ${f.age_days >= 90 ? "badge b-warn" : "muted"}">${t("rec.age", { n: num(f.age_days) })}</span>
        <span class="num small">${size(f.size)}</span>${openBtn(f.path)}</div>`).join("")}</div>`;
  }
  el.innerHTML = html + `<div class="sticky-actions" id="rcBar">${selectionBar("rc")}</div></div>`;
}

/* ---------- smart Recycle Bin card inside Cleanup */
function renderRecycleCard() {
  const box = $("#recycleCard");
  if (!box) return;
  const r = S.rbin.res;
  const days = S.rbin.days;
  let body = !r ? `<button class="btn" data-act="rb-load">${icon("trash")}${I18N[S.lang].common.analyze}</button>` : (() => {
    const b = r.older_than[days] || { count: 0, size: 0 };
    return `<p class="small muted">${t("rb.total", { n: num(r.count), size: size(r.size) })}</p>
      <div class="row"><select id="rbDays">${["7", "30", "90", "365"].map(d => `<option value="${d}" ${d === days ? "selected" : ""}>${t("rb.older", { d })} — ${size((r.older_than[d] || {}).size)}</option>`).join("")}</select>
      <button class="btn primary" data-act="rb-empty" ${b.count ? "" : "disabled"}>${icon("trash")}${t("rb.empty_btn", { d: days, size: size(b.size) })}</button></div>
      ${r.items.length ? `<details style="margin-top:10px"><summary class="small muted">${t("rb.recent")}</summary><div class="subpaths" style="margin-top:6px">${r.items.slice(0, 40).map(i =>
        `<div><span class="path grow">${esc(pp(i.original))}</span><span class="small muted">${t("rec.age", { n: num(i.age_days) })}</span><span class="num small">${size(i.size)}</span></div>`).join("")}</div></details>` : ""}`;
  })();
  box.innerHTML = `<div class="card"><h2>${icon("trash")}${t("rb.title")}</h2><p class="lead">${t("rb.sub")}</p>${body}</div>`;
}

async function recycleLoad() {
  try {
    const res = await runJob(api("recycle_summary"), $("#clTask"), t("rb.loading"));
    if (res) { S.rbin.res = res; renderRecycleCard(); }
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderRecordings);
SCOPE_RENDER.rc = renderRecordingsBody;
FORGET.rc = gone => {
  S.rc.res.sources.forEach(s => { s.files = s.files.filter(f => !gone.has(f.path)); s.count = s.files.length; s.size = s.files.reduce((a, f) => a + f.size, 0);
    s.older_90 = s.files.filter(f => f.age_days >= 90).reduce((a, f) => a + f.size, 0); });
  S.rc.res.total = S.rc.res.sources.reduce((a, s) => a + s.size, 0);
  renderRecordingsBody();
};
Object.assign(ACTIONS, {
  "rc-scan": async () => {
    try {
      const res = await runJob(api("recordings_scan"), $("#rcTask"), t("rec.loading"));
      if (!res) return;
      S.rc.res = res;
      S.rc.sel.clear();
      S.rc.sizes = new Map(res.sources.flatMap(s => s.files.map(f => [f.path, f.size])));
      renderRecordingsBody();
    } catch (e) { fail(e); }
  },
  "rc-old": () => { S.rc.res.sources.forEach(s => s.files.forEach(f => { if (f.age_days >= 90) S.rc.sel.add(f.path); })); renderRecordingsBody(); },
  "rb-load": () => recycleLoad(),
  "rb-empty": async () => {
    const days = +S.rbin.days, b = S.rbin.res.older_than[S.rbin.days];
    const ok = await modal({ title: t("rb.confirm_t", { d: days }), body: `<div class="note warn">${icon("alert")}<div>${t("rb.confirm_b", { n: num(b.count), size: size(b.size), d: days })}</div></div>`,
                             ok: t("rb.empty_btn", { d: days, size: size(b.size) }), okClass: "danger" });
    if (!ok) return;
    try {
      const res = await runJob(api("recycle_empty_older", days), $("#clTask"), I18N[S.lang].common.working);
      if (!res) return;
      res.removed ? toast(t("rb.done", { size: size(res.freed), n: num(res.removed) })) : toast(t("rb.nothing"));
      loadDrives();
      recycleLoad();
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => { if (el.id === "rbDays") { S.rbin.days = el.value; renderRecycleCard(); } });
