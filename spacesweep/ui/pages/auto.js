"use strict";
/* Automatic upkeep page: scheduled check, weekly safe clean, Downloads rules. */

Object.assign(I18N.es, { auto: {
  nav: "Automático", title: "Mantenimiento automático",
  sub: "SpaceSweep puede cuidar el disco por ti sin quedarse abierto: el Programador de tareas de Windows lo abre un par de segundos, hace su trabajo y se cierra. No usa memoria en segundo plano ni necesita administrador.",
  alert: "Aviso de poco espacio", alert_d: "Te muestra una notificación de Windows cuando el disco del sistema baja del porcentaje libre que elijas. Máximo un aviso al día.",
  percent: "Avisar con menos de", free_pct: "% libre", check_at: "Revisar cada día a las", after_logon: "y 5 minutos después de iniciar sesión",
  weekly: "Limpieza semanal", weekly_d: "Borra lo del grupo «Seguro de borrar» de Limpieza (cachés y temporales que se regeneran). Lo que requiere administrador se omite. Te avisa cuánto liberó.",
  day: "Día", at: "a las", recycle: "También vaciar de la Papelera lo que lleve más de", recycle_d: "0 = no tocar la Papelera",
  dl: "Reglas para Descargas", dl_d: "Se aplican en la revisión diaria. Lo que se quita va a la Papelera, así que puedes recuperarlo.",
  dl_partial: "Descargas incompletas de más de", dl_inst: "Instaladores de más de", dl_dups: "Copias exactas («archivo (1).exe»)", dl_org: "Ordenar los archivos sueltos por tipo",
  days_u: "días", save: "Guardar y programar", saved: "Guardado. Tareas de Windows actualizadas.", task_err: "No se pudo programar la tarea: {msg}",
  status: "Estado", task_check: "Revisión diaria", task_clean: "Limpieza semanal", next: "Próxima: {t}", off: "Desactivada",
  test: "Probar notificación", run_check: "Revisar ahora", run_clean: "Limpiar ahora", test_t: "SpaceSweep", test_b: "Así se verán los avisos.",
  log: "Lo que se hizo automáticamente", log_empty: "Todavía no ha corrido ninguna tarea automática.",
  k_alert: "Aviso de poco espacio", k_clean: "Limpieza semanal", k_downloads: "Reglas de Descargas",
  d_alert: "{pct}% libre en {d}", d_clean: "Liberó {size}", d_downloads: "{n} a la Papelera ({size}), {m} ordenados",
  ran_check: "Revisión completada.", ran_clean: "Limpieza completada: {size} liberados.",
  days: { MON: "Lunes", TUE: "Martes", WED: "Miércoles", THU: "Jueves", FRI: "Viernes", SAT: "Sábado", SUN: "Domingo" } },
});
Object.assign(I18N.en, { auto: {
  nav: "Automatic", title: "Automatic upkeep",
  sub: "SpaceSweep can look after your drive without staying open: Windows Task Scheduler starts it for a couple of seconds, it does its job and exits. No background memory, no administrator rights.",
  alert: "Low-space alert", alert_d: "Shows a Windows notification when the system drive drops below the free percentage you choose. At most one alert a day.",
  percent: "Alert below", free_pct: "% free", check_at: "Check every day at", after_logon: "and 5 minutes after you sign in",
  weekly: "Weekly cleanup", weekly_d: "Deletes the Cleanup \"Safe to delete\" group (caches and temp files that rebuild themselves). Items needing administrator are skipped. Tells you how much it freed.",
  day: "Day", at: "at", recycle: "Also empty Recycle Bin items older than", recycle_d: "0 = leave the Recycle Bin alone",
  dl: "Downloads rules", dl_d: "Applied by the daily check. Removed files go to the Recycle Bin, so you can restore them.",
  dl_partial: "Unfinished downloads older than", dl_inst: "Installers older than", dl_dups: "Exact copies ('file (1).exe')", dl_org: "Sort loose files by type",
  days_u: "days", save: "Save and schedule", saved: "Saved. Windows tasks updated.", task_err: "Could not schedule the task: {msg}",
  status: "Status", task_check: "Daily check", task_clean: "Weekly cleanup", next: "Next: {t}", off: "Off",
  test: "Test notification", run_check: "Check now", run_clean: "Clean now", test_t: "SpaceSweep", test_b: "This is how alerts will look.",
  log: "What ran automatically", log_empty: "No automatic task has run yet.",
  k_alert: "Low-space alert", k_clean: "Weekly cleanup", k_downloads: "Downloads rules",
  d_alert: "{pct}% free on {d}", d_clean: "Freed {size}", d_downloads: "{n} to the Recycle Bin ({size}), {m} sorted",
  ran_check: "Check finished.", ran_clean: "Cleanup finished: {size} freed.",
  days: { MON: "Monday", TUE: "Tuesday", WED: "Wednesday", THU: "Thursday", FRI: "Friday", SAT: "Saturday", SUN: "Sunday" } },
});

S.au = { st: null, form: null };

const toggle = (id, on) => `<label class="switch"><input type="checkbox" id="${id}" ${on ? "checked" : ""}><span></span></label>`;
const numIn = (id, v, w = 64) => `<input type="text" inputmode="numeric" id="${id}" value="${esc(v)}" style="width:${w}px">`;
const timeIn = (id, v) => `<input type="time" id="${id}" value="${esc(v)}">`;

function renderAuto() {
  const a = S.au, f = a.form;
  const el = $("#page-auto");
  el.innerHTML = head(t("auto.title"), t("auto.sub"));
  if (!f) { el.innerHTML += `<div class="card">${empty(I18N[S.lang].common.working, "clock")}</div>`; return; }
  const st = a.st;
  const taskLine = (mode, label) => {
    const info = st && st.tasks[mode];
    return `<div class="row"><span class="badge ${info ? "b-safe" : "b-muted"}">${info ? icon("check") : ""}${label}</span>
      <span class="small muted">${info ? t("auto.next", { t: info.next_run }) : t("auto.off")}</span></div>`;
  };
  el.innerHTML += `
    <div class="card"><div class="row"><h2 class="grow">${icon("alert")}${t("auto.alert")}</h2>${toggle("auAlert", f.alert.enabled)}</div>
      <p class="lead">${t("auto.alert_d")}</p>
      <div class="row">${t("auto.percent")} ${numIn("auPct", f.alert.percent, 52)} ${t("auto.free_pct")} · ${t("auto.check_at")} ${timeIn("auAlertTime", f.alert.time)}
        <span class="small muted">${t("auto.after_logon")}</span></div></div>
    <div class="card"><div class="row"><h2 class="grow">${icon("sweep")}${t("auto.weekly")}</h2>${toggle("auWeekly", f.weekly_clean.enabled)}</div>
      <p class="lead">${t("auto.weekly_d")}</p>
      <div class="row">${t("auto.day")} <select id="auDay">${Object.entries(I18N[S.lang].auto.days).map(([k, v]) => `<option value="${k}" ${f.weekly_clean.day === k ? "selected" : ""}>${v}</option>`).join("")}</select>
        ${t("auto.at")} ${timeIn("auWeeklyTime", f.weekly_clean.time)}</div>
      <div class="row" style="margin-top:8px">${t("auto.recycle")} ${numIn("auRecycle", f.weekly_clean.recycle_days || 0)} ${t("auto.days_u")}
        <span class="small muted">${t("auto.recycle_d")}</span></div></div>
    <div class="card"><div class="row"><h2 class="grow">${icon("download")}${t("auto.dl")}</h2>${toggle("auDl", f.downloads.enabled)}</div>
      <p class="lead">${t("auto.dl_d")}</p>
      <div style="display:grid;gap:8px">
        <div class="row">${t("auto.dl_partial")} ${numIn("auPartial", f.downloads.partial_days)} ${t("auto.days_u")}</div>
        <div class="row">${t("auto.dl_inst")} ${numIn("auInst", f.downloads.installer_days)} ${t("auto.days_u")}</div>
        <label class="row"><input type="checkbox" id="auDups" ${f.downloads.duplicates ? "checked" : ""}> ${t("auto.dl_dups")}</label>
        <label class="row"><input type="checkbox" id="auOrg" ${f.downloads.organize ? "checked" : ""}> ${t("auto.dl_org")}</label></div></div>
    <div class="sticky-actions"><span class="grow"></span><button class="btn primary" data-act="au-save">${icon("check")}${t("auto.save")}</button></div>
    <div class="task hidden" id="auTask"></div>
    <div class="card"><h2>${icon("clock")}${t("auto.status")}</h2>
      <div style="display:grid;gap:8px;margin:8px 0 14px">${taskLine("check", t("auto.task_check"))}${taskLine("clean", t("auto.task_clean"))}</div>
      <div class="row"><button class="btn sm" data-act="au-test">${t("auto.test")}</button>
        <button class="btn sm" data-act="au-run" data-mode="check">${icon("refresh")}${t("auto.run_check")}</button>
        <button class="btn sm" data-act="au-run" data-mode="clean">${icon("sweep")}${t("auto.run_clean")}</button></div></div>
    <div id="shellCard"></div>
    <div class="card"><h2>${icon("history")}${t("auto.log")}</h2>${autoLog()}</div>`;
  if (typeof renderShellCard === "function") renderShellCard();
}

function autoLog() {
  const log = (S.au.st && S.au.st.log) || [];
  if (!log.length) return `<p class="muted">${t("auto.log_empty")}</p>`;
  const detail = e => e.kind === "alert" ? t("auto.d_alert", { pct: e.percent, d: (e.drive || "").slice(0, 2) })
    : e.kind === "clean" ? t("auto.d_clean", { size: size(e.freed) })
    : t("auto.d_downloads", { n: num(e.recycled), size: size(e.bytes), m: num(e.sorted) });
  return `<div class="tbl-wrap"><table><tbody>${log.map(e => `<tr><td class="small">${new Date(e.time * 1000).toLocaleString()}</td>
    <td><b>${t("auto.k_" + e.kind)}</b></td><td class="small">${detail(e)}</td></tr>`).join("")}</tbody></table></div>`;
}

function readAutoForm() {
  const v = id => $("#" + id);
  return {
    alert: { enabled: v("auAlert").checked, percent: +v("auPct").value || 10, time: v("auAlertTime").value || "10:00" },
    weekly_clean: { enabled: v("auWeekly").checked, day: v("auDay").value, time: v("auWeeklyTime").value || "12:00",
      recycle_days: +v("auRecycle").value || 0 },
    downloads: { enabled: v("auDl").checked, partial_days: +v("auPartial").value || 7, installer_days: +v("auInst").value || 30,
      duplicates: v("auDups").checked, organize: v("auOrg").checked },
  };
}

async function autoLoad() {
  try {
    S.au.st = await api("auto_status");
    S.au.form = JSON.parse(JSON.stringify(S.au.st.settings));
    renderAuto();
  } catch (e) { fail(e); }
}

PAGE_RENDERERS.push(renderAuto);
PAGE_ENTER.auto = autoLoad;
Object.assign(ACTIONS, {
  "au-save": async () => {
    try {
      const res = await api("auto_save", readAutoForm());
      const bad = Object.values(res.tasks).filter(x => !x.ok);
      bad.length ? bad.forEach(x => toast(t("auto.task_err", { msg: x.message }), true)) : toast(t("auto.saved"));
      await autoLoad();
    } catch (e) { fail(e); }
  },
  "au-test": () => api("auto_test_notify", I18N[S.lang].auto.test_t, I18N[S.lang].auto.test_b).catch(fail),
  "au-run": async el => {
    try {
      const res = await runJob(api("auto_run", el.dataset.mode), $("#auTask"), I18N[S.lang].common.working);
      if (!res) return;
      toast(el.dataset.mode === "clean" ? t("auto.ran_clean", { size: size(res.freed) }) : t("auto.ran_check"));
      loadDrives();
      autoLoad();
    } catch (e) { fail(e); }
  },
});
CHANGE_HOOKS.push(el => {
  if (el.id && el.id.startsWith("au") && S.au.form && $("#auAlert")) S.au.form = readAutoForm();
});
