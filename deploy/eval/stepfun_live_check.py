"""Check the deployed service's text path end to end while the text model is a hosted API (run on the Spark).

Uploads a manual (compile -> rules), then asks the Compliance Agent about an existing violating run, so both the
compile step and the tool-calling agent (including delegation to the RCA agent) go through the configured provider.
Frames are not involved: video understanding stays on the local Ollama.

Usage: uv run python deploy/eval/stepfun_live_check.py [output.json]
"""
import json
import sys
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:8090/api"
MANUAL = Path.home() / "praxiproof/demo/manuals/dgx-h100-front-fan-replacement.html"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "praxiproof-data/eval/stepfun_live.json"

with httpx.Client(timeout=300, trust_env=False) as c:
    settings = c.get(f"{API}/settings").json()
    started = time.time()
    with MANUAL.open("rb") as f:
        manual = c.post(f"{API}/manuals", data={"procedure": "Front Fan Module Replacement"}, files={"file": (MANUAL.name, f, "text/html")}).json()
    while (m := c.get(f"{API}/manuals/{manual['id']}").json())["status"] not in ("ready", "failed"):
        time.sleep(3)
    compile_seconds = round(time.time() - started, 1)

    runs = [r for r in c.get(f"{API}/runs").json() if r.get("status") == "done" and r.get("violations", 0) > 0]
    answers = {}
    for language, question in (("en", "Why did the run fail? Name the root cause."), ("zh", "这次为什么没通过?请说明根因。")):
        t = time.time()
        reply = c.post(f"{API}/agent/ask", json={"question": question, "run_id": runs[0]["id"], "language": language}).json()
        calls = reply.get("tool_calls", [])
        delegated = [c for c in calls if c.get("agent") == "rca"]
        answers[language] = {
            "seconds": round(time.time() - t, 1),
            "compliance_agent_tool_calls": [c["tool"] for c in calls],
            "delegated_to_rca": bool(delegated),
            "rca_tool_calls": [s["tool"] for c in delegated for s in c.get("sub_trace", [])],
            "rca_category": next((c.get("result", {}).get("category") for c in delegated), None),
            "answer_chars": len(reply.get("answer", "")),
            "answer": reply.get("answer", "")[:400],
        }
result = {
    "provider": {k: settings[k] for k in ("llm_provider", "llm_model", "vlm_model", "openai_base_url", "data_flow")},
    "compile": {"manual": m["id"], "status": m["status"], "error": m.get("error"), "rules": (m.get("counts") or {}).get("rules"), "seconds": compile_seconds},
    "agent": answers,
    "run": runs[0]["id"],
}
out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
