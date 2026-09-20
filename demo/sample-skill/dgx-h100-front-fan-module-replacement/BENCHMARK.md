# BENCHMARK: DGX H100 front fan module replacement — PraxiProof demo skill

Modeled on the "Evaluated" tier of NVIDIA's Verified Skills spec: real measurements
against a fixed task set with hand-labeled ground truth, not self-reported claims.

Task set: 3 demo recording(s) compiled from `demo/requirements/dgx-h100-front-fan.json`, scored against hand-labeled expected verdicts in `demo/observations/*.json` (regenerate with `praxiproof bench`).

| Dimension | Score | What it measures |
|---|---|---|
| Correctness | 1.0 | rule verdict (PASS/VIOLATION/...) matches the hand-labeled expectation |
| Discoverability | 1.0 | every rule claim quotes the exact manual passage a human expects |
| Effectiveness | 1.0 | every verdict's evidence ids resolve to a real manual/video citation |
| Security | 1.0 (no issues) | no verdict states a claim it cannot trace to evidence; `evals/evals.json`'s negative cases additionally check the agent declines out-of-scope questions instead of guessing |
| Efficiency | not measured here | this harness scores the deterministic constraint engine, not VLM/LLM latency — see `praxiproof eval-sop` for per-video backend timing |

## Per-status recall

| Status | Recall |
|---|---|
| pass | 1.0 |
| violation | 1.0 |

## Per-recording detail

| Recording | Accuracy | Citation accuracy | Evidence traceability | Traceability issues |
|---|---|---|---|---|
| fan_replacement_A | 1.0 | 1.0 | 1.0 | 0 |
| fan_replacement_B | 1.0 | 1.0 | 1.0 | 0 |
| fan_replacement_C | 1.0 | 1.0 | 1.0 | 0 |

> Efficiency and a live agent-vs-no-agent differential (NVIDIA's exact Tier-3 method: run the same task set through `ComplianceAgent` with and without its tools) need a reachable Ollama endpoint; this harness runs offline against fixtures so it can be regenerated in CI. Once Ollama is reachable, extend this with a run over `evals/evals.json`, including its negative cases.
