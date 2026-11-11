"use strict";
/* v0.9: duplicates -> hard links, Explorer right-click entry, restore points. */

Object.assign(I18N.es, { intg: {
  link_btn: "Reemplazar por enlaces duros", link_t: "¿Reemplazar {n} copias por enlaces duros?",
  link_b: "Cada copia seleccionada pasa a ser el mismo archivo que la que se conserva: ambas rutas siguen funcionando y el espacio se libera, sin Papelera.",
  link_warn: "Úsalo solo con archivos que no se editan (instaladores, fotos, videos, zips). Si editas uno, cambian los dos. Solo funciona dentro del mismo disco.",
  linked: "{n} copias enlazadas ({size} liberados).", link_failed: "{n} no se pudieron enlazar (otro disco o cambiaron).",
  shell: "Integración con el Explorador", shell_d: "Añade «Analizar con SpaceSweep» al clic derecho de carpetas y discos. En Windows 11 aparece en «Mostrar más opciones». No necesita administrador y se quita al desinstalar.",
  shell_on: "Añadido al menú del Explorador.", shell_off: "Quitado del menú del Explorador.",
  rp: "Puntos de restauración", rp_d: "Copias del sistema para volver atrás si algo falla. Conserva al menos uno reciente; los viejos se pueden borrar para recuperar espacio.",
  rp_list: "Ver puntos de restauración", rp_none: "No hay puntos de restauración.", rp_used: "Usan {used} (máximo permitido {max})",
  rp_delete: "Borrar el más viejo", rp_t: "¿Borrar el punto de restauración más viejo?", rp_b: "Se borra solo el más antiguo ({date}). Los demás se conservan. No se puede deshacer.",
  rp_done: "Borrado. Quedan {n} puntos ({size} liberados).", rp_admin: "Requiere administrador: reinicia SpaceSweep como administrador.",
  rp_settings: "Configurar espacio máximo", opening: "Abriendo {path}…" },
});
Object.assign(I18N.en, { intg: {
  link_btn: "Replace with hard links", link_t: "Replace {n} copies with hard links?",
  link_b: "Each selected copy becomes the same file as the one you keep: both paths keep working and the space is freed, no Recycle Bin involved.",
  link_warn: "Only for files that aren't edited (installers, photos, videos, zips). Editing one changes both. Works only within the same drive.",
  linked: "{n} copies linked ({size} freed).", link_failed: "{n} couldn't be linked (other drive or changed).",
  shell: "Explorer integration", shell_d: "Adds \"Analyze with SpaceSweep\" to the right-click menu of folders and drives. On Windows 11 it's under \"Show more options\". No administrator needed; removed on uninstall.",
  shell_on: "Added to the Explorer menu.", shell_off: "Removed from the Explorer menu.",
  rp: "Restore points", rp_d: "System snapshots to roll back if something breaks. Keep at least one recent one; old ones can go to recover space.",
  rp_list: "Show restore points", rp_none: "No restore points.", rp_used: "Using {used} (max allowed {max})",
  rp_delete: "Delete the oldest", rp_t: "Delete the oldest restore point?", rp_b: "Only the oldest ({date}) is deleted. The others stay. This can't be undone.",
  rp_done: "Deleted. {n} points left ({size} freed).", rp_admin: "Needs administrator: restart SpaceSweep as administrator.",
  rp_settings: "Configure max space", opening: "Opening {path}…" },
});

S.ig = { shell: null, rp: null };

/* ---------- duplicates -> hard links */
function duLinkPairs() {
  const pairs = [];
  for (const g of S.du.res.groups) {
    const kept = g.files.filter(f => !S.du.sel.has(f.path));
    for (const f of g.files) {
      if (!S.du.sel.has(f.path)) continue;
      const k = kept.find(x => x.path.slice(0, 2).toUpperCase() === f.path.slice(0, 2).toUpperCase());
      if (k) pairs.push([f.path, k.path]);
    }
  }
  return pairs;
}

/* ---------- Explorer right-click card (on the Automatic page) */
function renderShellCard() {
  const box = $("#shellCard");
  if (!box) return;
  const st = S.ig.shell;
  box.innerHTML = `<div class="card"><div class="row"><h2 class="grow">${icon("open")}${t("intg.shell")}</h2>
    <label class="switch"><input type="checkbox" id="igShell" ${st && st.installed ? "checked" : ""} ${st ? "" : "disabled"}><span></span></label></div>
    <p class="lead">${t("intg.shell_d")}</p></div>`;
}

/* ---------- restore points card (in Cleanup) */
function renderRestoreCard() {
  const box = $("#restoreCard");
  if (!box) return;
  const r = S.ig.rp;
  let body;
  if (!S.info.admin) body = `<p class="muted small">${t("intg.rp_admin")}</p>`;
  else if (!r) body = `<button class="btn" data-act="rp-load">${icon("history")}${t("intg.rp_list")}</button>`;
  else body = `<p class="small muted">${t("intg.rp_used", { used: size(r.used), max: size(r.max) })}</p>` + (r.points.length
    ? `<div class="tbl-wrap"><table><tbody>${r.points.map(p => `<tr><td>${new Date(p.Date).toLocaleString()}</td><td class="small muted mono">${esc(p.ID)}</td></tr>`).join("")}</tbody></table></div>
       <div class="row" style="margin-top:10px"><button class="btn danger" data-act="rp-delete" ${r.points.length > 1 ? "" : "disabled"}>${icon("trash")}${t("intg.rp_delete")}</button></div>`
    : `<p class="muted">${t("intg.rp_none")}</p>`);
  box.innerHTML = `<div class="card"><div class="row"><h2 class="grow">${icon("history")}${t("intg.rp")}</h2>
    <button class="btn sm" data-act="tool" data-tool="protection">${icon("open")}${t("intg.rp_settings")}</button></div><p class="lead">${t("intg.rp_d")}</p>${body}</div>`;
}

Object.assign(ACTIONS, {
  "du-link": async () => {
    const pairs = duLinkPairs();
    if (!pairs.length) return toast(t("common.nothing_selected"));
    const ok = await modal({ title: t("intg.link_t", { n: num(pairs.length) }),
      body: `<p>${t("intg.link_b")}</p><div class="note warn">${icon("alert")}<div>${t("intg.link_warn")}</div></div>`, ok: t("intg.link_btn") });
    if (!ok) return;
    try {
      const res = await runJob(api("duplicates_hardlink", pairs), $("#duTask"), I18N[S.lang].common.working);
      if (!res) return;
      toast(t("intg.linked", { n: num(res.ok), size: size(res.freed) }));
      const bad = res.results.length - res.ok;
      if (bad) toast(t("intg.link_failed", { n: bad }), true);
      forgetPaths("du", new Set(res.results.filter(r => r.ok).map(r => r.path)));
      loadDrives();
    } catch (e) { fail(e); }
  },
  "rp-load": async () => {
    try {
      const res = await runJob(api("restore_points"), $("#clTask"), I18N[S.lang].common.working);
      if (res) { S.ig.rp = res; renderRestoreCard(); }
    } catch (e) { fail(e); }
  },
  "rp-delete": async () => {
    const oldest = S.ig.rp.points[0];
    const ok = await modal({ title: t("intg.rp_t"), body: `<p>${t("intg.rp_b", { date: new Date(oldest.Date).toLocaleString() })}</p>`, ok: t("intg.rp_delete"), okClass: "danger" });
    if (!ok) return;
    try {
      const res = await runJob(api("restore_delete_oldest", (oldest.VolumeName && S.cl.drive ? S.cl.drive : "C:\\").slice(0, 2)), $("#clTask"), I18N[S.lang].common.working);
      if (res) { toast(t("intg.rp_done", { n: num(res.left), size: size(res.freed) })); S.ig.rp = null; ACTIONS["rp-load"](); loadDrives(); }
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(async el => {
  if (el.id === "igShell") {
    try {
      S.ig.shell = await api("shellmenu_set", el.checked, S.lang);
      toast(el.checked ? t("intg.shell_on") : t("intg.shell_off"));
    } catch (e) { fail(e); }
    renderShellCard();
  }
});
const _prevAutoEnter = PAGE_ENTER.auto;
PAGE_ENTER.auto = async () => {
  if (_prevAutoEnter) await _prevAutoEnter();
  try { S.ig.shell = await api("shellmenu_status"); } catch (e) { S.ig.shell = { installed: false }; }
  renderShellCard();
};
BOOT_HOOKS.push(async () => {
  const p = await api("startup_path").catch(() => null);
  if (p) {
    toast(t("intg.opening", { path: pp(p) }));
    S.ex.root = p; S.ex.summary = null; renderExplorer(); go("explorer"); explorerScan();
  }
});
