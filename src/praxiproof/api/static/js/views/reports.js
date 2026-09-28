async function renderReports() {
  const runs = (await rapi("/api/runs")).filter((r) => r.status === "done" && matches(r));
  const details = await Promise.all(runs.slice(0, 20).map((r) => rapi(`/api/runs/${encodeURIComponent(r.id)}`)));
  const pct = (m) => (m ? `<span class="nowrap">${Math.round(m.value * 100)}% <span class="muted">(${m.numerator}/${m.denominator})</span></span>` : "-");
  view.innerHTML = `<div class="page-head"><div><h1>${t("reports.title")}</h1><p>${t("reports.subtitle")}</p></div></div>
    <section class="card">${details.length ? `<table><thead><tr><th>${t("reports.col_run")}</th><th>${t("runs.col_video")}</th><th>${t("runs.col_result")}</th><th>${t("reports.col_trace")}</th><th>${t("reports.col_safety")}</th><th>${t("reports.col_steps")}</th><th>${t("reports.col_alignment")}</th><th>${t("reports.col_pass")}</th><th>${t("reports.col_violation")}</th><th>${t("reports.col_unverified")}</th><th>${t("reports.col_insufficient")}</th></tr></thead><tbody>
    ${details.map((r) => `<tr class="clickable" data-href="#run/${esc(r.id)}"><td class="id">${esc(r.id)}</td><td>${esc(r.video_name)}</td><td>${resultBadge(r)}</td><td>${pct(r.metrics.evidence_traceability)}</td><td>${pct(r.metrics.safety_coverage)}</td><td>${pct(r.metrics.step_coverage)}</td><td>${pct(r.metrics.observation_alignment)}</td>
      <td>${r.counts.PASS}</td><td>${r.counts.VIOLATION}</td><td>${r.counts.UNVERIFIED}</td><td>${r.counts.INSUFFICIENT_EVIDENCE}</td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">${t("reports.none")}</p>`}</section>`;
  bindRowLinks(view);
}
