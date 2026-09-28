// Renders the Compliance/RCA agent tool-call trace, and the tiny markdown subset agent answers use.
const RCA_TONE = { VIDEO_GAP: "amber", LOW_CONFIDENCE: "amber", LABEL_MISMATCH: "blue", BOUNDARY_UNCERTAINTY: "blue", GENUINE_VIOLATION: "red", NOT_APPLICABLE: "green" };

function rcaCard(r) {
  if (r.status !== "ok") return `<div class="rca-card"><p class="error-text">${esc(r.error || t("rca.failed"))}</p></div>`;
  return `<div class="rca-card"><div class="rca-head"><span class="badge tone-${RCA_TONE[r.category] || "blue"}">${esc(t(`rca.cat.${r.category}`))}</span><span class="muted">${esc(t("rca.confidence", { level: r.confidence }))}</span></div>
    <p class="muted small">${esc(t(`rca.cat.${r.category}.hint`))}</p>
    <p>${esc(r.explanation)}</p>${r.recommendation ? `<p><b>${esc(t("rca.recommendation"))}</b> ${esc(r.recommendation)}</p>` : ""}</div>`;
}

function stepList(steps) {
  if (!steps.length) return `<p class="muted small">${esc(t("trace.no_tools"))}</p>`;
  return `<ol class="steps">${steps.map((s) => `<li><code>${esc(s.tool)}</code>${Object.keys(s.arguments || {}).length ? ` <span class="muted small">${esc(Object.entries(s.arguments).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ").slice(0, 80))}</span>` : ""}</li>`).join("")}</ol>`;
}

function traceView(trace) {
  const delegated = trace.some((s) => s.agent === "rca");
  return `<div class="trace"><div class="trace-title"><span class="agent-chip blue">${esc(t("trace.compliance"))}</span>${delegated ? `<span class="muted small">${esc(t("trace.delegated"))}</span>` : ""}</div>
    <ol class="steps">${trace.map((s) => s.agent === "rca"
      ? `<li class="delegate"><code>${esc(s.tool)}</code> <span class="muted small">${esc(s.arguments.rule_id || "")}</span>
          <div class="sub"><div class="trace-title"><span class="agent-chip purple">${esc(t("trace.rca"))}</span><span class="muted small">${esc(t("trace.rca_tools"))}</span></div>${stepList(s.sub_trace || [])}${rcaCard(s.result)}</div></li>`
      : `<li><code>${esc(s.tool)}</code></li>`).join("")}</ol></div>`;
}

async function askWhy(runId, ruleId, slot, button) {
  button.disabled = true;
  slot.innerHTML = `<div class="trace"><p>${ICON.spin} ${esc(t("rca.running"))}</p></div>`;
  try {
    const r = await api(`/api/runs/${encodeURIComponent(runId)}/verdicts/${encodeURIComponent(ruleId)}/analyze`, { method: "POST" });
    slot.innerHTML = `<div class="trace"><div class="trace-title"><span class="agent-chip purple">${esc(t("trace.rca"))}</span><span class="muted small">${esc(t("trace.rca_tools"))}</span></div>${stepList(r.trace || [])}${rcaCard(r)}</div>`;
  } catch (err) {
    slot.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
  }
  button.disabled = false;
}

// Minimal, XSS-safe markdown for agent answers: # headings, **bold**, *italic*, `code`, "* item" bullets, blank-line paragraphs.
function mdLite(text) {
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?![*\w])/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  let list = false;
  for (const line of String(text).split("\n")) {
    const item = line.match(/^\s*[*-]\s+(.*)$/);
    if (item) {
      if (!list) out.push("<ul>");
      list = true;
      out.push(`<li>${inline(item[1])}</li>`);
      continue;
    }
    if (list) out.push("</ul>");
    list = false;
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) out.push(`<h4>${inline(heading[1])}</h4>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}
