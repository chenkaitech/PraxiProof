"""Print a finished run's result and its observed events, marking those the second look re-examined.
Usage: python scripts/show_run_events.py <run id> [--base http://127.0.0.1:8090]"""
import argparse
import json
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--base", default="http://127.0.0.1:8090")
args = ap.parse_args()
run = json.loads(urllib.request.urlopen(f"{args.base}/api/runs/{args.run}", timeout=30).read())
print("result:", run["result"], "| counts:", run["counts"])
for e in run["observation"]["events"]:
    note = e["description"].split("[")[-1].rstrip("]") if "second look" in e["description"] else ""
    print(f"  {e['label']:14s} {e['start']:6.1f}-{e['end']:6.1f}  confidence={e['confidence']:<5}  {note}")
