const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const state = { query: "", pollTimer: null, renderToken: 0 };

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const ICON = {
  pdf: '<svg viewBox="0 0 24 24" style="width:44px;height:44px;color:#94a3b8"><path d="M6 2h9l5 5v15H6z"/><path d="M15 2v5h5"/><rect x="3" y="12" width="12" height="7" rx="1.5" fill="#e5484d" stroke="#e5484d"/><text x="4.4" y="17.6" font-size="5" fill="#fff" stroke="none" font-family="Arial" font-weight="700">PDF</text></svg>',
  play: '<svg viewBox="0 0 24 24" style="width:44px;height:44px;color:#475569"><rect x="2" y="4" width="20" height="16" rx="3" fill="#64748b" stroke="#64748b"/><path d="M10 9l5 3-5 3z" fill="#fff" stroke="#fff"/></svg>',
  doc: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M9 12h6M9 16h6M9 8h3"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  cam: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="14" height="12" rx="2"/><path d="m16 10 6-3v10l-6-3"/></svg>',
  screen: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>',
  check: '<svg viewBox="0 0 24 24" style="color:#12a150;width:26px;height:26px"><circle cx="12" cy="12" r="10" fill="#12a150" stroke="#12a150"/><path d="m7.5 12.5 3 3 6-6" stroke="#fff"/></svg>',
  spin: '<svg viewBox="0 0 24 24" style="width:24px;height:24px;color:#1a6cf0"><path d="M12 3a9 9 0 1 0 9 9"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></path></svg>',
  fail: '<svg viewBox="0 0 24 24" style="color:#e5484d;width:26px;height:26px"><circle cx="12" cy="12" r="10"/><path d="M12 7v6M12 17h.01"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" class="arrow"><path d="M4 12h15M13 6l6 6-6 6"/></svg>',
  cal: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
  stageManual: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M9 12h6M9 16h6"/></svg>',
  stageIR: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M9 11h2M9 15h2M13 11h2M13 15h2"/></svg>',
  stageAlign: '<svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="19" r="2.5"/><circle cx="19" cy="19" r="2.5"/><path d="M12 7.5v4M12 11.5 6.5 17M12 11.5l5.5 5.5"/></svg>',
  stageVerify: '<svg viewBox="0 0 24 24"><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg>',
  stageSkill: '<svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/></svg>',
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("json") ? response.json() : response.text();
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3500);
}

const fmtTime = (s) => {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
};
const fmtDuration = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const locale = () => (LANG === "zh" ? "zh-CN" : "en-US");
const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString(locale(), { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "—";
const fmtBytes = (n) => (n == null ? "" : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`);
const busy = (status) => status === "queued" || status === "processing";
const matches = (row) => !state.query || JSON.stringify(row).toLowerCase().includes(state.query);

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
  if (!r) return "—";
  if (r === "PASS") return `<span class="badge pass">✓ ${esc(t("result.PASS"))}</span>`;
  if (r === "Needs Evidence") return `<span class="badge warn">? ${esc(t("result.Needs Evidence"))}</span>`;
  const cls = r === "Missing Step" ? "warn" : "violation";
  return `<span class="badge ${cls}">⚠ ${esc(t(`result.${r}`))}</span>`;
}

function ring(value, color) {
  const r = 32, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(1, value ?? 0));
  return `<div class="ring ring-wrap"><svg viewBox="0 0 76 76"><circle class="track" cx="38" cy="38" r="${r}"/><circle cx="38" cy="38" r="${r}" stroke="${color}" stroke-dasharray="${c * pct} ${c}" stroke-linecap="round"/></svg>`;
}

function schedulePoll(needed) {
  clearTimeout(state.pollTimer);
  if (needed) {
    const token = state.renderToken;
    state.pollTimer = setTimeout(() => token === state.renderToken && render(true), 3000);
  }
}

function dropzone(kind, accept, title) {
  return `<label class="dropzone" data-kind="${kind}">
    ${kind === "manual" ? ICON.pdf : ICON.play}
    <div><strong>${esc(title)}</strong><span>${esc(t("common.or_browse"))}</span></div>
    <input type="file" accept="${accept}">
  </label>`;
}

function bindDropzones(root) {
  root.querySelectorAll(".dropzone").forEach((zone) => {
    const input = zone.querySelector("input");
    const send = (file) => file && upload(zone.dataset.kind, file);
    input.addEventListener("change", () => send(input.files[0]));
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
    zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("drag"); send(e.dataTransfer.files[0]); });
  });
}

async function upload(kind, file) {
  const body = new FormData();
  body.append("file", file);
  try {
    if (kind === "manual") {
      const procedure = $("#procedure")?.value.trim();
      if (procedure) body.append("procedure", procedure);
      const record = await api("/api/manuals", { method: "POST", body });
      toast(t("upload.manual_ok", { name: record.filename }));
    } else {
      toast(t("upload.video_progress", { name: file.name }));
      const record = await api("/api/videos", { method: "POST", body });
      toast(t("upload.video_ok", { name: record.filename }));
    }
    render(true);
  } catch (err) {
    toast(t("upload.failed", { error: err.message }));
  }
}

function manualRow(m) {
  if (!m) return `<p class="empty">${esc(t("dash.no_manual"))}</p>`;
  const icon = m.status === "ready" ? ICON.check : m.status === "failed" ? ICON.fail : ICON.spin;
  const sub = m.status === "failed" ? `<span class="error-text">${esc(m.error)}</span>` : `${esc(m.procedure || m.procedure_hint || t("dash.compiling"))} | ${m.page_count ? `${esc(t("common.pages", { n: m.page_count }))} | ` : ""}${fmtDate(m.created_at)}`;
  return `<a class="file-row" href="#manual/${esc(m.id)}" style="color:inherit">
    <span class="doc-icon">${ICON.doc}</span>
    <div class="grow"><div class="name">${esc(m.filename)}</div><div class="meta">${sub}</div></div>${icon}</a>`;
}

function videoRow(v) {
  if (!v) return `<p class="empty">${esc(t("dash.no_video"))}</p>`;
  return `<a class="file-row" href="#videos" style="color:inherit">
    <img class="thumb" src="/api/videos/${esc(v.id)}/frame?t=${Math.min(2, v.meta.duration / 2).toFixed(1)}" alt="">
    <div class="grow"><div class="name">${esc(v.filename)}</div>${v.note ? `<div class="meta"><span class="badge warn">${esc(t("video.note"))}</span> ${esc(v.note)}</div>` : ""}<div class="meta">${v.meta.width} × ${v.meta.height} | ${fmtBytes(v.size_bytes)} | ${fmtDate(v.created_at)}</div></div>${ICON.check}</a>`;
}

function runsTable(runs, compact = false) {
  const rows = runs.filter(matches);
  if (!rows.length) return `<p class="empty">${esc(t("runs.none"))}</p>`;
  return `<table><thead><tr><th>#</th><th>${t("runs.col_video")}</th>${compact ? "" : `<th>${t("runs.col_procedure")}</th>`}<th>${t("runs.col_manual")}</th><th>${t("runs.col_date")}</th><th>${t("runs.col_result")}</th><th>${t("runs.col_violations")}</th></tr></thead><tbody>
    ${rows.map((r) => `<tr class="clickable" data-href="#run/${esc(r.id)}"><td>${esc(r.id)}</td><td>${esc(r.video_name)}</td>${compact ? "" : `<td>${esc(r.procedure)}</td>`}<td>${esc(r.manual_name)}</td><td>${fmtDate(r.created_at)}</td><td>${resultBadge(r)}</td><td>${r.violations ?? "—"}</td></tr>`).join("")}
  </tbody></table>`;
}

function bindRowLinks(root) {
  root.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
}

function findingCard(f, compact = false) {
  const violation = f.status === "VIOLATION";
  const manual = f.manual[0];
  const video = f.video[0];
  const frame = video && f.video_id ? `<img src="/api/videos/${esc(f.video_id)}/frame?t=${video.start.toFixed(1)}" alt="" data-seek="${video.start}">` : "";
  return `<div class="finding ${violation ? "" : "unverified"}">
    <div class="finding-top"><div class="alert">${ICON.alert}</div>
      <div style="flex:1"><h4>${esc(t(`result.${f.kind}`))}: ${esc(f.statement)}</h4><p>${esc(verdictText(f.reason_code, f.reason_params, f.reason))}</p>
      ${f.needed_evidence && !violation ? `<p class="muted">${esc(t("finding.needed", { text: verdictText(f.needed_code, f.reason_params, f.needed_evidence) }))}</p>` : ""}</div>
      ${severityBadge(f.severity)}
    </div>
    <div class="evidence-pair">
      <div class="evidence-box"><div class="label">${esc(t("finding.reference"))}</div><b>${esc(t("finding.manual", { cite: manual?.citation || "—" }))}</b>${manual ? `<q>${esc(manual.text.slice(0, compact ? 110 : 400))}</q>` : ""}</div>
      <div class="evidence-box"><div class="label">${esc(t("finding.video"))}</div><b>${video ? `${fmtTime(video.start)} – ${fmtTime(video.end)}` : esc(t("finding.not_observed"))}</b>${frame}${video ? `<span class="muted">${esc(f.video_name)}</span>` : ""}</div>
    </div>
  </div>`;
}

const STALE = Symbol("stale render");
// A page renderer awaits several GETs; if the user has navigated on by the time one returns, drop the whole render
// instead of letting it overwrite the newer page (Settings waits ~1s on /api/models and used to clobber the next view).
function rapi(path) {
  const token = state.renderToken;
  return api(path).then((result) => {
    if (token !== state.renderToken) throw STALE;
    return result;
  });
}

async function renderDashboard() {
  const [d, skills] = await Promise.all([rapi("/api/dashboard"), rapi("/api/skills")]);
  const m = d.latest_manual, v = d.latest_video, metrics = d.metrics;
  const now = new Date();
  const activeRun = d.recent_runs.find((r) => busy(r.status));
  const doneRun = d.latest_run;
  const stageState = (i) => {
    if (m && busy(m.status)) return i === 0 ? "done" : i === 1 ? "active" : "";
    if (activeRun) return i < 2 ? "done" : (i === 2 && activeRun.stage !== "verifying") || (i === 3 && activeRun.stage === "verifying") ? "active" : "";
    if (doneRun) return i < 4 || skills.some((s) => s.run_id === doneRun.id) ? "done" : "";
    return m?.status === "ready" && i < 2 ? "done" : "";
  };
  const stageIcons = [ICON.stageManual, ICON.stageIR, ICON.stageAlign, ICON.stageVerify, ICON.stageSkill];
  const metricCard = (title, metric, color, subtitle) => `<div class="card metric">${ring(metric?.value, color)}<div class="ring-label">${metric ? Math.round(metric.value * 100) + "%" : "—"}</div></div>
    <div><h4>${esc(title)}</h4><p>${esc(subtitle)}</p></div></div>`;
  const violations = metrics?.violations ?? 0;

  view.innerHTML = `
    <div class="page-head">
      <div><h1>${t("dash.title")}</h1><p>${t("dash.subtitle")}</p></div>
      <div class="spacer"></div>
      <div class="date">${ICON.cal}<div>${now.toLocaleDateString(locale(), { month: "long", day: "numeric", year: "numeric" })}<small>${now.toLocaleDateString(locale(), { weekday: "long" })}, ${now.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })}</small></div></div>
      <button class="btn ghost big" id="pipeline">${t("pipe.button")}</button>
      <button class="btn primary big" id="start">${t("common.start")}</button>
    </div>

    <div class="grid-2">
      <section class="card upload-card manual">
        <div class="card-head"><div class="icon-chip blue">${ICON.doc}</div><div><h3>${t("dash.manual_title")}</h3><p>${t("dash.manual_sub")}</p></div></div>
        ${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", t("dash.manual_drop"))}
        <label class="procedure-input">${t("dash.procedure")} <input id="procedure" placeholder="${esc(t("dash.procedure_ph"))}"></label>
        ${manualRow(m)}
        <div class="stats"><div>${ICON.list}<div><b>${m?.counts?.safety_rules ?? "—"}</b><small>${t("dash.safety_rules")}</small></div></div><div>${ICON.doc}<div><b>${m?.counts?.rules ?? "—"}</b><small>${esc(t("dash.rules_steps", { steps: m?.counts?.steps ?? "—" }))}</small></div></div></div>
      </section>
      <section class="card upload-card video">
        <div class="card-head"><div class="icon-chip green"><svg viewBox="0 0 24 24"><path d="M9 7l8 5-8 5z" fill="#fff"/></svg></div><div><h3>${t("dash.video_title")}</h3><p>${t("dash.video_sub")}</p></div></div>
        ${dropzone("video", "video/*", t("dash.video_drop"))}
        ${videoRow(v)}
        <div class="stats"><div>${ICON.clock}<div><b>${v ? fmtDuration(v.meta.duration) : "—"}</b><small>${t("dash.duration")}</small></div></div><div>${ICON.cam}<div><b>${v ? esc(v.meta.format_name.toUpperCase()) : "—"}</b><small>${t("dash.format")}</small></div></div><div>${ICON.screen}<div><b>${v ? `${v.meta.height}p` : "—"}</b><small>${t("dash.resolution")}</small></div></div></div>
      </section>
    </div>

    <section class="card pipeline">
      ${stageIcons.map((icon, i) => `<div class="stage ${stageState(i)}"><div class="bubble">${icon}</div><div><b>${t(`stage.${i}`)}</b><small>${t(`stage.${i}.sub`)}</small></div></div>${i < 4 ? ICON.arrow : ""}`).join("")}
    </section>

    <div class="grid-4">
      ${metricCard(t("metric.trace"), metrics?.evidence_traceability, "#1a6cf0", metrics ? t("metric.trace_sub", { n: metrics.evidence_traceability.numerator, d: metrics.evidence_traceability.denominator }) : t("metric.empty"))}
      ${metricCard(t("metric.safety"), metrics?.safety_coverage, "#12a150", metrics ? t("metric.safety_sub", { n: metrics.safety_coverage.numerator, d: metrics.safety_coverage.denominator }) : "")}
      ${metricCard(t("metric.steps"), metrics?.step_coverage, "#1a6cf0", metrics ? t("metric.steps_sub", { n: metrics.step_coverage.numerator, d: metrics.step_coverage.denominator }) : "")}
      <div class="card metric">${ring(metrics ? Math.min(violations / Math.max(metrics.counts ? Object.values(metrics.counts).reduce((a, b) => a + b, 0) : 1, 1), 1) : 0, "#e5484d")}<div class="ring-label" style="color:#e5484d">${metrics ? violations : "—"}</div></div>
        <div><h4>${t("metric.violations")}</h4><p>${metrics ? esc(violations === 1 ? t("metric.violations_one") : t("metric.violations_many", { n: violations })) : ""}</p></div></div>
    </div>

    <div class="split" style="margin-top:20px">
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

async function openRunDialog(preset = {}) {
  const dialog = $("#run-dialog");
  const form = $("#run-form");
  const [manuals, videos, demos] = await Promise.all([api("/api/manuals"), api("/api/videos"), api("/api/demo/observations")]);
  const ready = manuals.filter((m) => m.status === "ready");
  if (!ready.length) return toast(t("dialog.need_manual"));
  form.manual_id.innerHTML = ready.map((m) => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.procedure)} (${esc(m.filename)})</option>`).join("");
  form.video_id.innerHTML = videos.map((v) => `<option value="${esc(v.id)}">${esc(v.filename)} (${fmtDuration(v.meta.duration)})</option>`).join("") || `<option value="">${esc(t("dialog.no_videos"))}</option>`;
  form.demo_observation.innerHTML = demos.map((o) => `<option value="${esc(o.name)}">${esc(LANG === "zh" && o.title_zh ? o.title_zh : o.title)}</option>`).join("");
  form.source.value = preset.video_id || videos.length ? "video" : "demo";
  if (preset.video_id) form.video_id.value = preset.video_id;
  $("#run-error").textContent = "";
  dialog.showModal();
  form.onsubmit = async (event) => {
    if (event.submitter?.value !== "ok") return;
    event.preventDefault();
    const body = { manual_id: form.manual_id.value };
    if (form.source.value === "video") {
      if (!form.video_id.value) return ($("#run-error").textContent = t("dialog.need_video"));
      body.video_id = form.video_id.value;
    } else body.demo_observation = form.demo_observation.value;
    try {
      const run = await api("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      dialog.close();
      location.hash = `#run/${run.id}`;
    } catch (err) {
      $("#run-error").textContent = err.message;
    }
  };
}

async function openPipelineDialog() {
  const dialog = $("#pipeline-dialog");
  const form = $("#pipeline-form");
  const [manuals, videos, demos] = await Promise.all([api("/api/manuals"), api("/api/videos"), api("/api/demo/observations")]);
  const usable = manuals.filter((m) => m.status !== "failed");
  form.manual_id.innerHTML = usable.map((m) => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.procedure || m.procedure_hint || m.filename)} (${esc(m.filename)})</option>`).join("");
  form.video_id.innerHTML = videos.map((v) => `<option value="${esc(v.id)}">${esc(v.filename)} (${fmtDuration(v.meta.duration)})</option>`).join("") || `<option value="">${esc(t("dialog.no_videos"))}</option>`;
  form.demo_observation.innerHTML = demos.map((o) => `<option value="${esc(o.name)}">${esc(LANG === "zh" && o.title_zh ? o.title_zh : o.title)}</option>`).join("");
  form.manual_source.value = usable.length ? "existing" : "upload";
  form.video_source.value = "upload";
  form.manual.value = "";
  form.video.value = "";
  form.video_note.value = "";
  $("#pipeline-error").textContent = "";
  dialog.showModal();
  form.onsubmit = async (event) => {
    if (event.submitter?.value !== "ok") return;
    event.preventDefault();
    const error = (key) => ($("#pipeline-error").textContent = t(key));
    const body = new FormData();
    if (form.manual_source.value === "upload") {
      if (!form.manual.files[0]) return error("pipe.need_manual_file");
      body.append("manual", form.manual.files[0]);
      if (form.procedure.value.trim()) body.append("procedure", form.procedure.value.trim());
    } else {
      if (!form.manual_id.value) return error("pipe.need_manual");
      body.append("manual_id", form.manual_id.value);
    }
    if (form.video_source.value === "upload") {
      if (!form.video.files[0]) return error("pipe.need_video_file");
      body.append("video", form.video.files[0]);
      if (form.video_note.value.trim()) body.append("video_note", form.video_note.value.trim());
    } else if (form.video_source.value === "existing") {
      if (!form.video_id.value) return error("pipe.need_video");
      body.append("video_id", form.video_id.value);
    } else {
      body.append("demo_observation", form.demo_observation.value);
    }
    const submit = form.querySelector('button[value="ok"]');
    submit.disabled = true;
    $("#pipeline-error").textContent = t("pipe.uploading");
    try {
      const pipeline = await api("/api/pipelines", { method: "POST", body });
      dialog.close();
      location.hash = `#pipeline/${pipeline.id}`;
    } catch (err) {
      $("#pipeline-error").textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  };
}

async function renderPipeline(id) {
  const p = await rapi(`/api/pipelines/${encodeURIComponent(id)}`);
  const failed = p.status === "failed";
  const order = ["compiling", "verifying", "packaging"];
  const current = p.status === "done" ? 3 : order.indexOf(p.stage);
  const state = (i) => (p.status === "done" || i < current ? "done" : i === current ? (failed ? "failed" : "active") : "");
  const detail = [
    p.manual.status === "ready"
      ? `${esc(p.manual.procedure || "")} · ${p.manual.counts?.rules ?? "—"} ${esc(t("dash.rules_steps", { steps: p.manual.counts?.steps ?? "—" }))}`
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

async function renderRuns() {
  const runs = await rapi("/api/runs");
  view.innerHTML = `<div class="page-head"><div><h1>${t("runs.title")}</h1><p>${t("runs.subtitle")}</p></div><div class="spacer"></div><button class="btn primary" id="start">${t("common.start")}</button></div>
    <section class="card">${runsTable(runs)}</section>`;
  $("#start").addEventListener("click", () => openRunDialog());
  bindRowLinks(view);
  schedulePoll(runs.some((r) => busy(r.status)));
}

function evidenceLine(ids, evidence, videoId) {
  return ids
    .map((id) => evidence[id])
    .filter(Boolean)
    .map((e) =>
      e.source_type === "document"
        ? `<div class="evidence-box"><div class="label">${esc(t("ev.manual", { cite: e.citation }))}${e.locator.section && e.locator.section !== e.citation ? ` · ${esc(e.locator.section)}` : ""}</div><q>${esc(e.text)}</q></div>`
        : `<div class="evidence-box"><div class="label">${esc(t("ev.video", { cite: e.citation, pct: Math.round(e.confidence * 100) }))}</div>${esc(e.text)}${videoId ? `<img src="/api/videos/${esc(videoId)}/frame?t=${e.locator.start.toFixed(1)}" alt="" data-seek="${e.locator.start}">` : ""}</div>`
    )
    .join("");
}

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

async function renderRun(id) {
  const [run, skills] = await Promise.all([rapi(`/api/runs/${encodeURIComponent(id)}`), rapi("/api/skills")]);
  const head = `<div class="page-head"><div><h1>${esc(run.id)} · ${esc(run.video_name)}</h1><p>${esc(run.procedure)} — ${esc(run.manual_name)}</p>${run.video_note ? `<p><span class="badge warn">${esc(t("video.note"))}</span> ${esc(run.video_note)}</p>` : ""}</div><div class="spacer"></div><a class="btn ghost" href="#runs">${t("run.all")}</a></div>`;
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
    <div class="split" style="margin-top:20px">
      <div class="stack">
        <section class="card"><div class="card-head"><h3>${t("run.verdicts")}</h3><p>${t("run.verdicts_sub")}</p></div>
          <div class="verdicts">${verdicts.map((v) => `
            <div class="verdict ${v.status}">
              <div class="verdict-head"><span class="title">${esc(v.rule_id)} · ${esc(v.statement)}</span>${statusBadge(v.status)}${severityBadge(v.severity)}${categoryBadge(v.category)}</div>
              <p class="reason"><code>${esc(signature(v.constraint))}</code> ${esc(verdictText(v.reason_code, v.reason_params, v.reason))}</p>
              ${v.needed_evidence ? `<p class="needed">${esc(t("run.needed", { text: verdictText(v.needed_code, v.reason_params, v.needed_evidence) }))}</p>` : ""}
              <div class="evidence-pair">${evidenceLine(v.requirement_evidence_ids, run.evidence, run.video_id)}${evidenceLine(v.observation_evidence_ids, run.evidence, run.video_id)}</div>
              ${v.status !== "PASS" ? `<div class="verdict-actions"><span class="muted">${t("run.review")}</span>
                <button class="btn small ${v.review === "accepted" ? "success" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="accepted">${t("run.confirm")}</button>
                <button class="btn small ${v.review === "rejected" ? "danger" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="rejected">${t("run.reject")}</button>
                <span class="spacer" style="flex:1"></span><button class="btn small why" data-why="${esc(v.rule_id)}">✦ ${t("rca.why")}</button></div>
                <div class="why-slot" data-why-slot="${esc(v.rule_id)}"></div>` : ""}
            </div>`).join("")}</div>
        </section>
        <section class="card"><div class="card-head"><h3>${t("run.alignment")}</h3><p>${t("run.alignment_sub")}</p></div>
          <table><thead><tr><th>${t("run.col_event")}</th><th>${t("run.col_observed")}</th><th>${t("run.col_matched")}</th><th>${t("run.col_method")}</th><th>${t("run.col_time")}</th></tr></thead><tbody>
          ${report.alignment.map((a) => { const e = run.observation.events.find((x) => x.event_id === a.event_id) || {}; return `<tr><td>${esc(a.event_id)}</td><td>${esc(a.observed_label)}</td><td>${esc(a.aligned_labels.join(", ") || "—")}</td><td>${esc(t(`method.${a.method}`))}</td><td>${fmtTime(e.start)}–${fmtTime(e.end)}</td></tr>`; }).join("")}
          </tbody></table>
          ${run.traceability_issues?.length ? `<p class="error-text">${esc(t("run.trace_issues", { issues: run.traceability_issues.join("; ") }))}</p>` : ""}
        </section>
      </div>
      <div class="stack">
        ${run.video_id ? `<section class="card"><div class="card-head"><h3>${t("run.video")}</h3></div><video id="player" controls preload="metadata" src="/api/videos/${esc(run.video_id)}/file"></video></section>` : ""}
        <section class="card"><div class="card-head"><h3>${t("run.agent")}</h3></div>
          <div class="chat"><textarea id="question" placeholder="${esc(t("run.agent_ph"))}"></textarea>
          <button class="btn primary" id="ask">${t("run.ask")}</button><div id="answer"></div></div>
        </section>
      </div>
    </div>`;

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

function bindSeek(root) {
  root.querySelectorAll("img[data-seek]").forEach((img) =>
    img.addEventListener("click", () => {
      const player = $("#player");
      if (!player) return;
      player.currentTime = Number(img.dataset.seek);
      player.scrollIntoView({ behavior: "smooth", block: "center" });
      player.play();
    })
  );
}

function signature(c) {
  if (c.type === "MUST_HAVE" || c.type === "MUST_NOT") return `${c.type}(${c.event})`;
  if (c.type === "COUNT") return `COUNT(${c.event} ≥ ${c.min_count})`;
  if (c.type === "MAX_INTERVAL") return `MAX_INTERVAL(${c.a} → ${c.b} ≤ ${c.seconds}s)`;
  return `${c.type}(${c.a}, ${c.b})`;
}

async function renderManuals() {
  const manuals = (await rapi("/api/manuals")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("manuals.title")}</h1><p>${t("manuals.subtitle")}</p></div></div>
    <div class="grid-2" style="margin-bottom:20px"><section class="card upload-card manual">${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", t("dash.manual_drop"))}
      <label class="procedure-input">${t("dash.procedure")} <input id="procedure" placeholder="${esc(t("manuals.procedure_ph"))}"></label></section></div>
    <section class="card">${manuals.length ? `<table><thead><tr><th>ID</th><th>${t("manuals.col_file")}</th><th>${t("manuals.col_procedure")}</th><th>${t("manuals.col_status")}</th><th>${t("manuals.col_rules")}</th><th>${t("manuals.col_safety")}</th><th>${t("manuals.col_steps")}</th><th>${t("manuals.col_uploaded")}</th></tr></thead><tbody>
      ${manuals.map((m) => `<tr class="clickable" data-href="#manual/${esc(m.id)}"><td>${esc(m.id)}</td><td>${esc(m.filename)}</td><td>${esc(m.procedure || m.procedure_hint || "")}</td><td>${statusBadge(m.status)}</td><td>${m.counts?.rules ?? "—"}</td><td>${m.counts?.safety_rules ?? "—"}</td><td>${m.counts?.steps ?? "—"}</td><td>${fmtDate(m.created_at)}</td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">${t("manuals.none")}</p>`}</section>`;
  bindDropzones(view);
  bindRowLinks(view);
  schedulePoll(manuals.some((m) => busy(m.status)));
}

async function renderManual(id) {
  const m = await rapi(`/api/manuals/${encodeURIComponent(id)}`);
  const rs = m.requirement_set;
  view.innerHTML = `<div class="page-head"><div><h1>${esc(m.procedure || m.filename)}</h1><p>${esc(m.id)} · ${esc(m.filename)} · ${esc(m.extractor || "")}${m.page_count ? ` · ${esc(t("common.pages", { n: m.page_count }))}` : ""}</p></div><div class="spacer"></div>
      ${statusBadge(m.status)}<button class="btn ghost" id="recompile">${t("manual.recompile")}</button><a class="btn ghost" href="#manuals">${t("manual.back")}</a></div>
    ${m.status === "failed" ? `<section class="card"><p class="error-text">${esc(m.error)}</p></section>` : ""}
    ${busy(m.status) ? `<section class="card"><p>${ICON.spin} ${esc(m.procedure_hint ? t("manual.working_focus", { hint: m.procedure_hint }) : t("manual.working"))}</p></section>` : ""}
    ${rs ? `<section class="card"><div class="card-head"><h3>${t("manual.rules")}</h3><p>${t("manual.rules_sub")}</p></div>
      <table><thead><tr><th>${t("manual.col_rule")}</th><th>${t("manual.col_constraint")}</th><th>${t("manual.col_category")}</th><th>${t("manual.col_severity")}</th><th>${t("manual.col_camera")}</th><th>${t("manual.col_source")}</th></tr></thead><tbody>
      ${rs.requirements.map((r) => `<tr><td><b>${esc(r.rule_id)}</b><br>${esc(r.statement)}</td><td><code>${esc(signature(r.constraint))}</code></td><td>${esc(t(`category.${r.category}`))}</td><td>${severityBadge(r.severity)}</td><td>${r.observable ? t("common.yes") : t("common.no")}</td>
        <td>${r.evidence_ids.map((e) => m.evidence[e]).filter(Boolean).map((e) => `<b>${esc(e.citation)}</b> <q class="muted">${esc(e.text.slice(0, 160))}</q>`).join("<br>")}</td></tr>`).join("")}
      </tbody></table></section>
      <section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("manual.vocab")}</h3><p>${t("manual.vocab_sub")}</p></div>
        <table><tbody>${rs.events.map((e) => `<tr><td><code>${esc(e.label)}</code></td><td>${esc(e.description)}</td></tr>`).join("")}</tbody></table></section>
      ${m.rejected?.length ? `<section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("manual.rejected")}</h3><p>${t("manual.rejected_sub")}</p></div>
        <table><tbody>${m.rejected.map((r) => `<tr><td class="error-text">${esc(r.error)}</td><td><code>${esc(JSON.stringify(r.item).slice(0, 240))}</code></td></tr>`).join("")}</tbody></table></section>` : ""}` : ""}`;
  $("#recompile").addEventListener("click", async () => { await api(`/api/manuals/${encodeURIComponent(id)}/recompile`, { method: "POST" }); render(true); });
  schedulePoll(busy(m.status));
}

async function renderVideos() {
  const videos = (await rapi("/api/videos")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("videos.title")}</h1><p>${t("videos.subtitle")}</p></div></div>
    <div class="grid-2" style="margin-bottom:20px"><section class="card upload-card video">${dropzone("video", "video/*", t("dash.video_drop"))}</section></div>
    <div class="grid-4">${videos.map((v) => `<section class="card"><img class="thumb" style="width:100%;height:150px" src="/api/videos/${esc(v.id)}/frame?t=${Math.min(2, v.meta.duration / 2).toFixed(1)}" alt="">
      <p style="margin:10px 0 2px"><b>${esc(v.filename)}</b></p>${v.note ? `<p style="margin:0 0 4px"><span class="badge warn">${esc(t("video.note"))}</span> ${esc(v.note)}</p>` : ""}<p class="muted" style="margin:0">${esc(v.id)} · ${fmtDuration(v.meta.duration)} · ${v.meta.width}×${v.meta.height} · ${fmtBytes(v.size_bytes)}</p>
      <button class="btn primary small" style="margin-top:10px" data-verify="${esc(v.id)}">${t("videos.verify")}</button></section>`).join("") || `<p class="empty">${t("videos.none")}</p>`}</div>`;
  bindDropzones(view);
  view.querySelectorAll("[data-verify]").forEach((b) => b.addEventListener("click", () => openRunDialog({ video_id: b.dataset.verify })));
}

async function renderSkills() {
  const skills = (await rapi("/api/skills")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("skills.title")}</h1><p>${t("skills.subtitle")}</p></div></div>
    <section class="card">${skills.length ? `<table><thead><tr><th>ID</th><th>${t("skills.col_skill")}</th><th>${t("skills.col_procedure")}</th><th>${t("skills.col_verified")}</th><th>${t("skills.col_results")}</th><th>${t("skills.col_review")}</th><th>${t("skills.col_created")}</th><th></th></tr></thead><tbody>
    ${skills.map((s) => `<tr class="clickable" data-href="#skill/${esc(s.id)}"><td>${esc(s.id)}</td><td><code>${esc(s.name)}</code></td><td>${esc(s.procedure)}</td><td>${esc(s.run_id)}</td><td>${Object.entries(s.verification_summary || {}).filter(([, n]) => n).map(([k, n]) => `${statusBadge(k)} ${n}`).join(" ")}</td><td>${reviewBadge(s)}</td><td>${fmtDate(s.created_at)}</td><td><a href="/api/skills/${esc(s.id)}/download">${t("common.download")}</a></td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">${t("skills.none")}</p>`}</section>`;
  bindRowLinks(view);
}

async function renderSkill(id) {
  const [skills, md] = await Promise.all([rapi("/api/skills"), rapi(`/api/skills/${encodeURIComponent(id)}/skill.md`)]);
  const s = skills.find((x) => x.id === id);
  view.innerHTML = `<div class="page-head"><div><h1><code style="font-size:26px">${esc(s?.name)}</code></h1><p>${esc(s?.procedure)} · ${t("skill.verified_by")} <a href="#run/${esc(s?.run_id)}">${esc(s?.run_id)}</a> · ${s ? reviewBadge(s) : ""}</p></div><div class="spacer"></div>
    ${s && s.review_status !== "approved" ? `<button class="btn ghost" id="approve">${t("skill.approve")}</button>` : ""}
    <a class="btn primary" href="/api/skills/${esc(id)}/download">${t("skill.download")}</a><a class="btn ghost" href="#skills">${t("skill.back")}</a></div>
    <section class="card"><div class="card-head"><h3>SKILL.md</h3><p>${t("skill.package")}</p></div><div class="skill-md">${esc(md)}</div></section>`;
  $("#approve")?.addEventListener("click", async () => {
    await api(`/api/skills/${encodeURIComponent(id)}/approve`, { method: "POST" });
    render(true);
  });
}

async function renderReports() {
  const runs = (await rapi("/api/runs")).filter((r) => r.status === "done" && matches(r));
  const details = await Promise.all(runs.slice(0, 20).map((r) => rapi(`/api/runs/${encodeURIComponent(r.id)}`)));
  const pct = (m) => (m ? `${Math.round(m.value * 100)}% <span class="muted">(${m.numerator}/${m.denominator})</span>` : "—");
  view.innerHTML = `<div class="page-head"><div><h1>${t("reports.title")}</h1><p>${t("reports.subtitle")}</p></div></div>
    <section class="card">${details.length ? `<table><thead><tr><th>${t("reports.col_run")}</th><th>${t("runs.col_video")}</th><th>${t("runs.col_result")}</th><th>${t("reports.col_trace")}</th><th>${t("reports.col_safety")}</th><th>${t("reports.col_steps")}</th><th>${t("reports.col_alignment")}</th><th>${t("reports.col_pass")}</th><th>${t("reports.col_violation")}</th><th>${t("reports.col_unverified")}</th><th>${t("reports.col_insufficient")}</th></tr></thead><tbody>
    ${details.map((r) => `<tr class="clickable" data-href="#run/${esc(r.id)}"><td>${esc(r.id)}</td><td>${esc(r.video_name)}</td><td>${resultBadge(r)}</td><td>${pct(r.metrics.evidence_traceability)}</td><td>${pct(r.metrics.safety_coverage)}</td><td>${pct(r.metrics.step_coverage)}</td><td>${pct(r.metrics.observation_alignment)}</td>
      <td>${r.counts.PASS}</td><td>${r.counts.VIOLATION}</td><td>${r.counts.UNVERIFIED}</td><td>${r.counts.INSUFFICIENT_EVIDENCE}</td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">${t("reports.none")}</p>`}</section>`;
  bindRowLinks(view);
}

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
    <td><b>${b.f1.toFixed(3)}</b> <span class="muted small">[${b.f1_ci95[0].toFixed(2)}–${b.f1_ci95[1].toFixed(2)}]</span></td><td class="barcell">${ciBar(b.f1, b.f1_ci95, cls)}</td></tr>`;
  const rows = [
    d.all && row("eval.cv.row_ddm_all", d.all, "good"),
    d.untouched && row("eval.cv.row_ddm_untouched", d.untouched, "good"),
    cv.local_vlm?.all && row("eval.cv.row_vlm_all", cv.local_vlm.all, ""),
    cv.local_vlm?.untouched && row("eval.cv.row_vlm_untouched", cv.local_vlm.untouched, ""),
  ].filter(Boolean).join("");
  const paired = (k, key) => cv.paired_f1_difference?.[k] ? `<li>${esc(t(key, { d: cv.paired_f1_difference[k].difference.toFixed(3), lo: cv.paired_f1_difference[k].ci95[0].toFixed(2), hi: cv.paired_f1_difference[k].ci95[1].toFixed(2), n: cv.paired_f1_difference[k].recordings }))}</li>` : "";
  const folds = Object.entries(d.per_fold).map(([f, x]) => `<span class="chip ok">${esc(f.replace("fold", t("eval.cv.fold") + " "))}: F1 ${x.f1.toFixed(2)}</span>`).join("");
  return `<section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.cv")}</h3><p>${t("eval.cv_sub", { n: cv.protocol.recordings })}</p></div>
    <table class="eval-table"><thead><tr><th>${t("eval.cv.col_setup")}</th><th>${t("eval.cv.col_rec")}</th><th>${t("eval.cv.col_events")}</th><th>${t("eval.col_precision")}</th><th>${t("eval.col_recall")}</th><th>F1 [95% CI]</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <ul class="cv-notes">${paired("all", "eval.cv.paired_all")}${paired("untouched", "eval.cv.paired_untouched")}</ul>
    <p class="chips">${folds}</p><p class="muted small">${esc(t("eval.cv_note"))}</p></section>`;
}

function secondLookSection(sl) {
  const a = sl.cross_validation_recordings, e = sl.edited_recordings;
  const violating = e.rows.filter((r) => r.truth !== "Compliant").length;
  const compliant = e.rows.length - violating;
  return `<section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.sl")}</h3><p>${t("eval.sl_sub", { n: a.weak_events })}</p></div>
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
    <section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.tuning")}</h3><p>${t("eval.tuning_sub")}</p></div>
      ${shipped && first ? `<p class="callout">${esc(t("eval.tuning_delta", { from: first.f1, to: shipped.f1 }))}</p>` : ""}
      <table class="eval-table"><thead><tr><th>${t("eval.col_backend")}</th><th>F1</th><th></th><th>${t("eval.col_precision")}</th><th>${t("eval.col_recall")}</th><th>${t("eval.col_seq")}</th><th>${t("eval.col_time")}</th></tr></thead><tbody>
      ${d.backends.map((r) => `<tr class="${r.shipped ? "shipped" : ""}"><td>${esc(t(`eval.backend.${r.id}`))}${r.shipped ? ` <span class="badge tone-green">${esc(t("eval.deployed"))}</span>` : ""}</td><td><b>${r.f1.toFixed(3)}</b></td><td class="barcell">${bar(r.f1, 1, r.shipped ? "good" : "")}</td><td>${r.precision.toFixed(3)}</td><td>${r.recall.toFixed(3)}</td><td>${r.sequence_similarity.toFixed(3)}</td><td>${Math.round(r.seconds_per_video)}s</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.tuning_note"))}</p></section>
    <section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.vlm")}</h3><p>${t("eval.vlm_sub")}</p></div>
      <table class="eval-table"><tbody>${d.vlm_selection.map((r, i) => `<tr class="${i === 0 ? "shipped" : ""}"><td>${esc(r.model)} <span class="muted small">${esc(t(r.think_off ? "eval.mode_off" : "eval.mode_default"))}</span></td><td><b>${r.correct}/${r.cases}</b></td><td class="barcell">${bar(r.accuracy, 1, i === 0 ? "good" : "")}</td><td>${r.seconds}s / ${esc(t("eval.per_clip"))}</td></tr>`).join("")}</tbody></table></section>
    ${b ? `<section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.baseline")}</h3><p>${t("eval.baseline_sub")}</p></div>${tiles}
      <table class="eval-table"><thead><tr><th>${t("eval.col_video")}</th><th>${t("eval.col_truth")}</th><th>${t("eval.col_vlm")}</th><th>PraxiProof</th></tr></thead><tbody>
      ${b.videos.map((v) => `<tr><td>${esc(v.id)}</td><td>${esc(labelText(v.truth))}</td><td class="chips">${v.baseline.map((l) => baselineChip(l, v.truth)).join("")}</td><td>${v.praxiproof === v.truth ? `<span class="chip ok">${esc(labelText(v.praxiproof))}</span>` : `<span class="chip warn">${esc(labelText(v.praxiproof))}</span>`}</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.baseline_note"))}</p></section>` : ""}
    ${d.second_look ? secondLookSection(d.second_look) : ""}
    ${d.stepfun ? `<section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("eval.stepfun")}</h3><p>${t("eval.stepfun_sub")}</p></div>
      <table class="eval-table"><thead><tr><th>${t("eval.col_model")}</th><th>${t("eval.col_time")}</th><th>${t("eval.col_rules")}</th></tr></thead><tbody>
      ${d.stepfun.runs.map((r) => `<tr><td>${esc(r.model)}</td><td>${r.seconds}s</td><td>${r.error ? `<span class="chip bad">${esc(r.error)}</span>` : `${r.rules}${r.rejected ? ` <span class="muted small">(${esc(t("eval.rejected", { n: r.rejected }))})</span>` : ""}`}</td></tr>`).join("")}
      </tbody></table><p class="muted small">${esc(t("eval.stepfun_note"))}</p></section>` : ""}`;
}

async function renderSettings() {
  const [s, h] = await Promise.all([rapi("/api/settings"), rapi("/health")]);
  let models = [];
  let modelError = "";
  try {
    models = await rapi("/api/models");
  } catch (err) {
    modelError = err.message;
  }
  const describe = (m) => [m.parameter_size, m.quantization, m.capabilities.filter((c) => c !== "completion").join("/")].filter(Boolean).join(" · ");
  const options = (capability, current) => {
    const fits = models.filter((m) => m.capabilities.includes(capability));
    const names = new Set(fits.map((m) => m.name));
    const extra = names.has(current) ? "" : `<option value="${esc(current)}" selected>${esc(current)}</option>`;
    return extra + fits.map((m) => `<option value="${esc(m.name)}" ${m.name === current ? "selected" : ""}>${esc(m.name)}${describe(m) ? ` — ${esc(describe(m))}` : ""}</option>`).join("");
  };
  const ok = (b) => (b ? `<span class="badge pass">${t("settings.available")}</span>` : `<span class="badge violation">${t("settings.missing")}</span>`);
  view.innerHTML = `<div class="page-head"><div><h1>${t("settings.title")}</h1><p>${t("settings.subtitle")}</p></div></div>
    <form class="card settings-form" id="settings-form">
      <div class="card-head"><h3>${t("settings.models_section")}</h3></div>
      ${modelError ? `<p class="error-text">${esc(t("settings.models_unavailable", { error: modelError }))}</p>` : ""}
      <label>${t("settings.llm")} ${ok(h.models.llm)}<select name="llm_model">${options("completion", s.llm_model)}</select><small>${t("settings.llm_hint")}</small></label>
      <label>${t("settings.vlm")} ${ok(h.models.vlm)}<select name="vlm_model">${options("vision", s.vlm_model)}</select><small>${t("settings.vlm_hint")}</small></label>
      <label class="check"><span><input type="checkbox" name="vlm_thinking" ${s.vlm_thinking ? "checked" : ""}> ${t("settings.vlm_thinking")}</span><small>${t("settings.vlm_thinking_hint")}</small></label>
      <label>${t("settings.backend")}<select name="video_backend">
        <option value="local_vlm" ${s.video_backend === "local_vlm" ? "selected" : ""}>${t("settings.backend_local")}</option>
        <option value="ddm_vlm" ${s.video_backend === "ddm_vlm" ? "selected" : ""}>${t("settings.backend_ddm")}</option>
        <option value="nvidia_sop" ${s.video_backend === "nvidia_sop" ? "selected" : ""}>${t("settings.backend_bp")}</option>
      </select></label>
      <label>${t("settings.ddm_checkpoint")}<input type="text" name="ddm_checkpoint" value="${esc(s.ddm_checkpoint || "")}" placeholder="/home/…/ddm_server_fan.ckpt"><small>${t("settings.ddm_hint")}</small></label>
      <label>${t("settings.reference_dir")}<input type="text" name="reference_dir" value="${esc(s.reference_dir || "")}" placeholder="/home/…/references/server_fan"><small>${t("settings.reference_hint")}</small></label>
      <label>${t("settings.bp_url")}<input type="text" name="sop_bp_url" value="${esc(s.sop_bp_url || "")}" placeholder="http://127.0.0.1:8000/..."></label>
      <label class="check"><span><input type="checkbox" name="second_look" ${s.second_look ? "checked" : ""}> ${t("settings.second_look")}</span><small>${t("settings.second_look_hint")}</small></label>
      <label>${t("settings.confidence")}<input type="number" name="min_confidence" min="0" max="1" step="0.05" value="${esc(s.min_confidence)}"><small>${t("settings.confidence_hint")}</small></label>
      <p class="form-error" id="settings-error"></p>
      <div><button class="btn primary" type="submit">${t("settings.save")}</button></div>
    </form>
    <section class="card" style="margin-top:20px"><div class="card-head"><h3>${t("settings.system")}</h3></div><div class="kv">
      <div>${t("settings.language")}</div><div><button class="btn small ${LANG === "en" ? "primary" : "ghost"}" data-lang="en">English</button> <button class="btn small ${LANG === "zh" ? "primary" : "ghost"}" data-lang="zh">中文</button></div>
      <div>Ollama</div><div>${esc(s.ollama_url)} — ${h.ollama === "ok" ? `<span class="badge pass">${t("settings.reachable")}</span>` : `<span class="badge violation">${esc(h.ollama)}</span>`}</div>
      <div>${t("settings.version")}</div><div>${esc(h.version)}</div>
    </div></section>`;
  const form = $("#settings-form");
  const syncBackend = () => {
    form.sop_bp_url.disabled = form.video_backend.value !== "nvidia_sop";
    form.ddm_checkpoint.disabled = form.video_backend.value !== "ddm_vlm";
    form.reference_dir.disabled = form.video_backend.value !== "ddm_vlm";
  };
  form.video_backend.addEventListener("change", syncBackend);
  syncBackend();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    $("#settings-error").textContent = "";
    const body = {
      llm_model: form.llm_model.value,
      vlm_model: form.vlm_model.value,
      vlm_thinking: form.vlm_thinking.checked,
      video_backend: form.video_backend.value,
      sop_bp_url: form.sop_bp_url.value.trim() || null,
      ddm_checkpoint: form.ddm_checkpoint.value.trim() || null,
      reference_dir: form.reference_dir.value.trim() || null,
      min_confidence: Number(form.min_confidence.value),
      second_look: form.second_look.checked,
    };
    try {
      await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      toast(t("settings.saved"));
      refreshHealth();
      render(true);
    } catch (err) {
      $("#settings-error").textContent = err.message;
    }
  });
  view.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => switchLang(b.dataset.lang)));
}

async function refreshHealth() {
  try {
    const h = await api("/health");
    const good = h.ollama === "ok" && Object.values(h.models).every(Boolean);
    $("#health").className = `health ${good ? "ok" : "bad"}`;
    $("#health").title = good ? t("top.health_ok") : t("top.health_bad", { detail: h.ollama });
  } catch {
    $("#health").className = "health bad";
  }
}

// Minimal, XSS-safe markdown for agent answers: **bold**, `code`, "* item" bullets, blank-line paragraphs.
function mdLite(text) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
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
    if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}

async function render(keepScroll = false) {
  const token = ++state.renderToken;
  clearTimeout(state.pollTimer);
  const [route, id] = (location.hash.slice(1) || "dashboard").split("/");
  const navView = { run: "runs", pipeline: "runs", manual: "manuals", skill: "skills" }[route] || route;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === navView));
  const scroll = window.scrollY;
  if (!keepScroll) view.innerHTML = `<p class="empty">${t("common.loading")}</p>`;
  const routes = { dashboard: renderDashboard, runs: renderRuns, run: () => renderRun(id), pipeline: () => renderPipeline(id), manuals: renderManuals, manual: () => renderManual(id), videos: renderVideos, skills: renderSkills, skill: () => renderSkill(id), reports: renderReports, evaluation: renderEvaluation, settings: renderSettings };
  try {
    await (routes[route] || renderDashboard)();
  } catch (err) {
    if (err === STALE) return;
    if (token === state.renderToken) view.innerHTML = `<section class="card"><p class="error-text">${esc(err.message)}</p></section>`;
  }
  if (keepScroll) window.scrollTo(0, scroll);
}

function applyStaticText() {
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-html]").forEach((el) => (el.innerHTML = t(el.dataset.i18nHtml)));
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => (el.placeholder = t(el.dataset.i18nPlaceholder)));
}

function switchLang(lang) {
  setLang(lang);
  applyStaticText();
  refreshHealth();
  render(true);
}

$("#lang-toggle").addEventListener("click", () => switchLang(LANG === "zh" ? "en" : "zh"));

$("#search").addEventListener("input", (e) => {
  state.query = e.target.value.trim().toLowerCase();
  const route = (location.hash.slice(1) || "dashboard").split("/")[0];
  if (["runs", "manuals", "videos", "skills", "reports"].includes(route)) render(true);
  else if (state.query) location.hash = "#runs";
});
window.addEventListener("hashchange", () => render());
applyStaticText();
render();
refreshHealth();
setInterval(refreshHealth, 30000);
