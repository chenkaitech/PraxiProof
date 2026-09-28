// The two <dialog> forms: starting a single verification run, and the upload-to-skill full pipeline.
async function openRunDialog(preset = {}) {
  const dialog = $("#run-dialog");
  const form = $("#run-form");
  const [manuals, videos, demos] = await Promise.all([api("/api/manuals"), api("/api/videos"), api("/api/demo/observations")]);
  const ready = manuals.filter((m) => m.status === "ready");
  if (!ready.length) return toast(t("dialog.need_manual"));
  form.manual_id.innerHTML = ready.map((m) => `<option value="${esc(m.id)}">${esc(m.id)} · ${esc(m.procedure)} (${esc(m.filename)})</option>`).join("");
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
  form.manual_id.innerHTML = usable.map((m) => `<option value="${esc(m.id)}">${esc(m.id)} · ${esc(m.procedure || m.procedure_hint || m.filename)} (${esc(m.filename)})</option>`).join("");
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
