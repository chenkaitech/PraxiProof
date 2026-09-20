"""Render the demo verification benchmark as a NVIDIA-Verified-Skills-style BENCHMARK.md.

Modeled on the "Evaluated" tier of NVIDIA's Verified Skills spec: real measurements against a
fixed task set with hand-labeled ground truth, not self-reported claims. `cli.run_benchmark`
already computes these numbers from `demo/observations/*.json` against the hand-labeled
`expected` verdicts; this module only formats them. It deliberately does not fabricate an
Efficiency score or a live agent-vs-no-agent differential — those need a reachable LLM/VLM
endpoint (see the module docstring note below) which this deterministic harness does not use.
"""


def render_benchmark_md(result: dict, title: str) -> str:
    summary = result["summary"]
    cases = result["cases"]
    recalls = {k: v for k, v in summary.items() if k.endswith("_recall")}
    issue_counts = {name: len(c.get("traceability_issues", [])) for name, c in cases.items()}
    total_issues = sum(issue_counts.values())

    def mean(key: str) -> float:
        values = [c[key] for c in cases.values() if key in c]
        return round(sum(values) / len(values), 3) if values else 0.0

    lines = [
        f"# BENCHMARK: {title}",
        "",
        'Modeled on the "Evaluated" tier of NVIDIA\'s Verified Skills spec: real measurements',
        "against a fixed task set with hand-labeled ground truth, not self-reported claims.",
        "",
        f"Task set: {len(cases)} demo recording(s) compiled from `demo/requirements/dgx-h100-front-fan.json`, "
        "scored against hand-labeled expected verdicts in `demo/observations/*.json` "
        "(regenerate with `praxiproof bench`).",
        "",
        "| Dimension | Score | What it measures |",
        "|---|---|---|",
        f"| Correctness | {summary.get('verification_accuracy', 0.0)} | rule verdict (PASS/VIOLATION/...) matches the hand-labeled expectation |",
        f"| Discoverability | {mean('citation_accuracy')} | every rule claim quotes the exact manual passage a human expects |",
        f"| Effectiveness | {mean('evidence_traceability')} | every verdict's evidence ids resolve to a real manual/video citation |",
        (
            "| Security | "
            + ("1.0 (no issues)" if total_issues == 0 else f"{total_issues} traceability issue(s) — see per-recording table")
            + " | no verdict states a claim it cannot trace to evidence; "
            "`evals/evals.json`'s negative cases additionally check the agent declines out-of-scope "
            "questions instead of guessing |"
        ),
        "| Efficiency | not measured here | this harness scores the deterministic constraint engine, not VLM/LLM latency — see `praxiproof eval-sop` for per-video backend timing |",
        "",
        "## Per-status recall",
        "",
        "| Status | Recall |",
        "|---|---|",
    ]
    lines += [f"| {name.removesuffix('_recall')} | {value} |" for name, value in recalls.items()]
    lines += [
        "",
        "## Per-recording detail",
        "",
        "| Recording | Accuracy | Citation accuracy | Evidence traceability | Traceability issues |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {name} | {c.get('accuracy', 0.0)} | {c.get('citation_accuracy', 0.0)} | "
        f"{c.get('evidence_traceability', 0.0)} | {issue_counts[name]} |"
        for name, c in cases.items()
    ]
    lines += [
        "",
        "> Efficiency and a live agent-vs-no-agent differential (NVIDIA's exact Tier-3 method: run the "
        "same task set through `ComplianceAgent` with and without its tools) need a reachable Ollama "
        "endpoint; this harness runs offline against fixtures so it can be regenerated in CI. Once Ollama "
        "is reachable, extend this with a run over `evals/evals.json`, including its negative cases.",
        "",
    ]
    return "\n".join(lines)
