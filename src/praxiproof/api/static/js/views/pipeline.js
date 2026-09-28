async function renderPipeline(id) {
  const p = await rapi(`/api/pipelines/${encodeURIComponent(id)}`);
  const failed = p.status === "failed";
  const order = ["compiling", "verifying", "packaging"];
  const current = p.status === "done" ? 3 : order.indexOf(p.stage);
  const state = (i) => (p.status === "done" || i < current ? "done" : i === current ? (failed ? "failed" : "active") : "");
  const detail = [
    p.manual.status === "ready"
      ? `${esc(p.manual.procedure || "")} · ${p.manual.counts?.rules ?? "-"} ${esc(t("dash.rules_steps", { steps: p.manual.counts?.steps ?? "-" }))}`
      : esc(t(`status.${p.manual.status}`)),
    p.run ? (p.run.status === "done" ? resultBadge(p.run) : esc(p.run.stage ? stageLabel(p.run.stage) : t(`status.${p.run.status}`))) : "",
    p.skill_id ? `<span class="badge warn">${esc(t("skill.review.pending"))}</span>` : "",
    p.status === "done" ? esc(t("pipe.review_hint")) : "",
  ];
  const steps = ["pipe.step.compile", "pipe.step.verify", "pipe.step.package", "pipe.step.review"];
  view.innerHTML = `<div class="page-head"><div><h1>${esc(t("pipe.title", { id: p.id }))}</h1><p>${esc(p.manual_name)} + ${esc(p.video_name)}</p></div><div class="spacer"></div><a class="btn ghost" href="#runs">${t("run.all")}</a></div>
    <section class="card">
      ${failed ? `<p class="error-text">${esc(t("pipe.failed", { error: p.error }))}</p>` : busy(p.status) ? `<p class="muted">${ICON.spin} ${esc(t("pipe.working"))}</p>` : ""}
      <div class="steps">${steps.map((key, i) => `<div class="step ${state(i)}"><div class="num">${state(i) === "done" ? "✓" : i + 1}</div><div class="grow"><b>${t(key)}</b><small>${detail[i]}</small></div></div>`).join("")}</div>
      <div class="page-actions">
        <a class="btn ghost" href="#manual/${esc(p.manual_id)}">${t("pipe.open_manual")}</a>
        ${p.run_id ? `<a class="btn ghost" href="#run/${esc(p.run_id)}">${t("pipe.open_run")}</a>` : ""}
        ${p.skill_id ? `<a class="btn primary" href="#skill/${esc(p.skill_id)}">${t("pipe.open_skill")}</a>` : ""}
      </div>
    </section>`;
  schedulePoll(busy(p.status));
}
