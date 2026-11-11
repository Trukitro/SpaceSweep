"use strict";
/* Export a shareable report (HTML + CSV) from the Home page. */

Object.assign(I18N.es, { rep: {
  btn: "Exportar reporte", working: "Armando el reporte (analiza la Limpieza del disco del sistema)…",
  done_t: "Reporte listo", done_b: "Se guardaron en tu carpeta Documentos. Las rutas de tu usuario aparecen como ~\\… para que puedas compartirlo.",
  open_html: "Abrir reporte (HTML)", open_csv: "Abrir CSV (Excel)", show: "Mostrar en la carpeta" },
});
Object.assign(I18N.en, { rep: {
  btn: "Export report", working: "Building the report (runs the Cleanup analysis of the system drive)…",
  done_t: "Report ready", done_b: "Saved in your Documents folder. Paths under your user folder appear as ~\\… so you can share it.",
  open_html: "Open report (HTML)", open_csv: "Open CSV (Excel)", show: "Show in folder" },
});

Object.assign(ACTIONS, {
  "report": async () => {
    try {
      go("home");
      const res = await runJob(api("report_export", S.lang), $("#repTask"), t("rep.working"));
      if (!res) return;
      const ok = await modal({ title: t("rep.done_t"), body: `<p>${t("rep.done_b")}</p>
        <div class="subpaths"><div><span class="path">${esc(pp(res.html))}</span></div><div><span class="path">${esc(pp(res.csv))}</span></div></div>
        <div class="row" style="margin-top:12px"><button class="btn" data-act="report-open" data-path="${esc(res.csv)}">${t("rep.open_csv")}</button>
        <button class="btn ghost" data-act="open" data-path="${esc(res.html)}">${t("rep.show")}</button></div>`, ok: t("rep.open_html") });
      if (ok) api("report_open", res.html).catch(fail);
    } catch (e) { fail(e); }
  },
  "report-open": el => api("report_open", el.dataset.path).catch(fail),
});
