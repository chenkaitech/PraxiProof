import argparse
import json
import logging
from pathlib import Path

from praxiproof.api.app import DEFAULT_DEMO_DIR
from praxiproof.config import get_settings, load_overrides


def main() -> None:
    parser = argparse.ArgumentParser(prog="praxiproof")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web app and API")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8090)

    bench = sub.add_parser("bench", help="score the verification engine on the demo reference set")
    bench.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    bench.add_argument("--skill-md", type=Path, help="also render a NVIDIA-Verified-Skill-style BENCHMARK.md to this path")

    compile_cmd = sub.add_parser("compile", help="compile a manual into constraints with the configured LLM")
    compile_cmd.add_argument("manual", type=Path)
    compile_cmd.add_argument("--procedure")

    sop = sub.add_parser("eval-sop", help="score the video backend on the NVIDIA SOP server-fan sample dataset")
    sop.add_argument("--data", type=Path, required=True, help="the extracted server_fan directory")
    sop.add_argument("--videos", nargs="+", default=["Install_12", "Install_13"])
    sop.add_argument("--out", type=Path, required=True)

    refs = sub.add_parser("build-references", help="extract reference images of each action from SOP training recordings")
    refs.add_argument("--data", type=Path, required=True, help="the extracted server_fan directory")
    refs.add_argument("--videos", nargs="+", required=True, help="training recordings to take frames from")
    refs.add_argument("--per-group", type=int, default=3)
    refs.add_argument("--out", type=Path, required=True)

    edits = sub.add_parser("make-edits", help="build compliant, missing-step and reordered copies of a SOP recording")
    edits.add_argument("--data", type=Path, required=True, help="the extracted server_fan directory")
    edits.add_argument("--video", required=True)
    edits.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "serve":
        import uvicorn

        from praxiproof.api.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
    elif args.command == "bench":
        result = run_benchmark(args.demo_dir)
        print(json.dumps(result, indent=2))
        if args.skill_md:
            from praxiproof.compiler.benchmark import render_benchmark_md

            args.skill_md.write_text(
                render_benchmark_md(result, "DGX H100 front fan module replacement — PraxiProof demo skill"), encoding="utf-8"
            )
    elif args.command == "build-references":
        from praxiproof.eval.nvidia_sop import build_references

        examples = build_references(args.data, args.videos, args.out, args.per_group)
        print(json.dumps({x.label: list(x.sources) for x in examples}, indent=2))
    elif args.command == "make-edits":
        from praxiproof.eval.nvidia_sop import make_edits

        print("\n".join(str(p) for p in make_edits(args.data, args.video, args.out)))
    elif args.command == "eval-sop":
        from praxiproof.eval.nvidia_sop import evaluate
        from praxiproof.llm import OllamaClient
        from praxiproof.video.backend import get_backend

        settings = load_overrides(get_settings())
        backend = get_backend(settings, OllamaClient(settings.ollama_url, settings.keep_alive))
        print(json.dumps(evaluate(args.data, args.videos, backend, args.out)["summary"], indent=2))
    else:
        from praxiproof.constraints.compiler import compile_requirements
        from praxiproof.document.extract import extract
        from praxiproof.llm import OllamaClient

        settings = load_overrides(get_settings())
        doc = extract(args.manual, source_id="CLI")
        result = compile_requirements(doc, OllamaClient(settings.ollama_url, settings.keep_alive), settings.llm_model, args.procedure)
        print(result.model_dump_json(indent=2, exclude={"evidence"}))


def run_benchmark(demo_dir: Path) -> dict:
    from praxiproof.constraints.engine import evaluate
    from praxiproof.demo import load_observation_fixture, load_reference_requirements
    from praxiproof.eval.metrics import citation_accuracy, verification_accuracy
    from praxiproof.ir.verification import Status, VerificationReport
    from praxiproof.service import observation_with_evidence
    from praxiproof.verifier.evidence import traceability

    requirements, _, manual_evidence, quotes = load_reference_requirements(demo_dir / "requirements" / "dgx-h100-front-fan.json", demo_dir)
    results, totals = {}, {"correct": 0, "compared": 0}
    per_status: dict[str, list[bool]] = {s.value: [] for s in Status}
    for path in sorted((demo_dir / "observations").glob("*.json")):
        fixture, _ = load_observation_fixture(path)
        observation, video_evidence = observation_with_evidence(fixture["observation"], path.stem)
        report = VerificationReport(
            run_id=path.stem,
            manual_id=requirements.source_id,
            video_id=None,
            procedure=requirements.procedure,
            verdicts=evaluate(requirements, observation),
        )
        evidence = {e.evidence_id: e for e in manual_evidence + video_evidence}
        accuracy = verification_accuracy(report, fixture["expected"])
        ratio, issues = traceability(report, evidence)
        results[path.stem] = accuracy | {
            "citation_accuracy": citation_accuracy(report, evidence, quotes),
            "evidence_traceability": round(ratio, 3),
            "traceability_issues": issues,
        }
        actual = {v.rule_id: v.status.value for v in report.verdicts}
        for rule, status in fixture["expected"].items():
            per_status[status].append(actual.get(rule) == status)
            totals["compared"] += 1
            totals["correct"] += actual.get(rule) == status
    summary = {
        "verification_accuracy": round(totals["correct"] / totals["compared"], 3) if totals["compared"] else 0.0,
        **{f"{s.lower()}_recall": round(sum(v) / len(v), 3) for s, v in per_status.items() if v},
    }
    return {"summary": summary, "cases": results}


if __name__ == "__main__":
    main()
