"use strict";
/* Installed games across Steam, Epic, GOG, Ubisoft and Xbox, with last-played dates. */

Object.assign(I18N.es, { games: {
  nav: "Juegos", title: "Juegos instalados",
  sub: "Juegos de Steam, Epic, GOG, Ubisoft y Xbox con su tamaño y la última vez que los jugaste. Desinstalar abre el launcher del juego, así no pierdes partidas en la nube ni deja restos.",
  loading: "Buscando juegos…", total: "Ocupan en total", count: "Juegos", idle: "Sin jugar hace {n}+ días", idle_d: "{n}+ días",
  game: "Juego", platform: "Plataforma", last: "Última vez jugado", never: "Desconocido", ago: "hace {n} días", today: "hoy",
  sort: "Ordenar por", by_size: "Tamaño", by_idle: "Tiempo sin jugar", drive: "Disco", all: "Todos",
  uninstall: "Desinstalar", confirm_t: "¿Desinstalar {name}?", confirm_b: "Se abrirá {platform} para desinstalarlo. Tus partidas guardadas en la nube no se pierden.",
  unknown_note: "Epic, GOG, Ubisoft y Xbox no guardan la última fecha de juego de forma accesible: se muestra «Desconocido»." },
});
Object.assign(I18N.en, { games: {
  nav: "Games", title: "Installed games",
  sub: "Steam, Epic, GOG, Ubisoft and Xbox games with size and when you last played them. Uninstalling opens the game's launcher, so cloud saves stay and nothing is left behind.",
  loading: "Looking for games…", total: "Total size", count: "Games", idle: "Unplayed for {n}+ days", idle_d: "{n}+ days",
  game: "Game", platform: "Platform", last: "Last played", never: "Unknown", ago: "{n} days ago", today: "today",
  sort: "Sort by", by_size: "Size", by_idle: "Time since played", drive: "Drive", all: "All",
  uninstall: "Uninstall", confirm_t: "Uninstall {name}?", confirm_b: "{platform} will open to uninstall it. Cloud saves are kept.",
  unknown_note: "Epic, GOG, Ubisoft and Xbox don't expose the last-played date: it shows as \"Unknown\"." },
});

S.gm = { res: null, sort: "size", drive: "*", idleDays: 90 };
const PLATFORM_BADGE = { Steam: "b-info", Epic: "b-muted", GOG: "b-warn", Ubisoft: "b-muted", Xbox: "b-safe" };

function renderGames() {
  $("#page-games").innerHTML = head(t("games.title"), t("games.sub")) +
    `<div class="card"><div class="row"><button class="btn primary" data-act="gm-scan">${icon("game")}${S.gm.res ? t("common.reanalyze") : t("common.analyze")}</button></div></div>
     <div class="task hidden" id="gmTask"></div><div id="gmBody"></div>`;
  renderGamesBody();
}

function renderGamesBody() {
  const g = S.gm, el = $("#gmBody");
  if (!el) return;
  if (!g.res) { el.innerHTML = `<div class="card">${empty(t("games.sub"), "game")}</div>`; return; }
  const all = g.res.games;
  const idle = all.filter(x => x.idle_days != null && x.idle_days >= g.idleDays);
  const drives = [...new Set(all.map(x => x.drive))].sort();
  let list = all.filter(x => g.drive === "*" || x.drive === g.drive);
  if (g.sort === "idle") list = [...list].sort((a, b) => (b.idle_days ?? -1) - (a.idle_days ?? -1) || b.size - a.size);
  const max = Math.max(1, ...list.map(x => x.size));
  el.innerHTML = `<div class="stats">${stat(t("games.total"), size(g.res.total), "", "game")}${stat(t("games.count"), num(all.length), "", "app")}
      ${stat(t("games.idle", { n: g.idleDays }), size(idle.reduce((a, x) => a + x.size, 0)), "accent", "clock")}</div>
    <div class="card"><div class="row" style="margin-bottom:12px"><span class="grow small muted">${t("games.unknown_note")}</span>
      <label class="muted">${t("games.sort")}</label><select id="gmSort"><option value="size" ${g.sort === "size" ? "selected" : ""}>${t("games.by_size")}</option>
        <option value="idle" ${g.sort === "idle" ? "selected" : ""}>${t("games.by_idle")}</option></select>
      <label class="muted">${t("games.drive")}</label><select id="gmDrive"><option value="*">${t("games.all")}</option>${drives.map(d => `<option ${d === g.drive ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></div>
    <div class="tbl-wrap"><table><thead><tr><th>${t("games.game")}</th><th>${t("games.platform")}</th><th class="num">${t("common.size")}</th><th style="width:16%"></th>
      <th>${t("games.last")}</th><th>${t("games.drive")}</th><th></th></tr></thead><tbody>${list.map((x, i) => `<tr>
      <td><b>${esc(x.name)}</b></td><td><span class="badge ${PLATFORM_BADGE[x.platform] || "b-muted"}">${esc(x.platform)}</span></td>
      <td class="num">${size(x.size)}</td><td><div class="bar"><i style="width:${(x.size / max * 100).toFixed(1)}%"></i></div></td>
      <td>${x.idle_days == null ? `<span class="muted small">${t("games.never")}</span>` : x.idle_days === 0 ? t("games.today")
        : `<span class="${x.idle_days >= g.idleDays ? "badge b-warn" : ""}">${t("games.ago", { n: num(x.idle_days) })}</span>`}</td>
      <td class="small">${esc(x.drive)}</td>
      <td class="act">${openBtn(x.path)}<button class="btn sm" data-act="gm-uninstall" data-i="${all.indexOf(x)}">${t("games.uninstall")}</button></td></tr>`).join("")}</tbody></table></div></div>`;
}

async function gamesScan() {
  try {
    const res = await runJob(api("inv_games"), $("#gmTask"), t("games.loading"));
    if (res) { S.gm.res = res; renderGames(); }
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderGames);
PAGE_ENTER.games = () => { if (!S.gm.res) gamesScan(); };
Object.assign(ACTIONS, {
  "gm-scan": () => gamesScan(),
  "gm-uninstall": async el => {
    const x = S.gm.res.games[+el.dataset.i];
    const ok = await modal({ title: t("games.confirm_t", { name: x.name }), body: `<p>${t("games.confirm_b", { platform: x.platform })}</p>`, ok: t("games.uninstall") });
    if (ok) api("inv_game_uninstall", x.platform, x.id).catch(fail);
  },
});
CHANGE_HOOKS.push(el => {
  if (el.id === "gmSort") { S.gm.sort = el.value; renderGamesBody(); }
  if (el.id === "gmDrive") { S.gm.drive = el.value; renderGamesBody(); }
});
