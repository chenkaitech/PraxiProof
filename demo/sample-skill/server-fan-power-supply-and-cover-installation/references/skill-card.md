# Skill Card — server-fan-power-supply-and-cover-installation

| Field | Value |
|---|---|
| Description / Use Case | Guide a technician through Server Fan, Power Supply and Cover Installation and check the work against 7 rules compiled from the official manual (1 critical). Use when planning, performing, or reviewing this procedure. |
| Owner | PraxiProof project — compiled and verified by run `DEMO-C2` |
| License / Deployment Geography | _(not yet declared — set before distributing this skill outside the team)_ |
| Requirements / Dependencies | Ollama-served LLM/VLM (see `praxiproof.config.Settings`); video observed via `fixture` |
| Risks & Mitigations | VLM misclassification of a step can produce a false PASS or VIOLATION, mitigated by per-verdict evidence citation and confidence thresholds; the compliance agent must call `get_verification_report` rather than recompute a verdict itself, checked by the negative cases in `evals/evals.json` |
| References | 7 compiled rule(s), 1 critical; see `references/` |
| Version / Verified against | run `DEMO-C2` — verdicts {'PASS': 4, 'VIOLATION': 2, 'UNVERIFIED': 0, 'INSUFFICIENT_EVIDENCE': 1} |
