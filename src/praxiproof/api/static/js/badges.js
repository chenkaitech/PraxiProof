// Small colored labels for statuses, severities and categories, used across every table and card.
function statusBadge(status) {
  const map = { PASS: "pass", VIOLATION: "violation", UNVERIFIED: "warn", INSUFFICIENT_EVIDENCE: "warn", done: "pass", ready: "pass", failed: "violation", queued: "neutral", processing: "info" };
  return `<span class="badge ${map[status] || "neutral"}">${esc(t(`status.${status}`))}</span>`;
}

const reviewBadge = (skill) =>
  skill.review_status === "approved" ? `<span class="badge pass">${esc(t("skill.review.approved"))}</span>` : `<span class="badge warn">${esc(t("skill.review.pending"))}</span>`;
const severityBadge = (severity) => `<span class="badge ${esc(severity)}">${esc(t(`severity.${severity}`))}</span>`;
const categoryBadge = (category) => `<span class="badge neutral">${esc(t(`category.${category}`))}</span>`;
const stageLabel = (stage) => (STRINGS.en[`stage.${stage}`] ? t(`stage.${stage}`) : t("status.queued"));

function resultBadge(run) {
  if (busy(run.status)) return `<span class="badge info">${esc(run.stage ? stageLabel(run.stage) : t(`status.${run.status}`))}…</span>`;
  if (run.status === "failed") return `<span class="badge violation">${esc(t("result.failed"))}</span>`;
  const r = run.result;
  if (!r) return "-";
  if (r === "PASS") return `<span class="badge pass">✓ ${esc(t("result.PASS"))}</span>`;
  if (r === "Needs Evidence") return `<span class="badge warn">? ${esc(t("result.Needs Evidence"))}</span>`;
  const cls = r === "Missing Step" ? "warn" : "violation";
  return `<span class="badge ${cls}">⚠ ${esc(t(`result.${r}`))}</span>`;
}
