"use strict";
/* Developer projects page: regenerable folders in code projects, by inactivity. */

Object.assign(I18N.es, { proj: {
  nav: "Proyectos", title: "Proyectos de programación",
  sub: "Busca proyectos de código y sus carpetas regenerables: dependencias (node_modules), entornos virtuales de Python, compilaciones (Rust target, .NET bin/obj) y cachés. Si no tocas un proyecto hace meses, esas carpetas solo ocupan espacio: se recrean con un comando cuando vuelvas.",
  roots: "Carpetas donde buscar", inactive: "Inactivo después de", days: "{n} días", search: "Buscar proyectos", scanning: "Buscando proyectos…",
  total: "Regenerable en total", inactive_total: "En proyectos inactivos", count: "Proyectos con algo que limpiar",
  perm_note: "Estas carpetas se borran permanentemente: se recrean con el comando indicado, y mandarlas a la Papelera no liberaría espacio.",
  project: "Proyecto", last: "Última actividad", junk: "Regenerable", contents: "Contenido", idle: "hace {n} días", never: "sin archivos propios",
  inactive_b: "Inactivo", active_b: "Activo", regen: "Para recrearlo:", auto_regen: "se regenera solo", review: "Revisar: puede ser una versión publicada",
  none: "No se encontraron carpetas regenerables en estas ubicaciones.", del_btn: "Borrar {n} carpetas ({size})",
  k_node_modules: "Dependencias de Node", k_venv: "Entorno virtual de Python", k_pycache: "Caché de Python", k_build_cache: "Compilación / caché de build", k_dist: "Build / dist de Python" },
});
Object.assign(I18N.en, { proj: {
  nav: "Projects", title: "Code projects",
  sub: "Finds code projects and their regenerable folders: dependencies (node_modules), Python virtual environments, build output (Rust target, .NET bin/obj) and caches. If you haven't touched a project in months, those folders just take space: one command recreates them when you come back.",
  roots: "Folders to search", inactive: "Inactive after", days: "{n} days", search: "Find projects", scanning: "Looking for projects…",
  total: "Regenerable in total", inactive_total: "In inactive projects", count: "Projects with something to clean",
  perm_note: "These folders are deleted permanently: the command shown recreates them, and the Recycle Bin wouldn't free any space.",
  project: "Project", last: "Last activity", junk: "Regenerable", contents: "Contents", idle: "{n} days ago", never: "no own files",
  inactive_b: "Inactive", active_b: "Active", regen: "To recreate:", auto_regen: "rebuilt automatically", review: "Review: may be a published release",
  none: "No regenerable folders found in these locations.", del_btn: "Delete {n} folders ({size})",
  k_node_modules: "Node dependencies", k_venv: "Python virtual environment", k_pycache: "Python cache", k_build_cache: "Build output / cache", k_dist: "Python build / dist" },
});

S.pr = { roots: null, days: "90", res: null, sel: new Set(), sizes: new Map(), perm: true, open: new Set() };

function renderProjects() {
  const p = S.pr;
  const roots = p.roots || [];
  const dayOpts = ["30", "60", "90", "180", "365"].map(d => `<option value="${d}" ${p.days === d ? "selected" : ""}>${t("proj.days", { n: d })}</option>`).join("");
  $("#page-projects").innerHTML = head(t("proj.title"), t("proj.sub")) +
    `<div class="card"><h2>${t("proj.roots")}</h2>
      <div class="row" style="margin:8px 0 12px">${roots.map((r, i) => `<span class="chip on">${icon("folder")}<span class="mono">${esc(pp(r))}</span>
        <span class="x" data-act="pr-rm" data-i="${i}">${icon("x")}</span></span>`).join("")}
        <button class="chip" data-act="pr-add">${icon("plus")}${t("dup.add")}</button></div>
      <div class="row"><label class="muted">${t("proj.inactive")}</label><select id="prDays">${dayOpts}</select><span class="grow"></span>
        <button class="btn primary" data-act="pr-scan" ${roots.length ? "" : "disabled"}>${icon("code")}${t("proj.search")}</button></div></div>
     <div class="task hidden" id="prTask"></div><div id="prBody"></div>`;
  renderProjectsBody();
}

/* One chip per folder name: "__pycache__ ×12 · 1.2 MB" instead of twelve chips. */
function prJunkChips(junk) {
  const groups = new Map();
  junk.forEach(j => {
    const k = base(j.path);
    const g = groups.get(k) || { name: k, n: 0, size: 0, review: j.review };
    g.n++; g.size += j.size;
    groups.set(k, g);
  });
  return [...groups.values()].sort((a, b) => b.size - a.size).map(g =>
    `<span class="badge ${g.review ? "b-warn" : "b-muted"}">${esc(g.name)}${g.n > 1 ? ` ×${g.n}` : ""} · ${size(g.size)}</span>`).join("");
}

function renderProjectsBody() {
  const p = S.pr, el = $("#prBody");
  if (!el) return;
  if (!p.res) { el.innerHTML = ""; return; }
  const r = p.res;
  if (!r.projects.length) { el.innerHTML = `<div class="card">${empty(t("proj.none"))}</div>`; return; }
  let html = `<div class="stats">${stat(t("proj.total"), size(r.total), "", "code")}${stat(t("proj.inactive_total"), size(r.inactive_total), "accent", "clock")}
    ${stat(t("proj.count"), num(r.projects.length), "", "folder")}</div>
    <div class="note">${icon("infoc")}<div>${t("proj.perm_note")}</div></div>
    <div class="card"><div class="row" style="margin-bottom:8px"><button class="btn ghost sm" data-act="sel-all" data-scope="pr">${t("common.select_all")}</button>
      <button class="btn ghost sm" data-act="sel-none" data-scope="pr">${t("common.select_none")}</button></div>
    <div class="tbl-wrap"><table><thead><tr><th class="chk"></th><th>${t("proj.project")}</th><th>${t("proj.last")}</th><th class="num">${t("proj.junk")}</th>
      <th>${t("proj.contents")}</th><th></th></tr></thead><tbody>`;
  r.projects.forEach((pr, i) => {
    const items = pr.junk.filter(j => !j.review);
    const all = items.length && items.every(j => p.sel.has(j.path));
    const some = items.some(j => p.sel.has(j.path));
    html += `<tr><td class="chk"><input type="checkbox" data-prproj="${i}" ${all ? "checked" : ""} ${!all && some ? "data-mixed" : ""}></td>
      <td class="what"><b>${esc(pr.name)}</b><span class="path">${esc(pp(pr.path))}</span>
        <div class="row" style="margin-top:4px">${pr.kinds.filter(k => k !== "other").map(k => `<span class="badge b-info">${esc(k)}</span>`).join("")}</div></td>
      <td>${pr.idle_days == null ? `<span class="muted small">${t("proj.never")}</span>` : `${t("proj.idle", { n: num(pr.idle_days) })}`}
        <div><span class="badge ${pr.inactive ? "b-warn" : "b-safe"}">${pr.inactive ? t("proj.inactive_b") : t("proj.active_b")}</span></div></td>
      <td class="num"><b>${size(pr.junk_size)}</b></td>
      <td><div class="row">${prJunkChips(pr.junk)}</div></td>
      <td class="act"><button class="btn ghost sm" data-act="pr-open" data-i="${i}">${p.open.has(i) ? t("cleanup.hide") : t("cleanup.details")}</button>${openBtn(pr.path)}</td></tr>`;
    if (p.open.has(i)) {
      html += `<tr class="details-row"><td></td><td colspan="5"><div class="subpaths">${pr.junk.map(j => `<div>${checkbox("pr", j.path)}
        <span class="path">${esc(pp(j.path))}</span><span class="small">${t("proj.k_" + j.kind)}</span>
        <span class="small muted">${j.review ? t("proj.review") : j.regen ? `${t("proj.regen")} <code>${esc(j.regen)}</code>` : t("proj.auto_regen")}</span>
        <span class="num small">${size(j.size)}</span></div>`).join("")}</div></td></tr>`;
    }
  });
  html += `</tbody></table></div><div class="sticky-actions" id="prBar">${prBar()}</div></div>`;
  el.innerHTML = html;
  $$("[data-mixed]", el).forEach(cb => { cb.indeterminate = true; });
}

function prBar() {
  const p = S.pr;
  let bytes = 0;
  p.sel.forEach(x => { bytes += p.sizes.get(x) || 0; });
  return `<span class="grow"><b>${num(p.sel.size)}</b> · ${size(bytes)}</span>
    <button class="btn danger" data-act="del-sel" data-scope="pr" ${p.sel.size ? "" : "disabled"}>${icon("trash")}${t("proj.del_btn", { n: num(p.sel.size), size: size(bytes) })}</button>`;
}

async function projectsScan() {
  const p = S.pr;
  p.days = $("#prDays").value;
  try {
    const res = await runJob(api("dev_scan", p.roots, +p.days), $("#prTask"), t("proj.scanning"));
    if (!res) return;
    p.res = res;
    p.open.clear();
    p.sizes = new Map(res.projects.flatMap(pr => pr.junk.map(j => [j.path, j.size])));
    p.sel = new Set(res.projects.filter(pr => pr.inactive).flatMap(pr => pr.junk.filter(j => !j.review).map(j => j.path)));
    renderProjectsBody();
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderProjects);
PAGE_ENTER.projects = async () => {
  if (S.pr.roots === null) {
    try { S.pr.roots = await api("dev_roots"); } catch (e) { S.pr.roots = []; fail(e); }
    renderProjects();
  }
};
SCOPE_RENDER.pr = renderProjectsBody;
BARS.pr = prBar;
FORGET.pr = gone => {
  const r = S.pr.res;
  r.projects.forEach(pr => { pr.junk = pr.junk.filter(j => !gone.has(j.path)); pr.junk_size = pr.junk.reduce((a, j) => a + j.size, 0); });
  r.projects = r.projects.filter(pr => pr.junk.length);
  r.total = r.projects.reduce((a, pr) => a + pr.junk_size, 0);
  r.inactive_total = r.projects.filter(pr => pr.inactive).reduce((a, pr) => a + pr.junk.filter(j => !j.review).reduce((b, j) => b + j.size, 0), 0);
  renderProjectsBody();
};
Object.assign(ACTIONS, {
  "pr-scan": () => projectsScan(),
  "pr-add": async () => { const f = await pickFolder(); if (f && !S.pr.roots.includes(f)) { S.pr.roots.push(f); renderProjects(); } },
  "pr-rm": el => { S.pr.roots.splice(+el.dataset.i, 1); renderProjects(); },
  "pr-open": el => { const i = +el.dataset.i; S.pr.open.has(i) ? S.pr.open.delete(i) : S.pr.open.add(i); renderProjectsBody(); },
});
CHANGE_HOOKS.push(el => {
  if (el.dataset.prproj !== undefined) {
    const pr = S.pr.res.projects[+el.dataset.prproj];
    pr.junk.filter(j => !j.review).forEach(j => (el.checked ? S.pr.sel.add(j.path) : S.pr.sel.delete(j.path)));
    renderProjectsBody();
  }
  if (el.id === "prDays") S.pr.days = el.value;
});
