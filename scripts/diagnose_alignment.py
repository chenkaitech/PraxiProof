"""Show how the step matcher maps a run's observed labels onto the manual's steps, with the configured text model and
optionally with a local Ollama model for comparison. Reads the run and manual from the service's data directory.

Usage: python scripts/diagnose_alignment.py <run id> [--ollama-model qwen3.6:35b-a3b-q8_0]
       python scripts/diagnose_alignment.py <run id> --models step-3.5-flash,step-3.7-flash --repeat 3   # compare hosted models
"""
import argparse
import json

from praxiproof.config import get_settings, load_overrides
from praxiproof.ir.requirement import EventDef, RequirementSet
from praxiproof.llm import OllamaClient, build_llm
from praxiproof.service import observation_with_evidence
from praxiproof.store import Store
from praxiproof.verifier.aligner import llm_matcher

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--ollama-model")
ap.add_argument("--models", help="comma-separated model names to try on the configured provider")
ap.add_argument("--repeat", type=int, default=1)
args = ap.parse_args()

settings = load_overrides(get_settings())
store = Store(settings.data_dir / "praxiproof.db")
run = store.get("runs", args.run)
vocabulary = RequirementSet.model_validate(store.get("manuals", run["manual_id"])["requirement_set"]).events
observation, _ = observation_with_evidence(run["input_observation"], args.run) if run.get("input_observation") else (None, None)
if observation is None:
    raise SystemExit("this run has no stored input observation (it came from a video); use a demo-observation run")
known = {e.label for e in vocabulary}
pending = {}
for e in observation.events:
    if e.label not in known:
        pending.setdefault(e.label, EventDef.model_construct(label=e.label, description=e.description or e.label))
print("manual steps:", {v.label: v.description[:70] for v in vocabulary})
print("observed, not in the manual:", {p.label: p.description[:70] for p in pending.values()})

def show(name, llm, model):
    try:
        print(f"{name} ({model}):", json.dumps(llm_matcher(llm, model)(list(pending.values()), vocabulary), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 - a diagnostic reports any failure
        print(f"{name} ({model}): {type(exc).__name__}: {str(exc)[:160]}")

llm = build_llm(settings)
for model in (args.models.split(",") if args.models else [settings.llm_model]):
    for i in range(args.repeat):
        show(f"configured #{i + 1}", llm, model)
if args.ollama_model:
    show("ollama", OllamaClient(settings.ollama_url, settings.keep_alive), args.ollama_model)
