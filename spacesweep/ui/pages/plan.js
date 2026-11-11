"use strict";
/* "Free N GB" assistant: one plan across every SpaceSweep source, safest first. */

Object.assign(I18N.es, { plan: {
  nav: "Liberar N GB", title: "Asistente: liberar N GB",
  sub: "Dime cuánto espacio necesitas y SpaceSweep arma un plan combinando todo lo que sabe hacer, empezando por lo que no te quita nada. Cada paso se hace en su propia página, con su explicación y su confirmación.",
  drive: "Disco", target: "Necesito liberar", gb: "GB", build: "Armar plan", building: "Revisando todas las fuentes (puede tardar un minuto)…",
  reachable: "Con los primeros {n} pasos llegas a tu meta de {target}.", short: "Todo junto da {total}: no alcanza los {target}. Considera mover juegos o datos a otro disco.",
  possible: "Posible en total", free_now: "Libre ahora", after: "Libre después de la meta",
  go: "Ir", estimate: "estimado",
  r0: "Sin pérdida", r1: "Pierdes algo menor", r2: "Cambia de lugar o forma", r3: "Hay que reinstalar",
  empty: "Elige el disco y cuántos GB quieres liberar." },
});
Object.assign(I18N.en, { plan: {
  nav: "Free N GB", title: "Assistant: free N GB",
  sub: "Tell SpaceSweep how much space you need and it builds a plan from everything it can do, starting with what costs you nothing. Each step runs on its own page, with its own explanation and confirmation.",
  drive: "Drive", target: "I need to free", gb: "GB", build: "Build plan", building: "Checking every source (may take a minute)…",
  reachable: "The first {n} steps reach your goal of {target}.", short: "Everything together gives {total}: short of {target}. Consider moving games or data to another drive.",
  possible: "Possible in total", free_now: "Free now", after: "Free after the goal",
  go: "Go", estimate: "estimate",
  r0: "Nothing lost", r1: "Lose something minor", r2: "Moves or changes form", r3: "Needs reinstalling",
  empty: "Pick the drive and how many GB you want to free." },
});

S.pl = { drive: null, gb: "50", res: null };

function renderPlan() {
  const p = S.pl;
  if (!p.drive) p.drive = (S.drives.find(d => d.system) || S.drives[0] || {}).root;
  const opts = S.drives.map(d => `<option value="${esc(d.root)}" ${d.root === p.drive ? "selected" : ""}>${esc(d.letter)}: ${esc(d.label)} — ${size(d.free)} ${t("common.free")}</option>`).join("");
  $("#page-plan").innerHTML = head(t("plan.title"), t("plan.sub")) +
    `<div class="card"><div class="row"><label class="muted">${t("plan.drive")}</label><select id="plDrive">${opts}</select>
      <label class="muted">${t("plan.target")}</label><input type="text" inputmode="numeric" id="plGb" value="${esc(p.gb)}" style="width:80px"> ${t("plan.gb")}
      <span class="grow"></span><button class="btn primary" data-act="pl-build">${icon("sweep")}${t("plan.build")}</button></div></div>
     <div class="task hidden" id="plTask"></div><div id="plBody"></div>`;
  renderPlanBody();
}

function renderPlanBody() {
  const r = S.pl.res, el = $("#plBody");
  if (!el) return;
  if (!r) { el.innerHTML = `<div class="card">${empty(t("plan.empty"), "sweep")}</div>`; return; }
  const n = r.steps.findIndex(s => s.reaches) + 1;
  const scale = Math.max(r.total_possible, r.target) || 1;
  let html = `<div class="stats">${stat(t("plan.free_now"), size(r.free), "", "disk")}${stat(t("plan.possible"), size(r.total_possible), r.reachable ? "accent" : "warn", "sweep")}
    ${stat(t("plan.after"), size(r.free + Math.min(r.target, r.total_possible)), "", "check")}</div>
    <div class="card"><div class="target-bar"><i style="width:${(Math.min(r.total_possible, scale) / scale * 100).toFixed(1)}%"></i>
      <b style="left:${(r.target / scale * 100).toFixed(1)}%"></b></div>
      <p class="${r.reachable ? "" : "muted"}">${r.reachable ? t("plan.reachable", { n, target: size(r.target) }) : t("plan.short", { total: size(r.total_possible), target: size(r.target) })}</p>
      <div>${r.steps.map((s, i) => `<div class="plan-step ${n && i < n ? "reached" : ""}"><span class="n">${i + 1}</span>
        <div><b>${L(s.title)}</b> <span class="badge risk-${s.risk}">${t("plan.r" + s.risk)}</span><div class="small muted">${L(s.detail)}</div></div>
        <div class="num"><b>${size(s.size)}</b>${s.estimate ? `<div class="small muted">${t("plan.estimate")}</div>` : ""}<div class="small muted">Σ ${size(s.cumulative)}</div></div>
        <button class="btn sm" data-act="nav" data-page="${s.page}">${t("plan.go")} ${icon("chevron")}</button></div>`).join("")}</div></div>`;
  el.innerHTML = html;
}

PAGE_RENDERERS.push(renderPlan);
Object.assign(ACTIONS, {
  "pl-build": async () => {
    const p = S.pl;
    p.drive = $("#plDrive").value;
    p.gb = $("#plGb").value.replace(",", ".");
    if (!(+p.gb > 0)) return toast(t("plan.empty"), true);
    try {
      const res = await runJob(api("plan_build", p.drive, +p.gb), $("#plTask"), t("plan.building"));
      if (res) { p.res = res; renderPlanBody(); }
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => { if (el.id === "plDrive") { S.pl.drive = el.value; S.pl.res = null; renderPlanBody(); } });
