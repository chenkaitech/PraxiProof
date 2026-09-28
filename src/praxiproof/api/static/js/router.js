// Health/theme/language chrome, the hash router, and the calls that boot the page. Loaded last, since it wires
// together every view defined in js/views/*.
async function refreshHealth() {
  const el = $("#health");
  try {
    const h = await api("/health");
    const good = h.ollama === "ok" && Object.values(h.models).every(Boolean);
    el.className = `health ${good ? "ok" : "bad"}`;
    el.textContent = good ? t("top.health_ok") : t("top.health_bad_short");
    el.title = good ? t("top.health_ok") : t("top.health_bad", { detail: h.ollama });
  } catch {
    el.className = "health bad";
    el.textContent = t("top.health_bad_short");
  }
  refreshDataNote();
}

// Where the text and the video frames are sent, straight from the server's provider configuration.
async function refreshDataNote() {
  try {
    const flow = (await api("/api/settings")).data_flow;
    const place = (where) => (where === "local" ? t("settings.data_flow_local") : where);
    $("#flow-text").textContent = place(flow.text);
    $("#flow-frames").textContent = place(flow.frames);
    $("#data-note").hidden = false;
  } catch {
    $("#data-note").hidden = true;
  }
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
try {
  applyTheme(localStorage.getItem("pp-theme"));
} catch {}
$("#theme-toggle").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const next = dark ? "light" : "dark";
  applyTheme(next);
  try {
    localStorage.setItem("pp-theme", next);
  } catch {}
});

// Shape of a page while it loads (announced once for assistive tech; the real content replaces it).
const skeleton = () => `<div role="status" aria-label="${esc(t("common.loading"))}"><div class="sk title"></div><div class="sk line"></div><div class="sk block mt"></div><div class="sk block mt"></div></div>`;

async function render(keepScroll = false) {
  const token = ++state.renderToken;
  clearTimeout(state.pollTimer);
  const [route, id] = (location.hash.slice(1) || "dashboard").split("/");
  const navView = { run: "runs", pipeline: "runs", manual: "manuals", skill: "skills" }[route] || route;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === navView));
  const scroll = window.scrollY;
  view.classList.toggle("enter", !keepScroll);  // page entrance only on navigation, not on the 3 s polling refresh
  if (!keepScroll) view.innerHTML = skeleton();
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
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  document.querySelectorAll("[data-i18n-title]").forEach((el) => (el.title = t(el.dataset.i18nTitle)));
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
