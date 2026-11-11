"use strict";
/* Developer tools & local AI models: Docker, WSL disks, editor/IDE leftovers, build caches, models. */

Object.assign(I18N.es, { dev: {
  nav: "Herramientas dev", title: "Herramientas de desarrollo e IA",
  sub: "Docker, discos de WSL, extensiones viejas de VS Code, versiones viejas de JetBrains y de los motores de LM Studio, cachés de Gradle/Maven/Cargo, y cada modelo de IA local (LM Studio, Ollama, Hugging Face) por separado.",
  loading: "Revisando herramientas…",
  docker: "Docker", docker_none: "Docker no está instalado.", docker_off: "Docker está instalado pero no está corriendo. Abre Docker Desktop para ver cuánto puedes recuperar.",
  docker_d: "Imágenes, contenedores y caché de compilación. «Recuperable» es lo que Docker puede borrar sin tocar lo que estás usando.",
  type: "Tipo", total: "Total", reclaim: "Recuperable", prune: "Limpiar lo que no se usa", prune_all: "Incluir imágenes sin usar (se vuelven a descargar)",
  prune_t: "¿Limpiar Docker?", prune_b: "Ejecuta «docker builder prune» y «docker system prune»: borra contenedores detenidos, redes sin usar, imágenes huérfanas y la caché de compilación.", pruned: "Docker limpio.",
  wsl: "Discos de WSL (Linux) y Docker", wsl_d: "Estos discos virtuales crecen pero nunca devuelven espacio solos. El «modo disperso» hace que Windows recupere automáticamente el espacio que Linux libera.",
  sparse: "Activar modo disperso", sparse_t: "¿Activar modo disperso en {name}?", sparse_b: "Se cerrará {name} (wsl --terminate) y se ejecutará «wsl --manage {name} --set-sparse true». Necesita WSL 2.0 o más nuevo. Tus archivos de Linux no se tocan.",
  sparse_ok: "Listo: {name} ahora devuelve espacio automáticamente.", docker_disk: "Lo administra Docker Desktop: usa «Limpiar» arriba o Ajustes → Resources → Disk image.",
  leftovers: "Sobras de herramientas", leftovers_d: "Versiones viejas y cachés que estas herramientas ya no usan. Se borran permanentemente: no tiene sentido que ocupen la Papelera.",
  r_old_runtime: "Motor viejo (se conserva {newest})", r_obsolete: "Marcada como obsoleta por el propio editor", r_old_version: "Versión anterior (se conserva {newest})",
  r_cache: "Caché de paquetes: se vuelve a descargar si hace falta", r_avd: "Teléfono virtual de Android (con sus datos)",
  models: "Modelos de IA locales", models_d: "Cada modelo por separado. Bórralos si no los usas: se pueden volver a descargar.",
  app: "App", model: "Modelo", downloaded: "Descargado", ollama_rm: "Quitar con ollama", ollama_missing: "Instala Ollama o bórralo desde su app",
  none: "Nada que limpiar aquí.", del_btn: "Borrar {n} ({size})", removed: "Modelo eliminado." },
});
Object.assign(I18N.en, { dev: {
  nav: "Dev tools", title: "Developer tools & AI",
  sub: "Docker, WSL disks, old VS Code extensions, old JetBrains and LM Studio engine versions, Gradle/Maven/Cargo caches, and every local AI model (LM Studio, Ollama, Hugging Face) one by one.",
  loading: "Checking tools…",
  docker: "Docker", docker_none: "Docker isn't installed.", docker_off: "Docker is installed but not running. Start Docker Desktop to see how much you can reclaim.",
  docker_d: "Images, containers and build cache. \"Reclaimable\" is what Docker can delete without touching what you're using.",
  type: "Type", total: "Total", reclaim: "Reclaimable", prune: "Clean what's unused", prune_all: "Include unused images (they download again)",
  prune_t: "Clean Docker?", prune_b: "Runs 'docker builder prune' and 'docker system prune': removes stopped containers, unused networks, dangling images and the build cache.", pruned: "Docker cleaned.",
  wsl: "WSL (Linux) and Docker disks", wsl_d: "These virtual disks grow but never give space back by themselves. Sparse mode lets Windows reclaim automatically the space Linux frees.",
  sparse: "Enable sparse mode", sparse_t: "Enable sparse mode on {name}?", sparse_b: "{name} will be stopped (wsl --terminate) and 'wsl --manage {name} --set-sparse true' will run. Needs WSL 2.0 or newer. Your Linux files are not touched.",
  sparse_ok: "Done: {name} now gives space back automatically.", docker_disk: "Managed by Docker Desktop: use Clean above or Settings → Resources → Disk image.",
  leftovers: "Tool leftovers", leftovers_d: "Old versions and caches these tools no longer use. Deleted permanently: no point filling the Recycle Bin with them.",
  r_old_runtime: "Old engine (keeps {newest})", r_obsolete: "Marked obsolete by the editor itself", r_old_version: "Older version (keeps {newest})",
  r_cache: "Package cache: downloaded again when needed", r_avd: "Android virtual phone (with its data)",
  models: "Local AI models", models_d: "Each model on its own. Delete the ones you don't use: they can be downloaded again.",
  app: "App", model: "Model", downloaded: "Downloaded", ollama_rm: "Remove with ollama", ollama_missing: "Install Ollama or delete it from its app",
  none: "Nothing to clean here.", del_btn: "Delete {n} ({size})", removed: "Model removed." },
});

S.dv = { res: null, sel: new Set(), sizes: new Map(), perm: true, pruneAll: false };

function renderDevtools() {
  $("#page-devtools").innerHTML = head(t("dev.title"), t("dev.sub")) +
    `<div class="card"><div class="row"><button class="btn primary" data-act="dv-scan">${icon("code")}${S.dv.res ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="dvTask"></div><div id="dvBody"></div>`;
  renderDevtoolsBody();
}

function dvBar() {
  let bytes = 0;
  S.dv.sel.forEach(p => { bytes += S.dv.sizes.get(p) || 0; });
  return `<span class="grow"><b>${num(S.dv.sel.size)}</b> · ${size(bytes)}</span>
    <button class="btn danger" data-act="del-sel" data-scope="dv" ${S.dv.sel.size ? "" : "disabled"}>${icon("trash")}${t("dev.del_btn", { n: num(S.dv.sel.size), size: size(bytes) })}</button>`;
}

function renderDevtoolsBody() {
  const r = S.dv.res, el = $("#dvBody");
  if (!el) return;
  if (!r) { el.innerHTML = `<div class="card">${empty(t("dev.sub"), "code")}</div>`; return; }
  const d = r.docker;
  let html = `<div class="card"><h2>${icon("package")}${t("dev.docker")}</h2>`;
  if (!d.available) html += `<p class="muted">${t("dev.docker_none")}</p>`;
  else if (!d.running) html += `<p class="muted">${t("dev.docker_off")}</p>`;
  else {
    html += `<p class="lead">${t("dev.docker_d")}</p><div class="tbl-wrap"><table><thead><tr><th>${t("dev.type")}</th><th class="num">${t("dev.total")}</th>
      <th class="num">${t("dev.reclaim")}</th></tr></thead><tbody>${d.rows.map(x => `<tr><td>${esc(x.Type)} <span class="muted small">(${esc(x.TotalCount)})</span></td>
      <td class="num">${esc(x.Size)}</td><td class="num"><b>${esc(x.Reclaimable)}</b></td></tr>`).join("")}</tbody></table></div>
      <div class="row" style="margin-top:12px"><label class="row small"><input type="checkbox" id="dvPruneAll" ${S.dv.pruneAll ? "checked" : ""}>${t("dev.prune_all")}</label>
      <span class="grow"></span><button class="btn primary" data-act="dv-prune">${icon("sweep")}${t("dev.prune")}</button></div>`;
  }
  html += `</div><div class="card"><h2>${icon("disk")}${t("dev.wsl")}</h2><p class="lead">${t("dev.wsl_d")}</p>${r.wsl.length ? `<div class="tbl-wrap"><table><tbody>${r.wsl.map(w => `<tr>
    <td><b>${esc(w.name)}</b><div class="path">${esc(pp(w.path || ""))}</div></td><td class="num">${size(w.size)}</td>
    <td class="act">${w.path ? openBtn(w.path) : ""}${w.docker || /^docker-desktop/.test(w.name) ? `<span class="small muted">${t("dev.docker_disk")}</span>`
      : `<button class="btn sm" data-act="dv-sparse" data-name="${esc(w.name)}">${t("dev.sparse")}</button>`}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">${t("dev.none")}</p>`}</div>`;

  html += `<div class="card"><h2>${icon("trash")}${t("dev.leftovers")}</h2><p class="lead">${t("dev.leftovers_d")}</p>`;
  html += r.leftovers.length ? `<div class="row" style="margin-bottom:8px"><button class="btn ghost sm" data-act="sel-all" data-scope="dv">${t("common.select_all")}</button>
      <button class="btn ghost sm" data-act="sel-none" data-scope="dv">${t("common.select_none")}</button></div>
    <div class="tbl-wrap"><table><tbody>${r.leftovers.map(x => `<tr><td class="chk">${checkbox("dv", x.path)}</td>
      <td><b>${esc(x.tool)}</b> · ${esc(x.name)}<div class="path">${esc(pp(x.path))}</div></td>
      <td><span class="badge ${x.reason === "avd" ? "b-warn" : "b-safe"} wrap">${t("dev.r_" + x.reason, { newest: x.newest || "" })}</span></td>
      <td class="num">${size(x.size)}</td><td class="act">${openBtn(x.path)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">${t("dev.none")}</p>`;
  html += `</div><div class="card"><h2>${icon("brain")}${t("dev.models")}</h2><p class="lead">${t("dev.models_d")}</p>`;
  html += r.models.models.length ? `<div class="tbl-wrap"><table><thead><tr><th class="chk"></th><th>${t("dev.model")}</th><th>${t("dev.app")}</th>
      <th>${t("dev.downloaded")}</th><th class="num">${t("common.size")}</th><th></th></tr></thead><tbody>${r.models.models.map((m, i) => `<tr>
      <td class="chk">${m.delete === "folder" ? checkbox("dv", m.path) : ""}</td><td><b>${esc(m.name)}</b></td><td><span class="badge b-info">${esc(m.app)}</span></td>
      <td class="small">${date(m.date)}</td><td class="num">${size(m.size)}</td>
      <td class="act">${m.delete === "ollama" ? `<button class="btn sm" data-act="dv-ollama" data-i="${i}">${t("dev.ollama_rm")}</button>`
        : m.delete === "none" ? `<span class="small muted">${t("dev.ollama_missing")}</span>` : openBtn(m.path)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">${t("dev.none")}</p>`;
  html += `<div class="sticky-actions" id="dvBar">${dvBar()}</div></div>`;
  el.innerHTML = html;
}

async function devtoolsScan() {
  try {
    const res = await runJob(api("inv_devtools"), $("#dvTask"), t("dev.loading"));
    if (!res) return;
    S.dv.res = res;
    S.dv.sel.clear();
    S.dv.sizes = new Map([...res.leftovers.map(x => [x.path, x.size]),
      ...res.models.models.filter(m => m.delete === "folder").map(m => [m.path, m.size])]);
    renderDevtools();
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderDevtools);
PAGE_ENTER.devtools = () => { if (!S.dv.res) devtoolsScan(); };
SCOPE_RENDER.dv = renderDevtoolsBody;
BARS.dv = dvBar;
FORGET.dv = gone => {
  S.dv.res.leftovers = S.dv.res.leftovers.filter(x => !gone.has(x.path));
  S.dv.res.models.models = S.dv.res.models.models.filter(m => !gone.has(m.path) || m.delete !== "folder");
  renderDevtoolsBody();
};
Object.assign(ACTIONS, {
  "dv-scan": () => devtoolsScan(),
  "dv-prune": async () => {
    const ok = await modal({ title: t("dev.prune_t"), body: `<p>${t("dev.prune_b")}</p>`, ok: t("dev.prune") });
    if (!ok) return;
    try {
      const res = await runJob(api("inv_docker_prune", S.dv.pruneAll), $("#dvTask"), I18N[S.lang].common.working);
      if (res) { toast(t("dev.pruned")); devtoolsScan(); }
    } catch (e) { fail(e); }
  },
  "dv-sparse": async el => {
    const name = el.dataset.name;
    const ok = await modal({ title: t("dev.sparse_t", { name }), body: `<p>${t("dev.sparse_b", { name })}</p>`, ok: t("dev.sparse") });
    if (!ok) return;
    try {
      const res = await runJob(api("inv_wsl_sparse", name), $("#dvTask"), I18N[S.lang].common.working);
      if (!res) return;
      const bad = res.find(s => s.result[0] !== 0 && s.cmd.includes("set-sparse"));
      bad ? toast(`${t("common.error")}: ${bad.result[1]}`, true) : toast(t("dev.sparse_ok", { name }));
    } catch (e) { fail(e); }
  },
  "dv-ollama": async el => {
    const m = S.dv.res.models.models[+el.dataset.i];
    const ok = await modal({ title: `ollama rm ${esc(m.name)}?`, body: `<p>${t("dev.models_d")}</p>`, ok: t("dev.ollama_rm"), okClass: "danger" });
    if (!ok) return;
    try {
      const [rc, out] = await api("inv_ollama_rm", m.name);
      rc === 0 ? (toast(t("dev.removed")), devtoolsScan()) : toast(`${t("common.error")}: ${out}`, true);
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => { if (el.id === "dvPruneAll") S.dv.pruneAll = el.checked; });
