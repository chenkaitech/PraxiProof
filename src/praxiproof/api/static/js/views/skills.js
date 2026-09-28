async function renderSkills() {
  const skills = (await rapi("/api/skills")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("skills.title")}</h1><p>${t("skills.subtitle")}</p></div></div>
    <section class="card">${skills.length ? `<table><thead><tr><th>ID</th><th>${t("skills.col_skill")}</th><th>${t("skills.col_procedure")}</th><th>${t("skills.col_verified")}</th><th>${t("skills.col_results")}</th><th>${t("skills.col_review")}</th><th>${t("skills.col_created")}</th><th></th></tr></thead><tbody>
    ${skills.map((s) => `<tr class="clickable" data-href="#skill/${esc(s.id)}"><td class="id">${esc(s.id)}</td><td><code class="clip" title="${esc(s.name)}">${esc(s.name)}</code></td><td>${esc(s.procedure)}</td><td>${esc(s.run_id)}</td><td><div class="results">${Object.entries(s.verification_summary || {}).filter(([, n]) => n).map(([k, n]) => `<span class="nowrap">${statusBadge(k)} ${n}</span>`).join("")}</div></td><td>${reviewBadge(s)}</td><td class="nowrap">${fmtDate(s.created_at)}</td><td><a href="/api/skills/${esc(s.id)}/download">${t("common.download")}</a></td></tr>`).join("")}
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
