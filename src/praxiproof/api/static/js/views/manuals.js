async function renderManuals() {
  const manuals = (await rapi("/api/manuals")).filter(matches);
  view.innerHTML = `<div class="page-head"><div><h1>${t("manuals.title")}</h1><p>${t("manuals.subtitle")}</p></div></div>
    <div class="grid-2 mb"><section class="card upload-card manual">${dropzone("manual", ".pdf,.html,.htm,.md,.markdown,.txt", t("dash.manual_drop"))}
      <label class="procedure-input">${t("dash.procedure")} <input id="procedure" placeholder="${esc(t("manuals.procedure_ph"))}"></label></section></div>
    <section class="card">${manuals.length ? `<table><thead><tr><th>ID</th><th>${t("manuals.col_file")}</th><th>${t("manuals.col_procedure")}</th><th>${t("manuals.col_status")}</th><th>${t("manuals.col_rules")}</th><th>${t("manuals.col_safety")}</th><th>${t("manuals.col_steps")}</th><th>${t("manuals.col_uploaded")}</th></tr></thead><tbody>
      ${manuals.map((m) => `<tr class="clickable" data-href="#manual/${esc(m.id)}"><td class="id">${esc(m.id)}</td><td>${esc(m.filename)}</td><td>${esc(m.procedure || m.procedure_hint || "")}</td><td>${statusBadge(m.status)}</td><td>${m.counts?.rules ?? "-"}</td><td>${m.counts?.safety_rules ?? "-"}</td><td>${m.counts?.steps ?? "-"}</td><td class="nowrap">${fmtDate(m.created_at)}</td></tr>`).join("")}
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
        <td>${r.evidence_ids.map((e) => m.evidence[e]).filter(Boolean).map((e) => `<b>${esc(e.citation)}</b> <q class="muted">${esc(plain(e.text).slice(0, 160))}</q>`).join("<br>")}</td></tr>`).join("")}
      </tbody></table></section>
      <section class="card mt"><div class="card-head"><h3>${t("manual.vocab")}</h3><p>${t("manual.vocab_sub")}</p></div>
        <table><tbody>${rs.events.map((e) => `<tr><td><code>${esc(e.label)}</code></td><td>${esc(e.description)}</td></tr>`).join("")}</tbody></table></section>
      ${m.rejected?.length ? `<section class="card mt"><div class="card-head"><h3>${t("manual.rejected")}</h3><p>${t("manual.rejected_sub")}</p></div>
        <table><tbody>${m.rejected.map((r) => `<tr><td class="error-text">${esc(r.error)}</td><td><code>${esc(JSON.stringify(r.item).slice(0, 240))}</code></td></tr>`).join("")}</tbody></table></section>` : ""}` : ""}`;
  $("#recompile").addEventListener("click", async () => { await api(`/api/manuals/${encodeURIComponent(id)}/recompile`, { method: "POST" }); render(true); });
  schedulePoll(busy(m.status));
}
