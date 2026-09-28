"""Compile a manual with the configured provider and show which candidate rules were accepted or rejected, and why.

Useful when a hosted model produces manuals that fail to compile: the service only keeps the outcome, this prints the
rejection reasons. Uses the same settings as the service (env vars and data/settings.json).
Usage: python scripts/diagnose_compile.py <manual file> [--procedure NAME] [--runs N]
"""
import argparse
import time
from collections import Counter
from pathlib import Path

from praxiproof.config import get_settings, load_overrides
from praxiproof.constraints.compiler import compile_requirements
from praxiproof.document.extract import extract
from praxiproof.llm import build_llm

ap = argparse.ArgumentParser()
ap.add_argument("manual", type=Path)
ap.add_argument("--procedure")
ap.add_argument("--runs", type=int, default=1)
ap.add_argument("--events", action="store_true", help="also print the compiled event vocabulary")
args = ap.parse_args()

settings = load_overrides(get_settings())
llm = build_llm(settings)
doc = extract(args.manual, source_id="DIAG")
print(f"provider={settings.llm_provider} model={settings.llm_model}")
for i in range(1, args.runs + 1):
    started = time.time()
    try:
        result = compile_requirements(doc, llm, settings.llm_model, args.procedure)
    except Exception as exc:  # noqa: BLE001 - a diagnostic should report any failure, not crash on it
        print(f"run {i}: {type(exc).__name__}: {str(exc)[:200]} ({time.time() - started:.0f}s)")
        continue
    reasons = Counter(r.error.split(":")[0][:70] for r in result.rejected)
    print(f"run {i}: {len(result.requirement_set.requirements)} rules, {len(result.rejected)} rejected, {result.repaired} repaired ({time.time() - started:.0f}s)")
    if args.events:
        print(f"    events: {[e.label for e in result.requirement_set.events]}")
    for reason, n in reasons.most_common(5):
        print(f"    {n} x {reason}")
    for r in result.rejected[:2]:
        print(f"    e.g. {r.error[:160]} | {str(r.item)[:160]}")
