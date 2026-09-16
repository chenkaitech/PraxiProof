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
const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "—";
const fmtBytes = (n) => (n == null ? "" : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`);
const busy = (status) => status === "queued" || status === "processing";
const matches = (row) => !state.query || JSON.stringify(row).toLowerCase().includes(state.query);

function statusBadge(status) {
  const map = { PASS: "pass", VIOLATION: "violation", UNVERIFIED: "warn", INSUFFICIENT_EVIDENCE: "warn", done: "pass", ready: "pass", failed: "violation", queued: "neutral", processing: "info" };
  const label = { INSUFFICIENT_EVIDENCE: "Insufficient evidence", UNVERIFIED: "Unverified" }[status] || status;
  return `<span class="badge ${map[status] || "neutral"}">${esc(label)}</span>`;
}

function resultBadge(run) {
  if (busy(run.status)) return `<span class="badge info">${esc(run.stage || run.status)}…</span>`;
  if (run.status === "failed") return `<span class="badge violation">Failed</span>`;
  const r = run.result;
  if (!r) return "—";
  if (r === "PASS") return `<span class="badge pass">✓ PASS</span>`;
  if (r === "Needs Evidence") return `<span class="badge warn">? Needs Evidence</span>`;
  const cls = r === "Missing Step" ? "warn" : "violation";
  return `<span class="badge ${cls}">⚠ ${esc(r)}</span>`;
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
    <div><strong>${title}</strong><span>or click to browse</span></div>
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
      toast(`${record.filename} uploaded — compiling requirements`);
    } else {
      toast(`Uploading ${file.name}…`);
      const record = await api("/api/videos", { method: "POST", body });
      toast(`${record.filename} uploaded`);
    }
    render(true);
  } catch (err) {
    toast(`Upload failed: ${err.message}`);
  }
}

function manualRow(m) {
  if (!m) return `<p class="empty">No manual uploaded yet.</p>`;
  const icon = m.status === "ready" ? ICON.check : m.status === "failed" ? ICON.fail : ICON.spin;
  const sub = m.status === "failed" ? `<span class="error-text">${esc(m.error)}</span>` : `${esc(m.procedure || m.procedure_hint || "Compiling…")} | ${m.page_count ? `${m.page_count} pages | ` : ""}${fmtDate(m.created_at)}`;
  return `<a class="file-row" href="#manual/${esc(m.id)}" style="color:inherit">
    <span class="doc-icon">${ICON.doc}</span>
    <div class="grow"><div class="name">${esc(m.filename)}</div><div class="meta">${sub}</div></div>${icon}</a>`;
}

function videoRow(v) {
  if (!v) return `<p class="empty">No video uploaded yet — you can also verify a demo observation.</p>`;
  return `<a class="file-row" href="#videos" style="color:inherit">
    <img class="thumb" src="/api/videos/${esc(v.id)}/frame?t=${Math.min(2, v.meta.duration / 2).toFixed(1)}" alt="">
    <div class="grow"><div class="name">${esc(v.filename)}</div><div class="meta">${v.meta.width} × ${v.meta.height} | ${fmtBytes(v.size_bytes)} | ${fmtDate(v.created_at)}</div></div>${ICON.check}</a>`;
}

function runsTable(runs, compact = false) {
  const rows = runs.filter(matches);
  if (!rows.length) return `<p class="empty">No verification runs yet. Click “Start Verification”.</p>`;
  return `<table><thead><tr><th>#</th><th>Video / Observation</th>${compact ? "" : "<th>Procedure</th>"}<th>Manual</th><th>Run Date</th><th>Result</th><th>Violations</th></tr></thead><tbody>
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
      <div style="flex:1"><h4>${esc(f.kind)}: ${esc(f.statement)}</h4><p>${esc(f.reason)}</p>
      ${f.needed_evidence && !violation ? `<p class="muted">Needed: ${esc(f.needed_evidence)}</p>` : ""}</div>
      <span class="badge ${esc(f.severity)}">${esc(f.severity)}</span>
    </div>
    <div class="evidence-pair">
      <div class="evidence-box"><div class="label">Reference</div><b>Manual ${esc(manual?.citation || "—")}</b>${manual ? `<q>${esc(manual.text.slice(0, compact ? 110 : 400))}</q>` : ""}</div>
      <div class="evidence-box"><div class="label">Video Evidence</div><b>${video ? `${fmtTime(video.start)} – ${fmtTime(video.end)}` : "Not observed"}</b>${frame}${video ? `<span class="muted">${esc(f.video_name)}</span>` : ""}</div>
    </div>
  </div>`;
}

async function renderDashboard() {
  const [d, skills] = await Promise.all([api("/api/dashboard"), api("/api/skills")]);
  const m = d.latest_manual, v = d.latest_video, metrics = d.metrics;
  const now = new Date();
  const activeRun = d.recent_runs.find((r) => busy(r.status));
  const stages = ["Manual", "Requirement IR", "Alignment", "Verification", "Verified Skill"];
  const doneRun = d.latest_run;
  const stageState = (i) => {
    if (m && busy(m.status)) return i === 0 ? "done" : i === 1 ? "active" : "";
    if (activeRun) return i < 2 ? "done" : (i === 2 && activeRun.stage !== "verifying") || (i === 3 && activeRun.stage === "verifying") ? "active" : "";
    if (doneRun) return i < 4 || skills.some((s) => s.run_id === doneRun.id) ? "done" : "";
    return m?.status === "ready" && i < 2 ? "done" : "";
  };
  const stageInfo = [
    ["Extract procedures and safety rules", ICON.stageManual],
    ["Convert to structured requirements", ICON.stageIR],
    ["Match video to procedure steps", ICON.stageAlign],
    ["Detect deviations with evidence", ICON.stageVerify],
    ["Package as an Agent Skill", ICON.stageSkill],
  ];
  const metricCard = (title, metric, color, subtitle) => `<div class="card metric">${ring(metric?.value, color)}<div class="ring-label">${metric ? Math.round(metric.value * 100) + "%" : "—"}</div></div>
    <div><h4>${title}</h4><p>${subtitle}</p></div></div>`;
  const violations = metrics?.violations ?? 0;

  view.innerHTML = `
    <div class="page-head">
      <div><h1>Operational Verification Dashboard</h1><p>Compare standards with reality.</p></div>
      <div class="spacer"></div>
      <div class="date">${ICON.cal}<div>${now.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}<small>${now.toLocaleDateString("en-US", { weekday: "long" })}, ${now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}</small></div></div>
      <button class="btn primary big" id="start">Start Verification →</button>
    </div>

    <div class="grid-2">
      <section class="card upload-card manual">
        <div class="card-head"><div class="icon-chip blue">${ICON.doc}</div><div><h3>Official Procedure Manual</h3><p>Upload a PDF, HTML or Markdown procedure manual</p></div></div>
        ${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", "Drag and drop a manual here")}
        <label class="procedure-input">Procedure to compile <input id="procedure" placeholder="e.g. Front Fan Module Replacement (needed for long manuals)"></label>
        ${manualRow(m)}
        <div class="stats"><div>${ICON.list}<div><b>${m?.counts?.safety_rules ?? "—"}</b><small>safety rules</small></div></div><div>${ICON.doc}<div><b>${m?.counts?.rules ?? "—"}</b><small>rules · ${m?.counts?.steps ?? "—"} steps</small></div></div></div>
      </section>
      <section class="card upload-card video">
        <div class="card-head"><div class="icon-chip green"><svg viewBox="0 0 24 24"><path d="M9 7l8 5-8 5z" fill="#fff"/></svg></div><div><h3>Operation Video</h3><p>Upload an operation video</p></div></div>
        ${dropzone("video", "video/*", "Drag and drop a video file here")}
        ${videoRow(v)}
        <div class="stats"><div>${ICON.clock}<div><b>${v ? fmtDuration(v.meta.duration) : "—"}</b><small>duration</small></div></div><div>${ICON.cam}<div><b>${v ? esc(v.meta.format_name.toUpperCase()) : "—"}</b><small>format</small></div></div><div>${ICON.screen}<div><b>${v ? `${v.meta.height}p` : "—"}</b><small>resolution</small></div></div></div>
      </section>
    </div>

    <section class="card pipeline">
      ${stages.map((s, i) => `<div class="stage ${stageState(i)}"><div class="bubble">${stageInfo[i][1]}</div><div><b>${s}</b><small>${stageInfo[i][0]}</small></div></div>${i < 4 ? ICON.arrow : ""}`).join("")}
    </section>

    <div class="grid-4">
      ${metricCard("Evidence Traceability", metrics?.evidence_traceability, "#1a6cf0", metrics ? `${metrics.evidence_traceability.numerator} / ${metrics.evidence_traceability.denominator} verdicts fully cited` : "Run a verification to see results")}
      ${metricCard("Safety Coverage", metrics?.safety_coverage, "#12a150", metrics ? `${metrics.safety_coverage.numerator} / ${metrics.safety_coverage.denominator} safety rules decided from video` : "")}
      ${metricCard("Step Coverage", metrics?.step_coverage, "#1a6cf0", metrics ? `${metrics.step_coverage.numerator} / ${metrics.step_coverage.denominator} procedure steps observed` : "")}
      <div class="card metric">${ring(metrics ? Math.min(violations / Math.max(metrics.counts ? Object.values(metrics.counts).reduce((a, b) => a + b, 0) : 1, 1), 1) : 0, "#e5484d")}<div class="ring-label" style="color:#e5484d">${metrics ? violations : "—"}</div></div>
        <div><h4>Violations Found</h4><p>${metrics ? `${violations} issue${violations === 1 ? " requires" : "s require"} review` : ""}</p></div></div>
    </div>

    <div class="split" style="margin-top:20px">
      <section class="card"><div class="card-head"><h3>Recent Verification Runs</h3><div class="spacer"></div><a href="#runs">View all runs →</a></div>${runsTable(d.recent_runs.slice(0, 6), true)}</section>
      <section class="card"><div class="card-head"><h3>Latest Findings</h3><div class="spacer"></div>${doneRun ? `<a href="#run/${esc(doneRun.id)}">View all findings →</a>` : ""}</div>
        ${d.findings.length ? d.findings.slice(0, 2).map((f) => findingCard(f, true)).join('<div style="height:10px"></div>') : `<p class="empty">${doneRun ? "No open findings in the latest run." : "Findings appear here after a verification run."}</p>`}
      </section>
    </div>`;

  $("#start").addEventListener("click", () => openRunDialog());
  bindDropzones(view);
  bindRowLinks(view);
  schedulePoll((m && busy(m.status)) || !!activeRun);
}

async function openRunDialog(preset = {}) {
  const dialog = $("#run-dialog");
  const form = $("#run-form");
  const [manuals, videos, demos] = await Promise.all([api("/api/manuals"), api("/api/videos"), api("/api/demo/observations")]);
  const ready = manuals.filter((m) => m.status === "ready");
  if (!ready.length) return toast("Upload a manual and wait for its requirements to compile first.");
  form.manual_id.innerHTML = ready.map((m) => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.procedure)} (${esc(m.filename)})</option>`).join("");
  form.video_id.innerHTML = videos.map((v) => `<option value="${esc(v.id)}">${esc(v.filename)} (${fmtDuration(v.meta.duration)})</option>`).join("") || "<option value=''>No videos uploaded</option>";
  form.demo_observation.innerHTML = demos.map((o) => `<option value="${esc(o.name)}">${esc(o.title)}</option>`).join("");
  form.source.value = preset.video_id || videos.length ? "video" : "demo";
  if (preset.video_id) form.video_id.value = preset.video_id;
  $("#run-error").textContent = "";
  dialog.showModal();
  form.onsubmit = async (event) => {
    if (event.submitter?.value !== "ok") return;
    event.preventDefault();
    const body = { manual_id: form.manual_id.value };
    if (form.source.value === "video") {
      if (!form.video_id.value) return ($("#run-error").textContent = "Upload a video or choose a demo observation.");
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

async function renderRuns() {
  const runs = await api("/api/runs");
  view.innerHTML = `<div class="page-head"><div><h1>Verification Runs</h1><p>Every comparison between a manual and an operation.</p></div><div class="spacer"></div><button class="btn primary" id="start">Start Verification →</button></div>
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
        ? `<div class="evidence-box"><div class="label">Manual ${esc(e.citation)}${e.locator.section ? ` · ${esc(e.locator.section)}` : ""}</div><q>${esc(e.text)}</q></div>`
        : `<div class="evidence-box"><div class="label">Video ${esc(e.citation)} · confidence ${Math.round(e.confidence * 100)}%</div>${esc(e.text)}${videoId ? `<img src="/api/videos/${esc(videoId)}/frame?t=${e.locator.start.toFixed(1)}" alt="" data-seek="${e.locator.start}">` : ""}</div>`
    )
    .join("");
}

async function renderRun(id) {
  const [run, skills] = await Promise.all([api(`/api/runs/${encodeURIComponent(id)}`), api("/api/skills")]);
  const head = `<div class="page-head"><div><h1>${esc(run.id)} · ${esc(run.video_name)}</h1><p>${esc(run.procedure)} — ${esc(run.manual_name)}</p></div><div class="spacer"></div><a class="btn ghost" href="#runs">← All runs</a></div>`;
  if (busy(run.status) || run.status === "failed") {
    view.innerHTML = `${head}<section class="card">${run.status === "failed" ? `<p class="error-text">Run failed: ${esc(run.error)}</p>` : `<p>${ICON.spin} ${esc(run.stage || "queued")}… Video analysis with the local VLM can take several minutes.</p>`}</section>`;
    return schedulePoll(busy(run.status));
  }
  const report = run.report;
  const skill = skills.find((s) => s.run_id === run.id);
  const order = { VIOLATION: 0, INSUFFICIENT_EVIDENCE: 1, UNVERIFIED: 2, PASS: 3 };
  const verdicts = [...report.verdicts].sort((a, b) => order[a.status] - order[b.status] || a.rule_id.localeCompare(b.rule_id));
  view.innerHTML = `${head}
    <section class="card run-head">${resultBadge(run)}<div class="counts">${Object.entries(run.counts).map(([k, n]) => `${statusBadge(k)} <b>${n}</b>`).join(" &nbsp; ")}</div><div class="spacer" style="flex:1"></div>
      ${skill ? `<a class="btn ghost" href="#skill/${esc(skill.id)}">View Skill ${esc(skill.id)}</a>` : ""}
      <button class="btn primary" id="compile">${skill ? "Recompile Skill" : "Compile Verified Skill"}</button></section>
    <div class="split" style="margin-top:20px">
      <div class="stack">
        <section class="card"><div class="card-head"><h3>Verdicts</h3><p>Each rule compiled from the manual, checked deterministically against observed events.</p></div>
          <div class="verdicts">${verdicts.map((v) => `
            <div class="verdict ${v.status}">
              <div class="verdict-head"><span class="title">${esc(v.rule_id)} · ${esc(v.statement)}</span>${statusBadge(v.status)}<span class="badge ${esc(v.severity)}">${esc(v.severity)}</span><span class="badge neutral">${esc(v.category)}</span></div>
              <p class="reason"><code>${esc(signature(v.constraint))}</code> ${esc(v.reason)}</p>
              ${v.needed_evidence ? `<p class="needed">Needed evidence: ${esc(v.needed_evidence)}</p>` : ""}
              <div class="evidence-pair">${evidenceLine(v.requirement_evidence_ids, run.evidence, run.video_id)}${evidenceLine(v.observation_evidence_ids, run.evidence, run.video_id)}</div>
              ${v.status !== "PASS" ? `<div class="verdict-actions"><span class="muted">Review:</span>
                <button class="btn small ${v.review === "accepted" ? "success" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="accepted">Confirm finding</button>
                <button class="btn small ${v.review === "rejected" ? "danger" : "ghost"}" data-review="${esc(v.rule_id)}" data-decision="rejected">Reject finding</button></div>` : ""}
            </div>`).join("")}</div>
        </section>
        <section class="card"><div class="card-head"><h3>Observation alignment</h3><p>How observed events were matched to the manual's step vocabulary.</p></div>
          <table><thead><tr><th>Event</th><th>Observed label</th><th>Matched step</th><th>Method</th><th>Time</th></tr></thead><tbody>
          ${report.alignment.map((a) => { const e = run.observation.events.find((x) => x.event_id === a.event_id) || {}; return `<tr><td>${esc(a.event_id)}</td><td>${esc(a.observed_label)}</td><td>${esc(a.aligned_labels.join(", ") || "—")}</td><td>${esc(a.method)}</td><td>${fmtTime(e.start)}–${fmtTime(e.end)}</td></tr>`; }).join("")}
          </tbody></table>
          ${run.traceability_issues?.length ? `<p class="error-text">Traceability issues: ${run.traceability_issues.map(esc).join("; ")}</p>` : ""}
        </section>
      </div>
      <div class="stack">
        ${run.video_id ? `<section class="card"><div class="card-head"><h3>Operation video</h3></div><video id="player" controls preload="metadata" src="/api/videos/${esc(run.video_id)}/file"></video></section>` : ""}
        <section class="card"><div class="card-head"><h3>Ask the Compliance Agent</h3></div>
          <div class="chat"><textarea id="question" placeholder="e.g. Did the technician respect the 30-second fan replacement limit? Cite the manual."></textarea>
          <button class="btn primary" id="ask">Ask</button><div id="answer"></div></div>
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
  $("#compile").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const s = await api(`/api/runs/${encodeURIComponent(run.id)}/skill`, { method: "POST" });
      toast(`Skill ${s.name} compiled`);
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
    $("#answer").innerHTML = `<p>${ICON.spin} Thinking…</p>`;
    try {
      const r = await api("/api/agent/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, run_id: run.id }) });
      $("#answer").innerHTML = `<div class="answer">${esc(r.answer)}</div><p class="muted">Tools used: ${r.tool_calls.map((t) => esc(t.tool)).join(", ") || "none"}</p>`;
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
  const manuals = (await api("/api/manuals")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>Manuals</h1><p>Official procedures compiled into executable rules.</p></div></div>
    <div class="grid-2" style="margin-bottom:20px"><section class="card upload-card manual">${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", "Drag and drop a manual here")}
      <label class="procedure-input">Procedure to compile <input id="procedure" placeholder="e.g. Front Fan Module Replacement"></label></section></div>
    <section class="card">${manuals.length ? `<table><thead><tr><th>ID</th><th>File</th><th>Procedure</th><th>Status</th><th>Rules</th><th>Safety</th><th>Steps</th><th>Uploaded</th></tr></thead><tbody>
      ${manuals.map((m) => `<tr class="clickable" data-href="#manual/${esc(m.id)}"><td>${esc(m.id)}</td><td>${esc(m.filename)}</td><td>${esc(m.procedure || m.procedure_hint || "")}</td><td>${statusBadge(m.status)}</td><td>${m.counts?.rules ?? "—"}</td><td>${m.counts?.safety_rules ?? "—"}</td><td>${m.counts?.steps ?? "—"}</td><td>${fmtDate(m.created_at)}</td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">No manuals yet.</p>`}</section>`;
  bindDropzones(view);
  bindRowLinks(view);
  schedulePoll(manuals.some((m) => busy(m.status)));
}

async function renderManual(id) {
  const m = await api(`/api/manuals/${encodeURIComponent(id)}`);
  const rs = m.requirement_set;
  view.innerHTML = `<div class="page-head"><div><h1>${esc(m.procedure || m.filename)}</h1><p>${esc(m.id)} · ${esc(m.filename)} · ${esc(m.extractor || "")}${m.page_count ? ` · ${m.page_count} pages` : ""}</p></div><div class="spacer"></div>
      ${statusBadge(m.status)}<button class="btn ghost" id="recompile">Recompile</button><a class="btn ghost" href="#manuals">← Manuals</a></div>
    ${m.status === "failed" ? `<section class="card"><p class="error-text">${esc(m.error)}</p></section>` : ""}
    ${busy(m.status) ? `<section class="card"><p>${ICON.spin} Extracting text and compiling rules with ${esc(m.procedure_hint ? `focus on “${m.procedure_hint}”` : "the LLM")}…</p></section>` : ""}
    ${rs ? `<section class="card"><div class="card-head"><h3>Compiled rules</h3><p>Natural-language SOP → executable constraints, each tied to its manual source.</p></div>
      <table><thead><tr><th>Rule</th><th>Constraint</th><th>Category</th><th>Severity</th><th>On camera</th><th>Source</th></tr></thead><tbody>
      ${rs.requirements.map((r) => `<tr><td><b>${esc(r.rule_id)}</b><br>${esc(r.statement)}</td><td><code>${esc(signature(r.constraint))}</code></td><td>${esc(r.category)}</td><td><span class="badge ${esc(r.severity)}">${esc(r.severity)}</span></td><td>${r.observable ? "yes" : "no"}</td>
        <td>${r.evidence_ids.map((e) => m.evidence[e]).filter(Boolean).map((e) => `<b>${esc(e.citation)}</b> <q class="muted">${esc(e.text.slice(0, 160))}</q>`).join("<br>")}</td></tr>`).join("")}
      </tbody></table></section>
      <section class="card" style="margin-top:20px"><div class="card-head"><h3>Step vocabulary</h3><p>Events the video observer is asked to find.</p></div>
        <table><tbody>${rs.events.map((e) => `<tr><td><code>${esc(e.label)}</code></td><td>${esc(e.description)}</td></tr>`).join("")}</tbody></table></section>
      ${m.rejected?.length ? `<section class="card" style="margin-top:20px"><div class="card-head"><h3>Rejected by validation</h3><p>Model output that failed the DSL or citation checks and was not used.</p></div>
        <table><tbody>${m.rejected.map((r) => `<tr><td class="error-text">${esc(r.error)}</td><td><code>${esc(JSON.stringify(r.item).slice(0, 240))}</code></td></tr>`).join("")}</tbody></table></section>` : ""}` : ""}`;
  $("#recompile").addEventListener("click", async () => { await api(`/api/manuals/${encodeURIComponent(id)}/recompile`, { method: "POST" }); render(true); });
  schedulePoll(busy(m.status));
}

async function renderVideos() {
  const videos = (await api("/api/videos")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>Videos</h1><p>Operation recordings to verify.</p></div></div>
    <div class="grid-2" style="margin-bottom:20px"><section class="card upload-card video">${dropzone("video", "video/*", "Drag and drop a video file here")}</section></div>
    <div class="grid-4">${videos.map((v) => `<section class="card"><img class="thumb" style="width:100%;height:150px" src="/api/videos/${esc(v.id)}/frame?t=${Math.min(2, v.meta.duration / 2).toFixed(1)}" alt="">
      <p style="margin:10px 0 2px"><b>${esc(v.filename)}</b></p><p class="muted" style="margin:0">${esc(v.id)} · ${fmtDuration(v.meta.duration)} · ${v.meta.width}×${v.meta.height} · ${fmtBytes(v.size_bytes)}</p>
      <button class="btn primary small" style="margin-top:10px" data-verify="${esc(v.id)}">Verify →</button></section>`).join("") || `<p class="empty">No videos yet.</p>`}</div>`;
  bindDropzones(view);
  view.querySelectorAll("[data-verify]").forEach((b) => b.addEventListener("click", () => openRunDialog({ video_id: b.dataset.verify })));
}

async function renderSkills() {
  const skills = (await api("/api/skills")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>Skills</h1><p>Agent Skills compiled from verified procedures.</p></div></div>
    <section class="card">${skills.length ? `<table><thead><tr><th>ID</th><th>Skill</th><th>Procedure</th><th>Verified by</th><th>Results</th><th>Created</th><th></th></tr></thead><tbody>
    ${skills.map((s) => `<tr class="clickable" data-href="#skill/${esc(s.id)}"><td>${esc(s.id)}</td><td><code>${esc(s.name)}</code></td><td>${esc(s.procedure)}</td><td>${esc(s.run_id)}</td><td>${Object.entries(s.verification_summary || {}).filter(([, n]) => n).map(([k, n]) => `${statusBadge(k)} ${n}`).join(" ")}</td><td>${fmtDate(s.created_at)}</td><td><a href="/api/skills/${esc(s.id)}/download">Download</a></td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">Compile a skill from a finished verification run.</p>`}</section>`;
  bindRowLinks(view);
}

async function renderSkill(id) {
  const [skills, md] = await Promise.all([api("/api/skills"), api(`/api/skills/${encodeURIComponent(id)}/skill.md`)]);
  const s = skills.find((x) => x.id === id);
  view.innerHTML = `<div class="page-head"><div><h1><code style="font-size:26px">${esc(s?.name)}</code></h1><p>${esc(s?.procedure)} · verified by <a href="#run/${esc(s?.run_id)}">${esc(s?.run_id)}</a></p></div><div class="spacer"></div>
    <a class="btn primary" href="/api/skills/${esc(id)}/download">Download skill package</a><a class="btn ghost" href="#skills">← Skills</a></div>
    <section class="card"><div class="card-head"><h3>SKILL.md</h3><p>Includes references/, evals/ and assets/ in the package.</p></div><div class="skill-md">${esc(md)}</div></section>`;
}

async function renderReports() {
  const runs = (await api("/api/runs")).filter((r) => r.status === "done" && matches(r));
  const details = await Promise.all(runs.slice(0, 20).map((r) => api(`/api/runs/${encodeURIComponent(r.id)}`)));
  const pct = (m) => (m ? `${Math.round(m.value * 100)}% <span class="muted">(${m.numerator}/${m.denominator})</span>` : "—");
  view.innerHTML = `<div class="page-head"><div><h1>Verification Reports</h1><p>How much of each procedure was proven, and with what evidence.</p></div></div>
    <section class="card">${details.length ? `<table><thead><tr><th>Run</th><th>Video / Observation</th><th>Result</th><th>Evidence traceability</th><th>Safety coverage</th><th>Step coverage</th><th>Observation alignment</th><th>Pass</th><th>Violation</th><th>Unverified</th><th>Insufficient</th></tr></thead><tbody>
    ${details.map((r) => `<tr class="clickable" data-href="#run/${esc(r.id)}"><td>${esc(r.id)}</td><td>${esc(r.video_name)}</td><td>${resultBadge(r)}</td><td>${pct(r.metrics.evidence_traceability)}</td><td>${pct(r.metrics.safety_coverage)}</td><td>${pct(r.metrics.step_coverage)}</td><td>${pct(r.metrics.observation_alignment)}</td>
      <td>${r.counts.PASS}</td><td>${r.counts.VIOLATION}</td><td>${r.counts.UNVERIFIED}</td><td>${r.counts.INSUFFICIENT_EVIDENCE}</td></tr>`).join("")}
    </tbody></table>` : `<p class="empty">No finished runs yet.</p>`}</section>`;
  bindRowLinks(view);
}

async function renderSettings() {
  const [s, h] = await Promise.all([api("/api/settings"), api("/health")]);
  const ok = (b) => (b ? `<span class="badge pass">available</span>` : `<span class="badge violation">missing</span>`);
  view.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Configured through environment variables on the server.</p></div></div>
    <section class="card"><div class="kv">
      <div>Ollama</div><div>${esc(s.ollama_url)} — ${h.ollama === "ok" ? '<span class="badge pass">reachable</span>' : `<span class="badge violation">${esc(h.ollama)}</span>`}</div>
      <div>Rule compiler LLM</div><div><code>${esc(s.llm_model)}</code> ${ok(h.models.llm)}</div>
      <div>Video VLM</div><div><code>${esc(s.vlm_model)}</code> ${ok(h.models.vlm)}</div>
      <div>Video backend</div><div><code>${esc(s.video_backend)}</code>${s.sop_blueprint_configured ? " · NVIDIA SOP blueprint endpoint configured" : " · NVIDIA SOP blueprint not configured"}</div>
      <div>Minimum event confidence</div><div>${esc(s.min_confidence)}</div>
      <div>Version</div><div>${esc(h.version)}</div>
    </div></section>`;
}

async function refreshHealth() {
  try {
    const h = await api("/health");
    const good = h.ollama === "ok" && Object.values(h.models).every(Boolean);
    $("#health").className = `health ${good ? "ok" : "bad"}`;
    $("#health").title = good ? "Models available" : `Model service issue: ${h.ollama}`;
  } catch {
    $("#health").className = "health bad";
  }
}

async function render(keepScroll = false) {
  const token = ++state.renderToken;
  clearTimeout(state.pollTimer);
  const [route, id] = (location.hash.slice(1) || "dashboard").split("/");
  const navView = { run: "runs", manual: "manuals", skill: "skills" }[route] || route;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === navView));
  const scroll = window.scrollY;
  const routes = { dashboard: renderDashboard, runs: renderRuns, run: () => renderRun(id), manuals: renderManuals, manual: () => renderManual(id), videos: renderVideos, skills: renderSkills, skill: () => renderSkill(id), reports: renderReports, settings: renderSettings };
  try {
    await (routes[route] || renderDashboard)();
  } catch (err) {
    if (token === state.renderToken) view.innerHTML = `<section class="card"><p class="error-text">${esc(err.message)}</p></section>`;
  }
  if (keepScroll) window.scrollTo(0, scroll);
}

$("#search").addEventListener("input", (e) => {
  state.query = e.target.value.trim().toLowerCase();
  const route = (location.hash.slice(1) || "dashboard").split("/")[0];
  if (["runs", "manuals", "videos", "skills", "reports"].includes(route)) render(true);
  else if (state.query) location.hash = "#runs";
});
window.addEventListener("hashchange", () => render());
render();
refreshHealth();
setInterval(refreshHealth, 30000);
