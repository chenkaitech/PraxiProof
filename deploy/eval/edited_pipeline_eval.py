"""Run the six edited recordings through the deployed pipeline and compare each verdict category with the known truth.

The recordings are the ones `praxiproof make-edits` builds (compliant / missing cover / PSU before the fans) from
Install_12 and Install_13. The pipeline runs exactly as deployed, i.e. with whatever the service is configured for
(fragment merging, second look, ...). Sequential; about 9 minutes per recording.

Usage (on the Spark):  uv run python deploy/eval/edited_pipeline_eval.py [MAN-004] [output.json]
"""
import json
import sys
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:8090/api"
EDITED = Path.home() / "datasets/sop-server-fan/edited"
TRUTH = {"compliant": "PASS", "missing_cover": "Missing Step", "psu_before_fans": "Order Violation"}
manual_id = sys.argv[1] if len(sys.argv) > 1 else "MAN-004"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "praxiproof-data/eval/edited_pipeline.json"

rows = []
with httpx.Client(timeout=120, trust_env=False) as client:
    settings = client.get(f"{API}/settings").json()
    for path in sorted(EDITED.glob("Install_1[23]_*.mp4")):
        edit = path.stem.split("_", 2)[2]
        started = time.time()
        with path.open("rb") as f:
            pipeline = client.post(f"{API}/pipelines", data={"manual_id": manual_id}, files={"video": (path.name, f, "video/mp4")}).json()
        while (state := client.get(f"{API}/pipelines/{pipeline['id']}").json())["status"] not in ("done", "failed"):
            time.sleep(15)
        run = client.get(f"{API}/runs/{state['run_id']}").json() if state.get("run_id") else {}
        events = run.get("observation", {}).get("events", [])
        rows.append({
            "video": path.stem, "truth": TRUTH[edit], "result": run.get("result") or state["status"], "run": state.get("run_id"),
            "counts": run.get("counts"), "seconds": round(time.time() - started),
            "events": len(events), "merged_events": sum("merged" in e["description"] for e in events),
            "second_looked": sum("second look" in e["description"] for e in events),
        })
        print(rows[-1], flush=True)

violating = [r for r in rows if r["truth"] != "PASS"]
summary = {
    "settings": {k: settings[k] for k in ("video_backend", "second_look", "min_confidence")},
    "matches_truth": sum(r["result"] == r["truth"] for r in rows),
    "recordings": len(rows),
    "violating_wrongly_cleared": sum(r["result"] == "PASS" for r in violating),
    "compliant_cleared": sum(r["result"] == "PASS" for r in rows if r["truth"] == "PASS"),
    "rows": rows,
}
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "rows"}))
