"use strict";
/* Move heavy folders to another drive (junction left behind) + WinSxS cleanup through DISM. */

Object.assign(I18N.es, { mv: {
  nav: "Mover a otro disco", title: "Mover a otro disco",
  sub: "Pasa una carpeta pesada (modelos de IA, SDKs, cachés de compilación…) a otro disco y deja un enlace en su lugar: los programas la siguen encontrando en la misma ruta, pero ya no ocupa C:. Se puede deshacer.",
  how: "Cómo funciona: copia todo al otro disco, comprueba que la copia es idéntica (archivos y bytes), y solo entonces cambia la carpeta original por un enlace (junction). Si algo falla, la original queda intacta. Cierra el programa que usa la carpeta antes de moverla.",
  moved: "Carpetas movidas", none_moved: "Todavía no has movido ninguna carpeta.", now_at: "Ahora en", broken: "El enlace o la copia ya no existen: revisa",
  restore: "Traer de vuelta", restore_t: "¿Traer {name} de vuelta a {d}?", restore_b: "Se copiará de nuevo a su ruta original, se verificará y se borrará la copia del otro disco.",
  suggest: "Buenas candidatas", suggest_d: "Carpetas grandes que suelen vivir bien en otro disco.", none_suggest: "No se encontraron carpetas grandes típicas para mover.",
  other: "Mover otra carpeta…", move: "Mover", pick_drive: "Mover {name} a otro disco", to: "Disco destino", free: "{size} libres",
  checking: "Comprobando…", moving: "Moviendo… no cierres SpaceSweep", done: "Movida: {name} ahora está en {target} ({size}).",
  restored: "{name} volvió a {d}.", leftover: "La carpeta vieja no se pudo borrar del todo; bórrala a mano: {path}",
  no_drive: "No hay otro disco fijo con espacio.", k_ai: "IA", k_dev: "Desarrollo",
  dism: "Almacén de componentes de Windows (WinSxS)",
  dism_d: "La forma segura de reducir WinSxS es la herramienta oficial DISM. «Analizar» dice cuánto ocupa de verdad y si conviene limpiar; «Limpiar» quita versiones viejas de componentes ya reemplazados. Las actualizaciones instaladas se siguen pudiendo desinstalar. Requiere administrador y puede tardar varios minutos.",
  dism_analyze: "Analizar", dism_clean: "Limpiar con DISM", dism_need_admin: "Reinicia SpaceSweep como administrador para usar DISM.",
  dism_working: "DISM trabajando (puede tardar varios minutos)…", dism_rec: "Limpieza recomendada", dism_not_rec: "No hace falta limpiar",
  dism_freed: "DISM terminó: {size} liberados.", dism_t: "¿Limpiar WinSxS con DISM?",
  dism_b: "Ejecuta «Dism /Online /Cleanup-Image /StartComponentCleanup». No uses la PC para cosas pesadas mientras corre." },
});
Object.assign(I18N.en, { mv: {
  nav: "Move to another drive", title: "Move to another drive",
  sub: "Moves a heavy folder (AI models, SDKs, build caches…) to another drive and leaves a link in its place: programs still find it at the same path, but it no longer uses C:. Can be undone.",
  how: "How it works: copies everything to the other drive, checks the copy is identical (files and bytes), and only then swaps the original folder for a link (junction). If anything fails, the original stays untouched. Close the program using the folder before moving it.",
  moved: "Moved folders", none_moved: "You haven't moved any folder yet.", now_at: "Now on", broken: "The link or the copy is gone: check",
  restore: "Bring back", restore_t: "Bring {name} back to {d}?", restore_b: "It's copied back to its original path, verified, and the copy on the other drive is deleted.",
  suggest: "Good candidates", suggest_d: "Big folders that usually live happily on another drive.", none_suggest: "No typical big folders to move were found.",
  other: "Move another folder…", move: "Move", pick_drive: "Move {name} to another drive", to: "Target drive", free: "{size} free",
  checking: "Checking…", moving: "Moving… don't close SpaceSweep", done: "Moved: {name} now lives in {target} ({size}).",
  restored: "{name} is back on {d}.", leftover: "The old folder couldn't be fully deleted; remove it by hand: {path}",
  no_drive: "No other fixed drive with free space.", k_ai: "AI", k_dev: "Dev",
  dism: "Windows component store (WinSxS)",
  dism_d: "The safe way to shrink WinSxS is Microsoft's DISM tool. Analyze tells you its real size and whether cleaning helps; Clean removes old versions of components that were replaced. Installed updates can still be uninstalled. Needs administrator and may take several minutes.",
  dism_analyze: "Analyze", dism_clean: "Clean with DISM", dism_need_admin: "Restart SpaceSweep as administrator to use DISM.",
  dism_working: "DISM working (may take several minutes)…", dism_rec: "Cleanup recommended", dism_not_rec: "No cleanup needed",
  dism_freed: "DISM finished: {size} freed.", dism_t: "Clean WinSxS with DISM?",
  dism_b: "Runs 'Dism /Online /Cleanup-Image /StartComponentCleanup'. Avoid heavy work on the PC while it runs." },
});

S.mv = { moves: null, sugg: null, dism: null };

function renderMove() {
  $("#page-move").innerHTML = head(t("mv.title"), t("mv.sub")) + `<div class="note">${icon("infoc")}<div>${t("mv.how")}</div></div>
    <div class="task hidden" id="mvJob"></div><div class="task hidden" id="mvTask"></div><div id="mvBody"></div>`;
  renderMoveBody();
}

function renderMoveBody() {
  const m = S.mv;
  let html = `<div class="card"><div class="row"><h2 class="grow">${icon("disk")}${t("mv.moved")}</h2>
      <button class="btn" data-act="mv-other">${icon("plus")}${t("mv.other")}</button></div>`;
  html += !m.moves ? empty(I18N[S.lang].common.working, "clock") : !m.moves.length ? `<p class="muted">${t("mv.none_moved")}</p>`
    : `<div class="tbl-wrap"><table><tbody>${m.moves.map((x, i) => `<tr><td><b>${esc(pp(x.src))}</b>
        <div class="small muted">${x.linked && x.target_ok ? `${t("mv.now_at")} <span class="mono">${esc(x.target)}</span>` : `<span class="badge b-danger">${t("mv.broken")}</span>`}</div></td>
        <td class="num">${size(x.size)}</td><td class="small">${date(x.time)}</td>
        <td class="act">${openBtn(x.target)}<button class="btn sm" data-act="mv-restore" data-i="${i}">${icon("undo")}${t("mv.restore")}</button></td></tr>`).join("")}</tbody></table></div>`;
  html += `</div><div class="card"><h2>${icon("brain")}${t("mv.suggest")}</h2><p class="lead">${t("mv.suggest_d")}</p>`;
  html += !m.sugg ? empty(I18N[S.lang].common.working, "clock") : !m.sugg.length ? `<p class="muted">${t("mv.none_suggest")}</p>`
    : `<div class="tbl-wrap"><table><tbody>${m.sugg.map((x, i) => `<tr><td><b>${esc(pp(x.path))}</b></td>
        <td><span class="badge b-info">${t("mv.k_" + x.kind)}</span></td><td class="num">${size(x.size)}</td>
        <td class="act">${openBtn(x.path)}<button class="btn sm primary" data-act="mv-move" data-path="${esc(x.path)}">${t("mv.move")}</button></td></tr>`).join("")}</tbody></table></div>`;
  $("#mvBody").innerHTML = html + `</div>`;
}

async function moveLoad(refresh = true) {
  try {
    S.mv.moves = await api("move_list");
    renderMoveBody();
    if (S.mv.loading || (!refresh && S.mv.sugg)) return;
    S.mv.loading = true;
    S.mv.sugg = await runJob(api("move_suggestions"), $("#mvTask"), t("mv.checking")) || [];
    renderMoveBody();
  } catch (e) { fail(e); } finally { S.mv.loading = false; }
}

async function moveFolder(src) {
  const drives = S.drives.filter(d => d.type === "fixed" && d.root[0].toUpperCase() !== src[0].toUpperCase());
  if (!drives.length) return toast(t("mv.no_drive"), true);
  const best = drives.reduce((a, b) => (b.free > a.free ? b : a));
  S.mv.dest = best.root;  // updated by the radio buttons (the dialog is gone once it resolves)
  const pick = await modal({
    title: t("mv.pick_drive", { name: base(src) }),
    body: `<p class="muted">${t("mv.how")}</p><label class="muted">${t("mv.to")}</label>
      <div style="display:grid;gap:6px;margin-top:6px">${drives.map(d => `<label class="row"><input type="radio" name="mvDrive" value="${esc(d.root)}" ${d === best ? "checked" : ""}>
        <b>${esc(d.letter)}:</b> ${esc(d.label)} <span class="muted small">${t("mv.free", { size: size(d.free) })}</span></label>`).join("")}</div>`,
    ok: t("mv.move"),
  });
  if (!pick) return;
  const dest = S.mv.dest + "SpaceSweep";
  try {
    if (S.page !== "move") go("move");
    const res = await runJob(api("move_run", src, dest), $("#mvJob"), t("mv.moving"));
    if (!res) return;
    toast(t("mv.done", { name: base(src), target: res.target, size: size(res.size) }));
    if (res.leftover) toast(t("mv.leftover", { path: src + ".spacesweep-old" }), true);
    loadDrives();
    moveLoad();
  } catch (e) { fail(e); }
}

/* ---------- DISM card shown inside the Cleanup page (system drive only) */
function renderDismCard() {
  const box = $("#dismCard");
  if (!box) return;
  const d = S.mv.dism;
  const rows = d ? Object.entries(d).filter(([k]) => k !== "recommended").map(([k, v]) => `<tr><td class="small">${esc(k)}</td><td class="small">${esc(v)}</td></tr>`).join("") : "";
  box.innerHTML = `<div class="card"><h2>${icon("windows")}${t("mv.dism")}</h2><p class="lead">${t("mv.dism_d")}</p>
    ${S.info.admin ? `<div class="row"><button class="btn" data-act="dism-analyze">${t("mv.dism_analyze")}</button>
      <button class="btn primary" data-act="dism-clean">${icon("sweep")}${t("mv.dism_clean")}</button>
      ${d ? `<span class="badge ${d.recommended ? "b-warn" : "b-safe"}">${d.recommended ? t("mv.dism_rec") : t("mv.dism_not_rec")}</span>` : ""}</div>
      ${rows ? `<div class="tbl-wrap" style="margin-top:12px"><table><tbody>${rows}</tbody></table></div>` : ""}`
      : `<p class="muted small">${t("mv.dism_need_admin")}</p>`}</div>`;
}

CHANGE_HOOKS.push(el => { if (el.name === "mvDrive") S.mv.dest = el.value; });
PAGE_RENDERERS.push(renderMove);
PAGE_ENTER.move = () => moveLoad(false);
Object.assign(ACTIONS, {
  "mv-move": el => moveFolder(el.dataset.path),
  "mv-other": async () => { const p = await pickFolder(); if (p) moveFolder(p); },
  "ex-move": el => moveFolder(el.dataset.path),
  "mv-restore": async el => {
    const x = S.mv.moves[+el.dataset.i];
    const ok = await modal({ title: t("mv.restore_t", { name: base(x.src), d: x.src.slice(0, 2) }), body: `<p>${t("mv.restore_b")}</p>`, ok: t("mv.restore") });
    if (!ok) return;
    try {
      const res = await runJob(api("move_restore", x.src), $("#mvJob"), t("mv.moving"));
      if (res) { toast(t("mv.restored", { name: base(x.src), d: x.src.slice(0, 2) })); loadDrives(); moveLoad(); }
    } catch (e) { fail(e); }
  },
  "dism-analyze": async () => {
    try {
      const res = await runJob(api("dism_analyze"), $("#clTask"), t("mv.dism_working"));
      if (res) { S.mv.dism = res; renderDismCard(); }
    } catch (e) { fail(e); }
  },
  "dism-clean": async () => {
    const ok = await modal({ title: t("mv.dism_t"), body: `<p>${t("mv.dism_b")}</p>`, ok: t("mv.dism_clean") });
    if (!ok) return;
    try {
      const res = await runJob(api("dism_cleanup"), $("#clTask"), t("mv.dism_working"));
      if (res) { toast(t("mv.dism_freed", { size: size(res.freed) })); loadDrives(); }
    } catch (e) { fail(e); }
  },
});
