async function renderRuns() {
  const runs = await rapi("/api/runs");
  view.innerHTML = `<div class="page-head"><div><h1>${t("runs.title")}</h1><p>${t("runs.subtitle")}</p></div><div class="spacer"></div><button class="btn primary" id="start">${t("common.start")}</button></div>
    <section class="card">${runsTable(runs)}</section>`;
  $("#start").addEventListener("click", () => openRunDialog());
  bindRowLinks(view);
  schedulePoll(runs.some((r) => busy(r.status)));
}
