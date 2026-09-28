async function renderVideos() {
  const videos = (await rapi("/api/videos")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("videos.title")}</h1><p>${t("videos.subtitle")}</p></div></div>
    <div class="grid-2 mb"><section class="card upload-card video">${dropzone("video", "video/*", t("dash.video_drop"))}</section></div>
    <div class="grid-4">${videos.map((v) => `<section class="card"><img class="thumb" style="width:100%;height:150px" src="/api/videos/${esc(v.id)}/frame?t=${Math.min(2, v.meta.duration / 2).toFixed(1)}" alt="">
      <p style="margin:10px 0 2px"><b>${esc(v.filename)}</b></p>${v.note ? `<p style="margin:0 0 4px"><span class="badge warn">${esc(t("video.note"))}</span> ${esc(v.note)}</p>` : ""}<p class="muted" style="margin:0">${esc(v.id)} · ${fmtDuration(v.meta.duration)} · ${v.meta.width}×${v.meta.height} · ${fmtBytes(v.size_bytes)}</p>
      <button class="btn primary small" style="margin-top:10px" data-verify="${esc(v.id)}">${t("videos.verify")}</button></section>`).join("") || `<p class="empty">${t("videos.none")}</p>`}</div>`;
  bindDropzones(view);
  view.querySelectorAll("[data-verify]").forEach((b) => b.addEventListener("click", () => openRunDialog({ video_id: b.dataset.verify })));
}
