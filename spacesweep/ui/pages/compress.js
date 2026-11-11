"use strict";
/* Transparent NTFS compression of games and rarely-written folders. */

Object.assign(I18N.es, { cmp: {
  nav: "Comprimir", title: "Comprimir sin borrar",
  sub: "Windows puede guardar carpetas comprimidas de forma transparente: los programas y juegos las usan igual, pero ocupan menos. Ideal para juegos instalados y herramientas que casi no cambian. No se borra nada y se puede revertir.",
  how: "Usa la compresión integrada de Windows (compact /EXE, la misma de CompactOS). Los juegos cargan casi igual en un SSD. Si un juego se actualiza, los archivos nuevos quedan sin comprimir: vuelve a comprimirlo después. Evita comprimir lo que cambia mucho (bases de datos, discos virtuales, partidas en curso).",
  loading: "Buscando juegos y carpetas candidatas…", algo: "Compresión", lzx: "Máxima (LZX) — recomendada para juegos", x8: "Rápida (XPRESS 8K)",
  candidates: "Candidatas", other: "Otra carpeta…", analyze: "Analizar", compress: "Comprimir", undo: "Descomprimir",
  analyzing: "Midiendo tamaño en disco y estimando…", compressing: "Comprimiendo (puede tardar; puedes seguir usando la PC)…", decompressing: "Descomprimiendo…",
  on_disk: "En disco", saved_now: "Ya ahorrado", estimate: "Ahorro estimado", idle: "sin jugar {n} días",
  done: "Comprimido: {saved} ahorrados en {name}.", undone: "Descomprimido {name}.",
  confirm_t: "¿Comprimir {name}?", confirm_b: "Se comprimirá {size} con {algo}. Puedes seguir usando la PC; los archivos abiertos se saltan. Se puede revertir con «Descomprimir».",
  undo_t: "¿Descomprimir {name}?", undo_b: "Volverá a ocupar su tamaño completo ({size}). Asegúrate de tener ese espacio libre." },
});
Object.assign(I18N.en, { cmp: {
  nav: "Compress", title: "Compress without deleting",
  sub: "Windows can store folders compressed transparently: programs and games use them as usual, but they take less space. Ideal for installed games and tools that rarely change. Nothing is deleted and it can be reverted.",
  how: "Uses Windows' built-in compression (compact /EXE, the same as CompactOS). Games load about the same on an SSD. When a game updates, the new files are stored uncompressed: compress it again afterwards. Avoid folders that change a lot (databases, virtual disks, active saves).",
  loading: "Looking for games and candidate folders…", algo: "Compression", lzx: "Maximum (LZX) — recommended for games", x8: "Fast (XPRESS 8K)",
  candidates: "Candidates", other: "Other folder…", analyze: "Analyze", compress: "Compress", undo: "Decompress",
  analyzing: "Measuring size on disk and estimating…", compressing: "Compressing (may take a while; you can keep using the PC)…", decompressing: "Decompressing…",
  on_disk: "On disk", saved_now: "Already saved", estimate: "Estimated saving", idle: "unplayed {n} days",
  done: "Compressed: {saved} saved in {name}.", undone: "Decompressed {name}.",
  confirm_t: "Compress {name}?", confirm_b: "{size} will be compressed with {algo}. You can keep using the PC; open files are skipped. Revert with Decompress.",
  undo_t: "Decompress {name}?", undo_b: "It will take its full size again ({size}). Make sure that much space is free." },
});

S.cp = { list: null, status: {}, algo: "LZX", extra: [] };

function renderCompress() {
  const c = S.cp;
  $("#page-compress").innerHTML = head(t("cmp.title"), t("cmp.sub")) +
    `<div class="note">${icon("infoc")}<div>${t("cmp.how")}</div></div>
     <div class="card"><div class="row"><label class="muted">${t("cmp.algo")}</label><select id="cpAlgo">
       <option value="LZX" ${c.algo === "LZX" ? "selected" : ""}>${t("cmp.lzx")}</option><option value="XPRESS8K" ${c.algo === "XPRESS8K" ? "selected" : ""}>${t("cmp.x8")}</option></select>
       <span class="grow"></span><button class="btn" data-act="cp-other">${icon("plus")}${t("cmp.other")}</button>
       <button class="btn" data-act="cp-load">${icon("refresh")}${I18N[S.lang].common.reanalyze}</button></div></div>
     <div class="task hidden" id="cpTask"></div><div id="cpBody"></div>`;
  renderCompressBody();
}

function cpRow(x, i) {
  const st = S.cp.status[x.path];
  const meas = st ? `<div class="small">${t("cmp.on_disk")}: <b>${size(st.on_disk)}</b> · ${t("cmp.saved_now")}: ${size(st.already_saved)}
      · ${t("cmp.estimate")}: <b style="color:var(--accent)">${size(st.estimate_saving)}</b></div>` : "";
  return `<tr><td><b>${esc(x.name)}</b> ${x.platform ? `<span class="badge b-info">${esc(x.platform)}</span>` : ""}
      ${x.idle_days != null ? `<span class="small muted">${t("cmp.idle", { n: num(x.idle_days) })}</span>` : ""}
      <div class="path">${esc(pp(x.path))}</div>${meas}</td><td class="num">${size(x.size)}</td><td class="small">${esc(x.drive)}</td>
    <td class="act"><button class="btn sm" data-act="cp-status" data-i="${i}">${t("cmp.analyze")}</button>
      <button class="btn sm primary" data-act="cp-run" data-i="${i}">${t("cmp.compress")}</button>
      ${st && st.already_saved > 0 ? `<button class="btn sm ghost" data-act="cp-undo" data-i="${i}">${t("cmp.undo")}</button>` : ""}</td></tr>`;
}

function cpItems() { return [...S.cp.extra, ...(S.cp.list || [])]; }

function renderCompressBody() {
  const el = $("#cpBody");
  if (!el) return;
  if (!S.cp.list) { el.innerHTML = ""; return; }
  const items = cpItems();
  el.innerHTML = `<div class="card"><h2>${icon("package")}${t("cmp.candidates")}</h2>${items.length ? `<div class="tbl-wrap"><table><tbody>
    ${items.map(cpRow).join("")}</tbody></table></div>` : empty(t("common.none"))}</div>`;
}

async function compressLoad() {
  try {
    const res = await runJob(api("compress_candidates"), $("#cpTask"), t("cmp.loading"));
    if (res) { S.cp.list = res; renderCompressBody(); }
  } catch (e) { fail(e); }
}

async function cpStatus(x) {
  const res = await runJob(api("compress_status", x.path), $("#cpTask"), t("cmp.analyzing"));
  if (res) { S.cp.status[x.path] = res; renderCompressBody(); }
  return res;
}

PAGE_RENDERERS.push(renderCompress);
PAGE_ENTER.compress = () => { if (!S.cp.list) compressLoad(); };
Object.assign(ACTIONS, {
  "cp-load": () => compressLoad(),
  "cp-other": async () => {
    const p = await pickFolder();
    if (p) { S.cp.extra.unshift({ kind: "folder", name: base(p), path: p, size: 0, idle_days: null, platform: "", drive: p.slice(0, 2).toUpperCase() });
      renderCompressBody(); cpStatus(S.cp.extra[0]).catch(fail); }
  },
  "cp-status": el => cpStatus(cpItems()[+el.dataset.i]).catch(fail),
  "cp-run": async el => {
    const x = cpItems()[+el.dataset.i];
    const algo = S.cp.algo;
    const ok = await modal({ title: t("cmp.confirm_t", { name: x.name }), body: `<p>${t("cmp.confirm_b", { size: size(x.size), algo })}</p>`, ok: t("cmp.compress") });
    if (!ok) return;
    try {
      const res = await runJob(api("compress_run", x.path, algo), $("#cpTask"), t("cmp.compressing"));
      if (!res) return;
      toast(t("cmp.done", { saved: size(res.saved), name: x.name }));
      loadDrives();
      await cpStatus(x);
    } catch (e) { fail(e); }
  },
  "cp-undo": async el => {
    const x = cpItems()[+el.dataset.i];
    const ok = await modal({ title: t("cmp.undo_t", { name: x.name }), body: `<p>${t("cmp.undo_b", { size: size(x.size) })}</p>`, ok: t("cmp.undo") });
    if (!ok) return;
    try {
      const res = await runJob(api("compress_undo", x.path), $("#cpTask"), t("cmp.decompressing"));
      if (res) { toast(t("cmp.undone", { name: x.name })); loadDrives(); await cpStatus(x); }
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => { if (el.id === "cpAlgo") S.cp.algo = el.value; });
