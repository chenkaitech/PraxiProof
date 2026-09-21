"""Direct-VLM baseline vs PraxiProof on the six edited SOP recordings (run on the Spark).

Baseline: gemma4:31b sees the manual text + 16 timestamped frames and answers "is this compliant?", asked three
times with different frame sampling. PraxiProof: the deployed /api/pipelines flow (DDM-Net + VLM -> deterministic
engine). Results are written to ~/praxiproof-data/eval/baseline_vs_praxiproof.json (copied to docs/eval/).

Needs the six edited recordings (`praxiproof make-edits`) in ~/datasets/sop-server-fan/edited and the service running.
Usage (on the Spark, from ~/praxiproof):  uv run python deploy/eval/baseline_vs_praxiproof.py
"""
import json
import time
import urllib.request
import uuid
from pathlib import Path

from praxiproof.llm import OllamaClient
from praxiproof.video.frames import frame_at, probe

HOME = Path.home()
EDITED = HOME / "datasets/sop-server-fan/edited"
OUT = HOME / "praxiproof-data/eval/baseline_vs_praxiproof.json"
API = "http://127.0.0.1:8090/api"
MANUAL = (HOME / "praxiproof/demo/manuals/server-fan-psu-cover-installation.md").read_text()
TRUTH = {"compliant": "Compliant", "missing_cover": "Missing Step", "psu_before_fans": "Order Violation"}
VIDEOS = [f"Install_{n}_{k}" for n in (12, 13) for k in TRUTH]
# already run by the earlier clean_pipelines.sh (manual MAN-004)
EXISTING = {"Install_13_compliant": "PL-016", "Install_13_missing_cover": "PL-018", "Install_13_psu_before_fans": "PL-020"}

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["compliant", "missing_step", "wrong_order"]},
        "explanation": {"type": "string"},
    },
    "required": ["verdict", "explanation"],
}
LABEL = {"compliant": "Compliant", "missing_step": "Missing Step", "wrong_order": "Order Violation"}
llm = OllamaClient("http://127.0.0.1:11434", "10m")


def baseline(video: str, phase: float) -> dict:
    path = EDITED / f"{video}.mp4"
    dur = probe(path).duration
    step = dur / 16
    times = [round(step * (i + phase), 2) for i in range(16)]
    frames = [frame_at(path, t, 512) for t in times]
    listing = "\n".join(f"Frame {i} at {t:.1f}s" for i, t in enumerate(times, 1))
    r = llm.chat_json(
        "gemma4:31b",
        [{"role": "user", "content": (
            f"This is the official procedure:\n{MANUAL}\n\nThe images are frames, in time order, from a video of a technician "
            f"carrying it out.\n{listing}\n\nDid the technician follow the procedure? Answer compliant, missing_step "
            "(a required part was never installed) or wrong_order (parts were installed in the wrong order).")}],
        SCHEMA, images=frames, think=False,
    )
    return {"phase": phase, "verdict": r["verdict"], "label": LABEL[r["verdict"]], "explanation": r["explanation"][:300]}


def post_pipeline(video: str) -> str:
    bd = uuid.uuid4().hex
    data = (f'--{bd}\r\nContent-Disposition: form-data; name="manual_id"\r\n\r\nMAN-004\r\n'
            f'--{bd}\r\nContent-Disposition: form-data; name="video"; filename="{video}.mp4"\r\nContent-Type: video/mp4\r\n\r\n').encode()
    data += (EDITED / f"{video}.mp4").read_bytes() + f"\r\n--{bd}--\r\n".encode()
    req = urllib.request.Request(f"{API}/pipelines", data=data, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["id"]


def wait(pid: str) -> dict:
    while True:
        d = json.loads(urllib.request.urlopen(f"{API}/pipelines/{pid}", timeout=60).read())
        if d["status"] in ("done", "failed"):
            return d
        time.sleep(15)


results = {"truth": TRUTH, "videos": {}}
for v in VIDEOS:
    kind = v.split("_", 2)[2]
    results["videos"][v] = {"truth": TRUTH[kind], "baseline": [baseline(v, p) for p in (0.25, 0.5, 0.75)]}
    print("baseline", v, [b["label"] for b in results["videos"][v]["baseline"]], flush=True)
    OUT.write_text(json.dumps(results, indent=2))

for v in VIDEOS:
    pid = EXISTING.get(v) or post_pipeline(v)
    d = wait(pid)
    results["videos"][v]["praxiproof"] = {"pipeline": pid, "status": d["status"], "result": d.get("result")}
    print("praxiproof", v, pid, d["status"], d.get("result"), flush=True)
    OUT.write_text(json.dumps(results, indent=2))
print("DONE", flush=True)
