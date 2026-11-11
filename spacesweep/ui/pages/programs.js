"use strict";
/* Installed programs: size, install date, repeated versions, uninstall through the program's own uninstaller. */

Object.assign(I18N.es, { prog: {
  nav: "Programas", title: "Programas instalados",
  sub: "Todos tus programas con su tamaño y fecha de instalación. Detecta versiones repetidas (como varios SQL Server Management Studio) y te dice cuáles son normales y cuáles sobran. Desinstalar siempre usa el desinstalador del propio programa.",
  loading: "Leyendo programas instalados…", total: "Ocupan en {d}", count: "Programas", repeated: "Versiones repetidas",
  groups: "Versiones repetidas", groups_d: "Programas instalados más de una vez. Revisa cada grupo antes de desinstalar.",
  keep_vcredist: "No desinstales: cada programa usa su propia versión de Visual C++.",
  keep_runtime: "No desinstales: son componentes que otros programas necesitan.",
  older_ok: "Normalmente basta la más nueva; las anteriores se pueden desinstalar si no las usas.",
  newest: "más nueva", older: "anterior", list: "Todos los programas", search: "Buscar…", drive: "Disco", all: "Todos",
  show_games: "Incluir juegos", version: "Versión", publisher: "Editor", installed: "Instalado", uninstall: "Desinstalar",
  confirm_t: "¿Desinstalar {name}?", confirm_b: "Se abrirá el desinstalador del propio programa. Puede pedir permisos de administrador y hacerte preguntas: síguelo hasta el final. Cuando termine, vuelve a analizar.",
  launched: "Desinstalador abierto.", not_launched: "No se pudo abrir el desinstalador. Usa Aplicaciones de Windows.", open_apps: "Abrir Aplicaciones de Windows",
  unknown: "—", measured: "medido" },
});
Object.assign(I18N.en, { prog: {
  nav: "Programs", title: "Installed programs",
  sub: "All your programs with size and install date. Spots repeated versions (like several SQL Server Management Studio) and tells you which are normal and which are leftovers. Uninstalling always uses the program's own uninstaller.",
  loading: "Reading installed programs…", total: "Use on {d}", count: "Programs", repeated: "Repeated versions",
  groups: "Repeated versions", groups_d: "Programs installed more than once. Review each group before uninstalling.",
  keep_vcredist: "Don't uninstall: each program uses its own Visual C++ version.",
  keep_runtime: "Don't uninstall: other programs need these components.",
  older_ok: "Usually only the newest is needed; older ones can go if you don't use them.",
  newest: "newest", older: "older", list: "All programs", search: "Search…", drive: "Drive", all: "All",
  show_games: "Include games", version: "Version", publisher: "Publisher", installed: "Installed", uninstall: "Uninstall",
  confirm_t: "Uninstall {name}?", confirm_b: "The program's own uninstaller will open. It may ask for administrator rights and ask questions: follow it to the end. Analyze again when it finishes.",
  launched: "Uninstaller opened.", not_launched: "Could not open the uninstaller. Use Windows Apps settings.", open_apps: "Open Windows Apps settings",
  unknown: "—", measured: "measured" },
});

S.pg = { res: null, q: "", drive: null, games: false, shown: 80 };

function renderPrograms() {
  const g = S.pg;
  if (!g.drive) g.drive = ((S.drives.find(d => d.system) || {}).letter || "C") + ":";
  $("#page-programs").innerHTML = head(t("prog.title"), t("prog.sub")) +
    `<div class="card"><div class="row"><button class="btn primary" data-act="pg-scan">${icon("app")}${g.res ? t("common.reanalyze") : t("common.analyze")}</button>
      <button class="btn" data-act="tool" data-tool="apps">${icon("open")}${t("prog.open_apps")}</button></div></div>
     <div class="task hidden" id="pgTask"></div><div id="pgBody"></div>`;
  renderProgramsBody();
}

function pgRow(p, extra = "") {
  return `<tr><td class="what"><b>${esc(p.name)}</b>${extra}<span>${esc(p.publisher)}</span></td><td class="small">${esc(p.version)}</td>
    <td class="small">${esc(p.installed) || t("prog.unknown")}</td><td class="num">${p.size ? size(p.size) : "—"}</td><td class="small">${esc(p.drive)}</td>
    <td class="act">${p.location ? openBtn(p.location) : ""}${p.uninstall ? `<button class="btn sm" data-act="pg-uninstall" data-id="${esc(p.id)}">${t("prog.uninstall")}</button>` : ""}</td></tr>`;
}

function renderProgramsBody() {
  const g = S.pg, el = $("#pgBody");
  if (!el) return;
  if (!g.res) { el.innerHTML = `<div class="card">${empty(t("prog.sub"), "app")}</div>`; return; }
  const all = g.res.programs;
  const byId = new Map(all.map(p => [p.id, p]));
  const onDrive = all.filter(p => !p.game && p.drive === g.drive);
  let html = `<div class="stats">${stat(t("prog.total", { d: g.drive }), size(onDrive.reduce((a, p) => a + (p.size || 0), 0)), "", "disk")}
    ${stat(t("prog.count"), num(all.filter(p => !p.game).length), "", "app")}
    ${stat(t("prog.repeated"), num(g.res.groups.filter(x => !x.keep_all).length), "accent", "copy")}</div>`;
  if (g.res.groups.length) {
    html += `<div class="card"><h2>${icon("copy")}${t("prog.groups")}</h2><p class="lead">${t("prog.groups_d")}</p>`;
    for (const grp of g.res.groups) {
      const note = grp.keep_all ? `<span class="badge b-info wrap">${t("prog.keep_" + grp.keep_all)}</span>` : `<span class="badge b-warn wrap">${t("prog.older_ok")}</span>`;
      html += `<div class="group"><div class="group-head"><b class="grow">${esc(grp.family)} · ${num(grp.count)}</b>${note}<span class="muted small">${size(grp.size)}</span></div>
        ${grp.ids.map((id, i) => { const p = byId.get(id); return `<div class="group-row ${i === 0 ? "keep" : ""}"><span class="grow">${esc(p.name)}
          <span class="small muted">${esc(p.version)}</span></span>${grp.keep_all ? "" : `<span class="badge ${i === 0 ? "b-safe" : "b-muted"}">${i === 0 ? t("prog.newest") : t("prog.older")}</span>`}
          <span class="small muted">${p.size ? size(p.size) : ""}</span>${!grp.keep_all && i > 0 && p.uninstall ? `<button class="btn sm" data-act="pg-uninstall" data-id="${esc(p.id)}">${t("prog.uninstall")}</button>` : ""}</div>`; }).join("")}</div>`;
    }
    html += `</div>`;
  }
  const drives = [...new Set(all.map(p => p.drive).filter(Boolean))].sort();
  const q = g.q.toLowerCase();
  const list = all.filter(p => (g.games || !p.game) && (g.drive === "*" || p.drive === g.drive || !p.drive) &&
    (!q || p.name.toLowerCase().includes(q) || p.publisher.toLowerCase().includes(q)));
  html += `<div class="card"><div class="row" style="margin-bottom:12px"><h2 class="grow">${icon("app")}${t("prog.list")} <span class="muted small">(${num(list.length)})</span></h2>
      <input type="text" id="pgSearch" placeholder="${esc(I18N[S.lang].prog.search)}" value="${esc(g.q)}" style="width:220px">
      <label class="muted">${t("prog.drive")}</label><select id="pgDrive"><option value="*">${t("prog.all")}</option>${drives.map(d => `<option ${d === g.drive ? "selected" : ""}>${esc(d)}</option>`).join("")}</select>
      <label class="row small"><input type="checkbox" id="pgGames" ${g.games ? "checked" : ""}>${t("prog.show_games")}</label></div>
    <div class="tbl-wrap"><table><thead><tr><th>${t("common.name")}</th><th>${t("prog.version")}</th><th>${t("prog.installed")}</th>
      <th class="num">${t("common.size")}</th><th>${t("prog.drive")}</th><th></th></tr></thead><tbody>${list.slice(0, g.shown).map(p => pgRow(p)).join("")}</tbody></table></div>
    ${list.length > g.shown ? `<button class="btn" style="margin-top:10px" data-act="pg-more">${t("common.show_more")} (${num(list.length - g.shown)})</button>` : ""}</div>`;
  el.innerHTML = html;
}

async function programsScan() {
  try {
    const res = await runJob(api("inv_programs"), $("#pgTask"), t("prog.loading"));
    if (res) { S.pg.res = res; S.pg.shown = 80; renderPrograms(); }
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderPrograms);
PAGE_ENTER.programs = () => { if (!S.pg.res) programsScan(); };
Object.assign(ACTIONS, {
  "pg-scan": () => programsScan(),
  "pg-more": () => { S.pg.shown += 200; renderProgramsBody(); },
  "pg-uninstall": async el => {
    const p = S.pg.res.programs.find(x => x.id === el.dataset.id);
    if (!p) return;
    const ok = await modal({ title: t("prog.confirm_t", { name: p.name }), body: `<p>${t("prog.confirm_b")}</p>`, ok: t("prog.uninstall") });
    if (!ok) return;
    try {
      toast((await api("inv_uninstall", p.id, p.uninstall)) ? t("prog.launched") : t("prog.not_launched"), false);
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => {
  if (el.id === "pgDrive") { S.pg.drive = el.value; renderProgramsBody(); }
  if (el.id === "pgGames") { S.pg.games = el.checked; renderProgramsBody(); }
});
document.addEventListener("input", e => {
  if (e.target.id === "pgSearch") {
    S.pg.q = e.target.value;
    clearTimeout(S.pg.timer);
    S.pg.timer = setTimeout(() => { const pos = e.target.selectionStart; renderProgramsBody(); const f = $("#pgSearch"); f.focus(); f.setSelectionRange(pos, pos); }, 200);
  }
});
