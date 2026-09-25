"""Replay the Compliance Agent's first model turn several times against the configured OpenAI-compatible provider and
show what each streamed reply consists of (answer text, reasoning text, tool calls, finish reason).

For diagnosing replies that come back with no usable content. Usage: python scripts/probe_agent_turn.py [--runs N]
"""
import argparse
import json

import httpx

from praxiproof.config import get_settings, load_overrides
from praxiproof.runtime.compliance_agent import SYSTEM_PROMPT, TOOLS

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=10)
ap.add_argument("--run-id", default="V-029")
args = ap.parse_args()
settings = load_overrides(get_settings())
payload = {
    "model": settings.llm_model, "temperature": 0, "stream": True, "tools": TOOLS,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT + f"\nCurrent run: {args.run_id}."},
        {"role": "user", "content": "Why did the run fail? Name the root cause."},
    ],
}
with httpx.Client(base_url=settings.openai_base_url.rstrip("/"), headers={"Authorization": f"Bearer {settings.openai_api_key}"}, timeout=httpx.Timeout(10, read=90)) as c:
    for i in range(1, args.runs + 1):
        content = reasoning = ""
        calls, finish, usage = 0, None, None
        with c.stream("POST", "/chat/completions", json=payload) as r:
            for line in r.iter_lines():
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                event = json.loads(line[5:])
                usage = event.get("usage") or usage
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content += delta.get("content") or ""
                    reasoning += delta.get("reasoning_content") or ""
                    calls += len(delta.get("tool_calls") or [])
                    finish = choice.get("finish_reason") or finish
        print(f"{i}: content={len(content)} reasoning={len(reasoning)} tool_call_deltas={calls} finish={finish} usage={usage}", flush=True)
