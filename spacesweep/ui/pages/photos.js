"use strict";
/* Similar photos: bursts, edited copies, resized versions. */

Object.assign(I18N.es, { ph: {
  nav: "Fotos parecidas", title: "Fotos parecidas",
  sub: "Encuentra fotos casi iguales aunque no sean idénticas: ráfagas, versiones editadas, capturas repetidas o la misma foto en otro tamaño. Usa las miniaturas que Windows ya genera, así que no necesita nada extra.",
  how: "Cómo funciona: reduce cada foto a una huella de 64 puntos (dHash) y agrupa las que difieren en pocos puntos. Revisa siempre las miniaturas: «parecida» no significa «sobrante».",
  folders: "Carpetas", sens: "Sensibilidad", strict: "Estricta (casi idénticas)", normal: "Normal", wide: "Amplia (más grupos, más falsos parecidos)",
  search: "Buscar fotos parecidas", hashing: "Calculando huellas de las fotos…", listing: "Buscando fotos…", grouping: "Agrupando…",
  groups: "Grupos", wasted: "Si dejas solo la más grande", scanned: "Fotos revisadas",
  auto: "Marcar todas menos la más grande", auto_d: "La más grande suele ser la de mejor calidad.", none: "No se encontraron fotos parecidas.",
  largest: "más grande", photos_n: "{n} fotos parecidas" },
});
Object.assign(I18N.en, { ph: {
  nav: "Similar photos", title: "Similar photos",
  sub: "Finds photos that look almost the same even when they aren't identical: bursts, edited versions, repeated screenshots or the same photo in another size. Uses the thumbnails Windows already makes, so nothing extra is needed.",
  how: "How it works: each photo is reduced to a 64-point fingerprint (dHash) and photos whose fingerprints differ in few points are grouped. Always look at the thumbnails: \"similar\" doesn't mean \"spare\".",
  folders: "Folders", sens: "Sensitivity", strict: "Strict (near-identical)", normal: "Normal", wide: "Wide (more groups, more false matches)",
  search: "Find similar photos", hashing: "Fingerprinting photos…", listing: "Looking for photos…", grouping: "Grouping…",
  groups: "Groups", wasted: "If you keep only the largest", scanned: "Photos checked",
  auto: "Select all but the largest", auto_d: "The largest is usually the best quality.", none: "No similar photos found.",
  largest: "largest", photos_n: "{n} similar photos" },
});

S.ph = { folders: [], threshold: "6", res: null, sel: new Set(), sizes: new Map(), perm: false, shown: 30, thumbs: new Map() };

function renderPhotos() {
  const p = S.ph;
  if (!p.folders.length && S.info) p.folders = [S.info.folders.pictures];
  const opts = [["4", "strict"], ["6", "normal"], ["10", "wide"]];
  $("#page-photos").innerHTML = head(t("ph.title"), t("ph.sub")) +
    `<div class="card"><h2>${t("ph.folders")}</h2>
      <div class="row" style="margin:8px 0 12px">${p.folders.map((f, i) => `<span class="chip on">${icon("image")}<span class="mono">${esc(pp(f))}</span>
        <span class="x" data-act="ph-rm" data-i="${i}">${icon("x")}</span></span>`).join("")}
        <button class="chip" data-act="ph-add">${icon("plus")}${t("dup.add")}</button></div>
      <div class="row"><label class="muted">${t("ph.sens")}</label><select id="phSens">${opts.map(([v, k]) => `<option value="${v}" ${p.threshold === v ? "selected" : ""}>${t("ph." + k)}</option>`).join("")}</select>
        <span class="grow"></span><button class="btn primary" data-act="ph-scan">${icon("image")}${t("ph.search")}</button></div>
      <div class="note">${icon("infoc")}<div>${t("ph.how")}</div></div></div>
     <div class="task hidden" id="phTask"></div><div id="phBody"></div>`;
  renderPhotosBody();
}

function renderPhotosBody() {
  const p = S.ph, el = $("#phBody");
  if (!el) return;
  if (!p.res) { el.innerHTML = ""; return; }
  const r = p.res;
  let html = `<div class="stats">${stat(t("ph.groups"), num(r.groups.length), "", "image")}${stat(t("ph.wasted"), size(r.wasted), "accent", "trash")}
    ${stat(t("ph.scanned"), num(r.hashed), "", "file")}</div>`;
  if (!r.groups.length) { el.innerHTML = html + `<div class="card">${empty(t("ph.none"))}</div>`; return; }
  html += `<div class="card"><div class="row" style="margin-bottom:12px"><button class="btn sm" data-act="ph-auto">${t("ph.auto")}</button>
    <button class="btn ghost sm" data-act="sel-none" data-scope="ph">${t("common.select_none")}</button><span class="small muted">${t("ph.auto_d")}</span></div>`;
  html += r.groups.slice(0, p.shown).map(g => `<div class="group"><div class="group-head">${icon("image")}<b class="grow">${t("ph.photos_n", { n: g.count })}</b>
      <span class="muted small">${size(g.wasted)}</span></div>
      <div class="photo-grid">${g.files.map((f, i) => `<label class="photo ${p.sel.has(f.path) ? "sel" : ""}">
        <div class="thumb" data-thumb="${esc(f.path)}">${p.thumbs.get(f.path) ? `<img src="${p.thumbs.get(f.path)}" alt="">` : ""}</div>
        <div class="row small">${checkbox("ph", f.path)}<span class="grow ellipsis" title="${esc(f.path)}">${esc(base(f.path))}</span></div>
        <div class="row small muted"><span>${size(f.size)}</span>${i === 0 ? `<span class="badge b-safe">${t("ph.largest")}</span>` : ""}<span class="grow"></span>${openBtn(f.path)}</div>
      </label>`).join("")}</div></div>`).join("");
  if (r.groups.length > p.shown) html += `<button class="btn" data-act="ph-more">${t("common.show_more")} (${num(r.groups.length - p.shown)})</button>`;
  html += `<div class="sticky-actions" id="phBar">${selectionBar("ph")}</div></div>`;
  el.innerHTML = html;
  loadThumbs();
}

/* Thumbnails are fetched lazily, a few at a time, and cached. */
async function loadThumbs() {
  const p = S.ph;
  if (p.loadingThumbs) return;
  p.loadingThumbs = true;
  try {
    for (const box of $$("#phBody [data-thumb]")) {
      const path = box.dataset.thumb;
      if (p.thumbs.has(path)) continue;
      const uri = await api("photo_thumb", path, 160).catch(() => null);
      p.thumbs.set(path, uri || "");
      $$(`#phBody [data-thumb]`).filter(b => b.dataset.thumb === path).forEach(b => { b.innerHTML = uri ? `<img src="${uri}" alt="">` : icon("image"); });
    }
  } finally { p.loadingThumbs = false; }
}

async function photosScan() {
  const p = S.ph;
  if (!p.folders.length) return toast(t("dup.choose"));
  const label = s => ({ hashing: t("ph.hashing"), grouping: t("ph.grouping") }[s.message] || t("ph.listing"));
  try {
    const res = await runJob(api("photos_find", p.folders, +p.threshold), $("#phTask"), label);
    if (!res) return;
    p.res = res;
    p.shown = 30;
    p.sel.clear();
    p.sizes = new Map(res.groups.flatMap(g => g.files.map(f => [f.path, f.size])));
    renderPhotosBody();
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderPhotos);
SCOPE_RENDER.ph = renderPhotosBody;
FORGET.ph = gone => {
  const r = S.ph.res;
  r.groups = r.groups.map(g => ({ ...g, files: g.files.filter(f => !gone.has(f.path)) })).filter(g => g.files.length > 1);
  r.groups.forEach(g => { g.count = g.files.length; g.wasted = g.files.slice(1).reduce((a, f) => a + f.size, 0); });
  r.wasted = r.groups.reduce((a, g) => a + g.wasted, 0);
  renderPhotosBody();
};
Object.assign(ACTIONS, {
  "ph-scan": () => photosScan(),
  "ph-add": async () => { const f = await pickFolder(); if (f && !S.ph.folders.includes(f)) { S.ph.folders.push(f); renderPhotos(); } },
  "ph-rm": el => { S.ph.folders.splice(+el.dataset.i, 1); renderPhotos(); },
  "ph-more": () => { S.ph.shown += 30; renderPhotosBody(); },
  "ph-auto": () => {
    S.ph.sel.clear();
    S.ph.res.groups.forEach(g => g.files.slice(1).forEach(f => S.ph.sel.add(f.path)));
    renderPhotosBody();
  },
});
CHANGE_HOOKS.push(el => {
  if (el.id === "phSens") S.ph.threshold = el.value;
});
