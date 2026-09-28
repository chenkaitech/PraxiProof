async function renderRun(id) {
  const [run, skills] = await Promise.all([rapi(`/api/runs/${encodeURIComponent(id)}`), rapi("/api/skills")]);
  const head = `<div class="page-head"><div><h1>${esc(run.id)} · ${esc(run.video_name)}</h1><p>${esc(run.procedure)} · ${esc(run.manual_name)}</p>${run.video_note ? `<p><span class="badge warn">${esc(t("video.note"))}</span> ${esc(run.video_note)}</p>` : ""}</div><div class="spacer"></div><a class="btn ghost" href="#runs">${t("run.all")}</a></div>`;
  if (busy(run.status) || run.status === "failed") {
    view.innerHTML = `${head}<section class="card">${run.status === "failed" ? `<p class="error-text">${esc(t("run.failed", { error: run.error }))}</p>` : `<p>${ICON.spin} ${esc(t("run.working", { stage: stageLabel(run.stage) }))}</p>`}</section>`;
    return schedulePoll(busy(run.status));
  }
  const report = run.report;
  const skill = skills.find((s) => s.run_id === run.id);
  const order = { VIOLATION: 0, INSUFFICIENT_EVIDENCE: 1, UNVERIFIED: 2, PASS: 3 };
  const verdicts = [...report.verdicts].sort((a, b) => order[a.status] - order[b.status] || a.rule_id.localeCompare(b.rule_id));
  view.innerHTML = `${head}
    <section class="card run-head">${resultBadge(run)}<div class="counts">${Object.entries(run.counts).map(([k, n]) => `${statusBadge(k)} <b>${n}</b>`).join(" &nbsp; ")}</div><div class="spacer" style="flex:1"></div>
      ${skill ? `<a class="btn ghost" href="#skill/${esc(skill.id)}">${esc(t("run.view_skill", { id: skill.id }))}</a>` : ""}
      <button class="btn primary" id="compile">${skill ? t("run.recompile_skill") : t("run.compile_skill")}</button></section>
    <div class="split mt">
      <div class="stack">
        <section class="card"><div class="card-head"><h3>${t("run.verdicts")}</h3><p>${t("run.verdicts_sub")}</p>${verdicts.some((v) => v.status === "PASS") ? `<button class="btn ghost small" id="toggle-passed" type="button">${t("run.expand_passed")}</button>` : ""}</div>
          <div class="verdicts">${verdicts.map((v) => {
            const head = `<div class="verdict-head"><span class="title">${esc(v.rule_id)} · ${esc(v.statement)}</span>${statusBadge(v.status)}${severityBadge(v.severity)}${categoryBadge(v.category)}</div>
              <p class="reason"><code>${esc(signature(v.constraint))}</code> ${esc(verdictText(v.reason_code, v.reason_params, v.reason))}</p>`;
            const evidence = `<div class="evidence-pair">${evidenceLine(v.requirement_evidence_ids, run.evidence, run.video_id)}${evidenceLine(v.observation_evidence_ids, run.evidence, run.video_id)}</div>`;
            // A passed rule is a summary line; its evidence opens on demand. Anything that needs attention stays open.
            if (v.status === "PASS") return `<details class="verdict PASS"><summary>${head}</summary>${evidence}</details>`;
            return `<div class="verdict ${v.status}">${head}
              ${v.needed_evidence ? `<p class="needed">${esc(t("run.needed", { text: verdictText(v.needed_code, v.reason_params, v.needed_evidence) }))}</p>` : ""}
              ${evidence}
              <div class="verdict-actions"><span class="muted">${t("run.review")}</span>
                <button class="btn small ${v.review === "accepted" ? "success" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="accepted">${t("run.confirm")}</button>
                <button class="btn small ${v.review === "rejected" ? "danger" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="rejected">${t("run.reject")}</button>
                <span class="spacer" style="flex:1"></span><button class="btn small why" data-why="${esc(v.rule_id)}">✦ ${t("rca.why")}</button></div>
                <div class="why-slot" data-why-slot="${esc(v.rule_id)}"></div>
            </div>`;
          }).join("")}</div>
        </section>
        <section class="card"><div class="card-head"><h3>${t("run.alignment")}</h3><p>${t("run.alignment_sub")}</p></div>
          <table><thead><tr><th>${t("run.col_event")}</th><th>${t("run.col_observed")}</th><th>${t("run.col_matched")}</th><th>${t("run.col_method")}</th><th>${t("run.col_time")}</th></tr></thead><tbody>
          ${report.alignment.map((a) => { const e = run.observation.events.find((x) => x.event_id === a.event_id) || {}; return `<tr><td class="id">${esc(a.event_id)}</td><td>${esc(a.observed_label)}</td><td>${esc(a.aligned_labels.join(", ") || "-")}</td><td>${esc(t(`method.${a.method}`))}</td><td>${fmtTime(e.start)} to ${fmtTime(e.end)}</td></tr>`; }).join("")}
          </tbody></table>
          ${run.traceability_issues?.length ? `<p class="error-text">${esc(t("run.trace_issues", { issues: run.traceability_issues.join("; ") }))}</p>` : ""}
        </section>
      </div>
      <div class="stack sticky">
        ${run.video_id ? `<section class="card"><div class="card-head"><h3>${t("run.video")}</h3></div><video id="player" controls preload="metadata" src="/api/videos/${esc(run.video_id)}/file"></video></section>` : ""}
        <section class="card"><div class="card-head"><h3>${t("run.agent")}</h3></div>
          <div class="chat"><textarea id="question" placeholder="${esc(t("run.agent_ph"))}"></textarea>
          <button class="btn primary" id="ask">${t("run.ask")}</button><div id="answer"></div></div>
        </section>
      </div>
    </div>`;

  $("#toggle-passed")?.addEventListener("click", (e) => {
    const open = e.target.dataset.open !== "1";
    view.querySelectorAll("details.verdict").forEach((d) => (d.open = open));
    e.target.dataset.open = open ? "1" : "0";
    e.target.textContent = t(open ? "run.collapse_passed" : "run.expand_passed");
  });
  view.querySelectorAll("[data-review]").forEach((b) =>
    b.addEventListener("click", async () => {
      const current = report.verdicts.find((v) => v.rule_id === b.dataset.review).review;
      const decision = current === b.dataset.decision ? null : b.dataset.decision;
      await api(`/api/runs/${encodeURIComponent(run.id)}/verdicts/${encodeURIComponent(b.dataset.review)}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) });
      render(true);
    })
  );
  view.querySelectorAll("[data-why]").forEach((b) => b.addEventListener("click", () => askWhy(run.id, b.dataset.why, view.querySelector(`[data-why-slot="${CSS.escape(b.dataset.why)}"]`), b)));
  $("#compile").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const s = await api(`/api/runs/${encodeURIComponent(run.id)}/skill`, { method: "POST" });
      toast(t("run.skill_ok", { name: s.name }));
      location.hash = `#skill/${s.id}`;
    } catch (err) {
      toast(err.message);
      e.target.disabled = false;
    }
  });
  $("#ask").addEventListener("click", async (e) => {
    const question = $("#question").value.trim();
    if (!question) return;
    e.target.disabled = true;
    $("#answer").innerHTML = `<p>${ICON.spin} ${esc(t("common.thinking"))}</p>`;
    try {
      const r = await api("/api/agent/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, run_id: run.id, language: LANG }) });
      $("#answer").innerHTML = `<div class="answer">${mdLite(r.answer)}</div>${r.tool_calls.length ? traceView(r.tool_calls) : `<p class="muted">${esc(t("run.tools", { tools: t("common.none") }))}</p>`}`;
    } catch (err) {
      $("#answer").innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
    }
    e.target.disabled = false;
  });
  bindSeek(view);
}
