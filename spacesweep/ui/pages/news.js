"use strict";
/* What's new: in-app changelog, "updated to vX" notice, and the new-version check. */

Object.assign(I18N.es, { news: {
  nav: "Novedades", title: "Novedades",
  sub: "Qué cambió en cada versión de SpaceSweep. También aquí ves si hay una versión más nueva para descargar.",
  current: "Tienes la versión {v}", latest: "Última publicada: {v}", uptodate: "Estás al día.",
  newer: "Hay una versión nueva: {v}", download_setup: "Descargar instalador", download_portable: "Descargar portátil",
  open_release: "Ver en GitHub", check: "Buscar ahora", checking: "Buscando…", auto_check: "Buscar actualizaciones automáticamente (una vez al día)",
  offline: "No se pudo consultar GitHub ({err}).", updated_t: "SpaceSweep se actualizó a {v}", updated_b: "Esto es lo nuevo desde la versión {from}:",
  pill: "Nueva versión {v}", log: "Historial de cambios", privacy: "La consulta solo pide a GitHub los datos públicos del último release; no envía nada de tu PC." },
});
Object.assign(I18N.en, { news: {
  nav: "What's new", title: "What's new",
  sub: "What changed in each SpaceSweep version. You can also see here whether a newer version is available.",
  current: "You have version {v}", latest: "Latest published: {v}", uptodate: "You're up to date.",
  newer: "A new version is available: {v}", download_setup: "Download installer", download_portable: "Download portable",
  open_release: "View on GitHub", check: "Check now", checking: "Checking…", auto_check: "Check for updates automatically (once a day)",
  offline: "Couldn't reach GitHub ({err}).", updated_t: "SpaceSweep was updated to {v}", updated_b: "Here's what's new since version {from}:",
  pill: "New version {v}", log: "Changelog", privacy: "The check only asks GitHub for the latest release's public data; nothing about your PC is sent." },
});

S.nw = { md: null, upd: null, checking: false };

/* Minimal Markdown: headings, nested lists, paragraphs, **bold**, *em*, `code`, [links]. */
function mdInline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => url.startsWith("https://github.com/Trukitro/SpaceSweep")
      ? `<a href="#" data-act="news-open" data-url="${url}">${text}</a>` : text);
}
function markdown(md) {
  let html = "", depth = 0;
  const close = to => { while (depth > to) { html += "</ul>"; depth--; } };
  for (const raw of md.split(/\r?\n/)) {
    const m = raw.match(/^(\s*)- (.*)$/);
    if (m) {
      const level = Math.floor(m[1].length / 2) + 1;
      while (depth < level) { html += "<ul>"; depth++; }
      close(level);
      html += `<li>${mdInline(m[2])}</li>`;
      continue;
    }
    close(0);
    if (/^### /.test(raw)) html += `<h4>${mdInline(raw.slice(4))}</h4>`;
    else if (/^## /.test(raw)) html += `<h3 class="news-ver">${mdInline(raw.slice(3))}</h3>`;
    else if (/^# /.test(raw)) continue;
    else if (raw.trim()) html += `<p>${mdInline(raw)}</p>`;
  }
  close(0);
  return html;
}
/* Only the sections of versions newer than `from`. */
function changelogSince(md, from) {
  const parts = md.split(/^(?=## )/m).filter(p => p.startsWith("## "));
  const ver = p => (p.match(/\d+\.\d+\.\d+/) || ["0.0.0"])[0].split(".").map(Number);
  const gt = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
  const f = from.split(".").map(Number);
  return parts.filter(p => gt(ver(p), f) > 0).join("\n");
}

function renderNews() {
  const n = S.nw, u = n.upd;
  let status = "";
  if (u && u.error) status = `<p class="muted">${t("news.offline", { err: u.error })}</p>`;
  else if (u && u.newer) status = `<div class="note warn">${icon("download")}<div class="grow"><b>${t("news.newer", { v: u.latest })}</b></div>
      ${u.setup ? `<button class="btn primary sm" data-act="news-open" data-url="${esc(u.setup)}">${t("news.download_setup")}</button>` : ""}
      ${u.portable ? `<button class="btn sm" data-act="news-open" data-url="${esc(u.portable)}">${t("news.download_portable")}</button>` : ""}
      <button class="btn ghost sm" data-act="news-open" data-url="${esc(u.url)}">${t("news.open_release")}</button></div>`;
  else if (u && u.latest) status = `<p>${icon("check")} ${t("news.uptodate")} <span class="muted small">${t("news.latest", { v: u.latest })}</span></p>`;
  const auto = !(S.info && S.info.check_updates === false);
  $("#page-news").innerHTML = head(t("news.title"), t("news.sub")) +
    `<div class="card"><div class="row"><h2 class="grow">${icon("refresh")}${t("news.current", { v: S.info ? S.info.version : "" })}</h2>
      <button class="btn sm" data-act="news-check" ${n.checking ? "disabled" : ""}>${n.checking ? t("news.checking") : t("news.check")}</button></div>${status}
      <label class="row small" style="margin-top:8px"><input type="checkbox" id="nwAuto" ${auto ? "checked" : ""}>${t("news.auto_check")}</label>
      <p class="small muted">${t("news.privacy")}</p></div>
     <div class="card news"><h2>${icon("history")}${t("news.log")}</h2>${n.md === null ? empty(I18N[S.lang].common.working, "clock") : markdown(n.md)}</div>`;
}

function updatePill() {
  const u = S.nw.upd;
  let pill = $("#updatePill");
  if (!(u && u.newer)) { if (pill) pill.remove(); return; }
  if (!pill) {
    pill = document.createElement("button");
    pill.id = "updatePill";
    pill.className = "btn sm primary";
    pill.dataset.act = "nav";
    pill.dataset.page = "news";
    $(".side-foot").prepend(pill);
  }
  pill.innerHTML = `${icon("download")}${t("news.pill", { v: u.latest })}`;
}

async function newsCheck(force) {
  S.nw.checking = true;
  if (S.page === "news") renderNews();
  try { S.nw.upd = await api("update_check", !!force); } catch (e) { S.nw.upd = { error: e.message }; }
  S.nw.checking = false;
  updatePill();
  renderNews();
}

PAGE_RENDERERS.push(() => { renderNews(); updatePill(); });
PAGE_ENTER.news = async () => {
  if (S.nw.md === null) { S.nw.md = await api("changelog").catch(() => ""); renderNews(); }
};
BOOT_HOOKS.push(async () => {
  try {
    const wn = await api("whats_new");
    if (wn) {
      S.nw.md = await api("changelog");
      const since = changelogSince(S.nw.md, wn.from);
      modal({ title: t("news.updated_t", { v: wn.to }), body: `<p class="muted">${t("news.updated_b", { from: wn.from })}</p><div class="news">${markdown(since)}</div>`,
              ok: t("common.close"), cancel: false });
    }
  } catch (e) { console.error(e); }
  if (!(S.info && S.info.check_updates === false)) newsCheck(false);
});
Object.assign(ACTIONS, {
  "news-check": () => newsCheck(true),
  "news-open": el => api("open_url", el.dataset.url).catch(fail),
});
CHANGE_HOOKS.push(el => {
  if (el.id === "nwAuto") { S.info.check_updates = el.checked; api("save_settings", { check_updates: el.checked }).catch(fail); }
});
