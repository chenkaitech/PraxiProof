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
    return extra + fits.map((m) => `<option value="${esc(m.name)}" ${m.name === current ? "selected" : ""}>${esc(m.name)}${describe(m) ? ` · ${esc(describe(m))}` : ""}</option>`).join("");
  };
  const place = (where) => (where === "local" ? t("settings.data_flow_local") : where);
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
    <section class="card mt"><div class="card-head"><h3>${t("settings.system")}</h3></div><div class="kv">
      <div>${t("settings.language")}</div><div><button class="btn small ${LANG === "en" ? "primary" : "ghost"}" data-lang="en">English</button> <button class="btn small ${LANG === "zh" ? "primary" : "ghost"}" data-lang="zh">中文</button></div>
      <div>Ollama</div><div>${esc(s.ollama_url)} · ${h.ollama === "ok" ? `<span class="badge pass">${t("settings.reachable")}</span>` : `<span class="badge violation">${esc(h.ollama)}</span>`}</div>
      <div>${t("settings.data_flow")}</div><div>${esc(t("settings.data_flow_text", { where: place(s.data_flow.text) }))}<br>${esc(t("settings.data_flow_frames", { where: place(s.data_flow.frames) }))}</div>
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
