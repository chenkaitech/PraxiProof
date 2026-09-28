async function renderDashboard() {
  const [d, skills] = await Promise.all([rapi("/api/dashboard"), rapi("/api/skills")]);
  const m = d.latest_manual, v = d.latest_video, metrics = d.metrics;
  const activeRun = d.recent_runs.find((r) => busy(r.status));
  const doneRun = d.latest_run;
  const stageState = (i) => {
    if (m && busy(m.status)) return i === 0 ? "done" : i === 1 ? "active" : "";
    if (activeRun) return i < 2 ? "done" : (i === 2 && activeRun.stage !== "verifying") || (i === 3 && activeRun.stage === "verifying") ? "active" : "";
    if (doneRun) return i < 4 || skills.some((s) => s.run_id === doneRun.id) ? "done" : "";
    return m?.status === "ready" && i < 2 ? "done" : "";
  };
  const stageIcons = [ICON.stageManual, ICON.stageIR, ICON.stageAlign, ICON.stageVerify, ICON.stageSkill];
  const metricCard = (title, metric, tone, subtitle) => `<div class="card metric">${ring(metric?.value, tone)}<div class="ring-label">${metric ? Math.round(metric.value * 100) + "%" : "-"}</div></div>
    <div><h4>${esc(title)}</h4><p>${esc(subtitle)}</p></div></div>`;
  const violations = metrics?.violations ?? 0;

  view.innerHTML = `
    <div class="page-head">
      <div><h1>${t("dash.title")}</h1><p>${t("dash.subtitle")}</p></div>
      <div class="spacer"></div>
      <button class="btn ghost big" id="pipeline">${t("pipe.button")}</button>
      <button class="btn primary big" id="start">${t("common.start")}</button>
    </div>

    <div class="grid-2">
      <section class="card upload-card manual">
        <div class="card-head"><div class="icon-chip blue">${ICON.doc}</div><div><h3>${t("dash.manual_title")}</h3><p>${t("dash.manual_sub")}</p></div></div>
        ${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", t("dash.manual_drop"))}
        <label class="procedure-input">${t("dash.procedure")} <input id="procedure" placeholder="${esc(t("dash.procedure_ph"))}"></label>
        ${manualRow(m)}
        <div class="stats"><div>${ICON.list}<div><b>${m?.counts?.safety_rules ?? "-"}</b><small>${t("dash.safety_rules")}</small></div></div><div>${ICON.doc}<div><b>${m?.counts?.rules ?? "-"}</b><small>${esc(t("dash.rules_steps", { steps: m?.counts?.steps ?? "-" }))}</small></div></div></div>
      </section>
      <section class="card upload-card video">
        <div class="card-head"><div class="icon-chip green"><svg viewBox="0 0 24 24"><path d="M9 7l8 5-8 5z" fill="#fff"/></svg></div><div><h3>${t("dash.video_title")}</h3><p>${t("dash.video_sub")}</p></div></div>
        ${dropzone("video", "video/*", t("dash.video_drop"))}
        ${videoRow(v)}
        <div class="stats"><div>${ICON.clock}<div><b>${v ? fmtDuration(v.meta.duration) : "-"}</b><small>${t("dash.duration")}</small></div></div><div>${ICON.cam}<div><b>${v ? esc(v.meta.format_name.toUpperCase()) : "-"}</b><small>${t("dash.format")}</small></div></div><div>${ICON.screen}<div><b>${v ? `${v.meta.height}p` : "-"}</b><small>${t("dash.resolution")}</small></div></div></div>
      </section>
    </div>

    <section class="card pipeline">
      ${stageIcons.map((icon, i) => `<div class="stage ${stageState(i)}"><div class="bubble">${icon}</div><div><b>${t(`stage.${i}`)}</b><small>${t(`stage.${i}.sub`)}</small></div></div>${i < 4 ? ICON.arrow : ""}`).join("")}
    </section>

    <div class="grid-4">
      ${metricCard(t("metric.trace"), metrics?.evidence_traceability, "blue", metrics ? t("metric.trace_sub", { n: metrics.evidence_traceability.numerator, d: metrics.evidence_traceability.denominator }) : t("metric.empty"))}
      ${metricCard(t("metric.safety"), metrics?.safety_coverage, "green", metrics ? t("metric.safety_sub", { n: metrics.safety_coverage.numerator, d: metrics.safety_coverage.denominator }) : "")}
      ${metricCard(t("metric.steps"), metrics?.step_coverage, "blue", metrics ? t("metric.steps_sub", { n: metrics.step_coverage.numerator, d: metrics.step_coverage.denominator }) : "")}
      <div class="card metric">${ring(metrics ? Math.min(violations / Math.max(metrics.counts ? Object.values(metrics.counts).reduce((a, b) => a + b, 0) : 1, 1), 1) : 0, "red")}<div class="ring-label red">${metrics ? violations : "-"}</div></div>
        <div><h4>${t("metric.violations")}</h4><p>${metrics ? esc(violations === 1 ? t("metric.violations_one") : t("metric.violations_many", { n: violations })) : ""}</p></div></div>
    </div>

    <div class="split mt">
      <section class="card"><div class="card-head"><h3>${t("dash.recent")}</h3><div class="spacer"></div><a href="#runs">${t("dash.view_runs")}</a></div>${runsTable(d.recent_runs.slice(0, 6), true)}</section>
      <section class="card"><div class="card-head"><h3>${t("dash.findings")}</h3><div class="spacer"></div>${doneRun ? `<a href="#run/${esc(doneRun.id)}">${t("dash.view_findings")}</a>` : ""}</div>
        ${d.findings.length ? d.findings.slice(0, 2).map((f) => findingCard(f, true)).join('<div style="height:10px"></div>') : `<p class="empty">${doneRun ? t("dash.no_findings") : t("dash.findings_empty")}</p>`}
      </section>
    </div>`;

  $("#start").addEventListener("click", () => openRunDialog());
  $("#pipeline").addEventListener("click", () => openPipelineDialog());
  bindDropzones(view);
  bindRowLinks(view);
  schedulePoll((m && busy(m.status)) || !!activeRun);
}
