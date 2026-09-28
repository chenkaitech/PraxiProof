const ciBar = (f1, ci, cls) => `<div class="bar ci"><span class="${cls}" style="width:${Math.max(2, f1 * 100)}%"></span><i style="left:${ci[0] * 100}%;width:${Math.max(1, (ci[1] - ci[0]) * 100)}%"></i></div>`;
const bar = (value, max, cls = "") => `<div class="bar"><span class="${cls}" style="width:${Math.max(2, Math.round((value / max) * 100))}%"></span></div>`;
const labelText = (s) => t(`eval.l.${String(s).toLowerCase().replace(/ /g, "_")}`);

function baselineChip(label, truth) {
  const cls = label === truth ? "ok" : label === "Compliant" ? "bad" : "warn";
  return `<span class="chip ${cls}">${esc(labelText(label))}</span>`;
}

function cvSection(cv) {
  const d = cv.ddm_vlm_cv;
  const row = (key, b, cls) => `<tr><td>${esc(t(key))}</td><td>${b.recordings}</td><td>${b.gold_events}</td><td>${b.precision.toFixed(3)}</td><td>${b.recall.toFixed(3)}</td>
    <td><b>${b.f1.toFixed(3)}</b> <span class="muted small">[${b.f1_ci95[0].toFixed(2)} to ${b.f1_ci95[1].toFixed(2)}]</span></td><td class="barcell">${ciBar(b.f1, b.f1_ci95, cls)}</td></tr>`;
  const rows = [
    d.all && row("eval.cv.row_ddm_all", d.all, "good"),
    d.untouched && row("eval.cv.row_ddm_untouched", d.untouched, "good"),
    cv.local_vlm?.all && row("eval.cv.row_vlm_all", cv.local_vlm.all, ""),
    cv.local_vlm?.untouched && row("eval.cv.row_vlm_untouched", cv.local_vlm.untouched, ""),
  ].filter(Boolean).join("");
  const paired = (k, key) => cv.paired_f1_difference?.[k] ? `<li>${esc(t(key, { d: cv.paired_f1_difference[k].difference.toFixed(3), lo: cv.paired_f1_difference[k].ci95[0].toFixed(2), hi: cv.paired_f1_difference[k].ci95[1].toFixed(2), n: cv.paired_f1_difference[k].recordings }))}</li>` : "";
  const folds = Object.entries(d.per_fold).map(([f, x]) => `<span class="chip ok">${esc(f.replace("fold", t("eval.cv.fold") + " "))}: F1 ${x.f1.toFixed(2)}</span>`).join("");
  return `<section class="card mt"><div class="card-head"><h3>${t("eval.cv")}</h3><p>${t("eval.cv_sub", { n: cv.protocol.recordings })}</p></div>
    <table class="eval-table"><thead><tr><th>${t("eval.cv.col_setup")}</th><th>${t("eval.cv.col_rec")}</th><th>${t("eval.cv.col_events")}</th><th>${t("eval.col_precision")}</th><th>${t("eval.col_recall")}</th><th>F1 [95% CI]</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <ul class="cv-notes">${paired("all", "eval.cv.paired_all")}${paired("untouched", "eval.cv.paired_untouched")}</ul>
    <p class="chips">${folds}</p><p class="muted small">${esc(t("eval.cv_note"))}</p></section>`;
}

function fragmentMergeSection(fm) {
  const b = fm.before.all, a = fm.after.all, d = fm.paired_f1_difference;
  return `<section class="card mt"><div class="card-head"><h3>${t("eval.fm")}</h3><p>${t("eval.fm_sub")}</p></div>
    <div class="tiles">
      <div class="tile"><b>${b.precision} → ${a.precision}</b><span>${esc(t("eval.fm.precision"))}</span></div>
      <div class="tile"><b>${b.recall} → ${a.recall}</b><span>${esc(t("eval.fm.recall"))}</span></div>
      <div class="tile"><b>${b.f1} → ${a.f1}</b><span>${esc(t("eval.fm.f1", { lo: a.f1_ci95[0], hi: a.f1_ci95[1] }))}</span></div>
      <div class="tile"><b>+${d.difference}</b><span>${esc(t("eval.fm.paired", { lo: d.ci95[0], hi: d.ci95[1] }))}</span></div>
    </div><p class="muted small">${esc(t("eval.fm_note"))}</p></section>`;
}

function secondLookSection(sl) {
  const a = sl.cross_validation_recordings, e = sl.edited_recordings;
  const violating = e.rows.filter((r) => r.truth !== "Compliant").length;
  const compliant = e.rows.length - violating;
  return `<section class="card mt"><div class="card-head"><h3>${t("eval.sl")}</h3><p>${t("eval.sl_sub", { n: a.weak_events })}</p></div>
    <div class="tiles">
      <div class="tile"><b>${esc(a.true_events_confirmed)}</b><span>${esc(t("eval.sl.true"))}</span></div>
      <div class="tile weak"><b>${esc(a.false_events_confirmed)}</b><span>${esc(t("eval.sl.false"))}</span></div>
      <div class="tile"><b>${a.recordings_cleared_before} → ${a.recordings_cleared_after}<small> / ${a.recordings}</small></b><span>${esc(t("eval.sl.cleared"))}</span></div>
      <div class="tile"><b>${e.violating_recordings_wrongly_cleared_after}/${violating}</b><span>${esc(t("eval.sl.unsafe"))}</span></div>
      <div class="tile"><b>${e.compliant_cleared_before} → ${e.compliant_cleared_after}<small> / ${compliant}</small></b><span>${esc(t("eval.sl.compliant"))}</span></div>
    </div><p class="muted small">${esc(t("eval.sl_note"))}</p></section>`;
}

async function renderEvaluation() {
  const d = await rapi("/api/evaluation");
  const shipped = d.backends.find((b) => b.shipped);
  const first = d.backends[0];
  const agentCard = (a) => `<div class="agent-card ${a.id === "rca" ? "purple" : "blue"}"><span class="agent-chip ${a.id === "rca" ? "purple" : "blue"}">${esc(t(`trace.${a.id}`))}</span>
    <p class="muted small">${esc(t(`eval.agent.${a.id}`))}</p><div class="tool-chips">${a.tools.map((n) => `<code class="${n === "run_root_cause_analysis" ? "hot" : ""}">${esc(n)}</code>`).join("")}</div></div>`;
  const b = d.baseline;
  const tiles = b ? `<div class="tiles">
      <div class="tile"><b>${b.violating.praxiproof_correct}/${b.violating.n}</b><span>${esc(t("eval.tile.pp_violations"))}</span></div>
      <div class="tile weak"><b>${b.violating.baseline_correct}/${b.violating.samples}</b><span>${esc(t("eval.tile.vlm_violations"))}</span></div>
      <div class="tile weak"><b>${b.violating.baseline_false_compliant}/${b.violating.samples}</b><span>${esc(t("eval.tile.vlm_missed"))}</span></div>
      <div class="tile"><b>${b.compliant.praxiproof_cleared}/${b.compliant.n}</b><span>${esc(t("eval.tile.pp_cleared"))}</span></div>
    </div>` : "";
  view.innerHTML = `<div class="page-head"><div><h1>${t("eval.title")}</h1><p>${t("eval.subtitle")}</p></div></div>
    <section class="card"><div class="card-head"><h3>${t("eval.agents")}</h3><p>${t("eval.agents_sub")}</p></div>
      <div class="agent-flow">${agentCard(d.agents[0])}<div class="flow-arrow"><code>run_root_cause_analysis</code><span>→</span><small>${esc(t("eval.delegates"))}</small></div>${agentCard(d.agents[1])}</div></section>
    ${d.cross_validation ? cvSection(d.cross_validation) : ""}
    <section class="card mt"><div class="card-head"><h3>${t("eval.tuning")}</h3><p>${t("eval.tuning_sub")}</p></div>
      ${shipped && first ? `<p class="callout">${esc(t("eval.tuning_delta", { from: first.f1, to: shipped.f1 }))}</p>` : ""}
      <table class="eval-table"><thead><tr><th>${t("eval.col_backend")}</th><th>F1</th><th></th><th>${t("eval.col_precision")}</th><th>${t("eval.col_recall")}</th><th>${t("eval.col_seq")}</th><th>${t("eval.col_time")}</th></tr></thead><tbody>
      ${d.backends.map((r) => `<tr class="${r.shipped ? "shipped" : ""}"><td>${esc(t(`eval.backend.${r.id}`))}${r.shipped ? ` <span class="badge tone-green">${esc(t("eval.deployed"))}</span>` : ""}</td><td><b>${r.f1.toFixed(3)}</b></td><td class="barcell">${bar(r.f1, 1, r.shipped ? "good" : "")}</td><td>${r.precision.toFixed(3)}</td><td>${r.recall.toFixed(3)}</td><td>${r.sequence_similarity.toFixed(3)}</td><td>${Math.round(r.seconds_per_video)}s</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.tuning_note"))}</p></section>
    <section class="card mt"><div class="card-head"><h3>${t("eval.vlm")}</h3><p>${t("eval.vlm_sub")}</p></div>
      <table class="eval-table"><tbody>${d.vlm_selection.map((r, i) => `<tr class="${i === 0 ? "shipped" : ""}"><td>${esc(r.model)} <span class="muted small">${esc(t(r.think_off ? "eval.mode_off" : "eval.mode_default"))}</span></td><td><b>${r.correct}/${r.cases}</b></td><td class="barcell">${bar(r.accuracy, 1, i === 0 ? "good" : "")}</td><td>${r.seconds}s / ${esc(t("eval.per_clip"))}</td></tr>`).join("")}</tbody></table></section>
    ${b ? `<section class="card mt"><div class="card-head"><h3>${t("eval.baseline")}</h3><p>${t("eval.baseline_sub")}</p></div>${tiles}
      <table class="eval-table"><thead><tr><th>${t("eval.col_video")}</th><th>${t("eval.col_truth")}</th><th>${t("eval.col_vlm")}</th><th>PraxiProof</th></tr></thead><tbody>
      ${b.videos.map((v) => `<tr><td>${esc(v.id)}</td><td>${esc(labelText(v.truth))}</td><td class="chips">${v.baseline.map((l) => baselineChip(l, v.truth)).join("")}</td><td>${v.praxiproof === v.truth ? `<span class="chip ok">${esc(labelText(v.praxiproof))}</span>` : `<span class="chip warn">${esc(labelText(v.praxiproof))}</span>`}</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.baseline_note"))}</p></section>` : ""}
    ${d.fragment_merge ? fragmentMergeSection(d.fragment_merge) : ""}
    ${d.second_look ? secondLookSection(d.second_look) : ""}
    ${d.stepfun ? `<section class="card mt"><div class="card-head"><h3>${t("eval.stepfun")}</h3><p>${t("eval.stepfun_sub")}</p></div>
      <table class="eval-table"><thead><tr><th>${t("eval.col_model")}</th><th>${t("eval.col_time")}</th><th>${t("eval.col_rules")}</th></tr></thead><tbody>
      ${d.stepfun.runs.map((r) => `<tr><td>${esc(r.model)}</td><td>${r.seconds}s</td><td>${r.error ? `<span class="chip bad">${esc(r.error)}</span>` : `${r.rules}${r.rejected ? ` <span class="muted small">(${esc(t("eval.rejected", { n: r.rejected }))})</span>` : ""}`}</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.stepfun_note"))}</p></section>` : ""}`;
}
