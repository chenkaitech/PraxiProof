# Skill Card — dgx-h100-front-fan-module-replacement

| Field | Value |
|---|---|
| Description / Use Case | Guide a technician through DGX H100 Front Fan Module Replacement and check the work against 8 rules compiled from the official manual (2 critical). Use when planning, performing, or reviewing this procedure. |
| Owner | PraxiProof project — compiled and verified by run `DEMO-B` |
| License / Deployment Geography | _(not yet declared — set before distributing this skill outside the team)_ |
| Requirements / Dependencies | Ollama-served LLM/VLM (see `praxiproof.config.Settings`); video observed via `fixture` |
| Risks & Mitigations | VLM misclassification of a step can produce a false PASS or VIOLATION, mitigated by per-verdict evidence citation and confidence thresholds; the compliance agent must call `get_verification_report` rather than recompute a verdict itself, checked by the negative cases in `evals/evals.json` |
| References | 8 compiled rule(s), 2 critical; see `references/` |
| Version / Verified against | run `DEMO-B` — verdicts {'PASS': 6, 'VIOLATION': 2, 'UNVERIFIED': 0, 'INSUFFICIENT_EVIDENCE': 0} |
