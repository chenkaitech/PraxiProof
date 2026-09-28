// Reusable building blocks shared by several views: progress rings, upload dropzones, row-style summaries and tables.
function ring(value, tone) {
  const r = 32, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(1, value ?? 0));
  return `<div class="ring ring-wrap"><svg viewBox="0 0 76 76"><circle class="track" cx="38" cy="38" r="${r}"/><circle class="arc ${tone}" cx="38" cy="38" r="${r}" stroke-dasharray="${c * pct} ${c}" stroke-linecap="round"/></svg>`;
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
    ${rows.map((r) => `<tr class="clickable" data-href="#run/${esc(r.id)}"><td class="id">${esc(r.id)}</td><td>${esc(r.video_name)}</td>${compact ? "" : `<td>${esc(r.procedure)}</td>`}<td>${esc(r.manual_name)}</td><td class="nowrap">${fmtDate(r.created_at)}</td><td>${resultBadge(r)}</td><td>${r.violations ?? "-"}</td></tr>`).join("")}
  </tbody></table>`;
}

function bindRowLinks(root) {
  root.querySelectorAll("tr[data-href]").forEach((tr) => {
    const open = () => (location.hash = tr.dataset.href);
    tr.tabIndex = 0;
    tr.setAttribute("role", "link");
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || (e.key === " " && e.target === tr)) {
        e.preventDefault();
        open();
      }
    });
  });
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
      <div class="evidence-box"><div class="label">${esc(t("finding.reference"))}</div><b>${esc(t("finding.manual", { cite: manual?.citation || "-" }))}</b>${manual ? `<q>${esc(plain(manual.text).slice(0, compact ? 110 : 400))}</q>` : ""}</div>
      <div class="evidence-box"><div class="label">${esc(t("finding.video"))}</div><b>${video ? `${fmtTime(video.start)} to ${fmtTime(video.end)}` : esc(t("finding.not_observed"))}</b>${frame}${video ? `<span class="muted">${esc(f.video_name)}</span>` : ""}</div>
    </div>
  </div>`;
}

function evidenceLine(ids, evidence, videoId) {
  return ids
    .map((id) => evidence[id])
    .filter(Boolean)
    .map((e) =>
      e.source_type === "document"
        ? `<div class="evidence-box"><div class="label">${esc(t("ev.manual", { cite: e.citation }))}${e.locator.section && e.locator.section !== e.citation ? ` · ${esc(e.locator.section)}` : ""}</div><q>${esc(plain(e.text))}</q></div>`
        : `<div class="evidence-box"><div class="label">${esc(t("ev.video", { cite: e.citation, pct: Math.round(e.confidence * 100) }))}</div>${esc(e.text)}${videoId ? `<img src="/api/videos/${esc(videoId)}/frame?t=${e.locator.start.toFixed(1)}" alt="" data-seek="${e.locator.start}">` : ""}</div>`
    )
    .join("");
}

function signature(c) {
  if (c.type === "MUST_HAVE" || c.type === "MUST_NOT") return `${c.type}(${c.event})`;
  if (c.type === "COUNT") return `COUNT(${c.event} ≥ ${c.min_count})`;
  if (c.type === "MAX_INTERVAL") return `MAX_INTERVAL(${c.a} → ${c.b} ≤ ${c.seconds}s)`;
  return `${c.type}(${c.a}, ${c.b})`;
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
