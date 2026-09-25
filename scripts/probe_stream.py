"""Stream one manual-compile request from the configured OpenAI-compatible provider and report the gaps between chunks.

Tells whether a hosted model streams steadily while it works (so a short per-chunk timeout can spot a stalled request
without cutting off a long but healthy generation). Reads the provider settings from the environment.
Usage: python scripts/probe_stream.py <manual file> [--procedure NAME]
"""
import argparse
import json
import time
from pathlib import Path

import httpx

from praxiproof.config import get_settings, load_overrides
from praxiproof.constraints.compiler import OUTPUT_SCHEMA, SYSTEM_PROMPT, _render, select_blocks
from praxiproof.document.extract import extract

ap = argparse.ArgumentParser()
ap.add_argument("manual", type=Path)
ap.add_argument("--procedure")
args = ap.parse_args()
settings = load_overrides(get_settings())
doc = extract(args.manual, source_id="PROBE")
focus = f'Compile only the procedure "{args.procedure}".' if args.procedure else "Compile the main procedure in this text."
payload = {
    "model": settings.llm_model, "temperature": 0, "stream": True,
    "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"{focus}\n\nManual text:\n{_render(select_blocks(doc, args.procedure))}"}],
    "response_format": {"type": "json_schema", "json_schema": {"name": "response", "schema": OUTPUT_SCHEMA, "strict": True}},
}
started, last, gaps, kinds, text = time.time(), time.time(), [], {}, ""
timeout = httpx.Timeout(connect=10, read=120, write=30, pool=10)
with httpx.Client(base_url=settings.openai_base_url.rstrip("/"), headers={"Authorization": f"Bearer {settings.openai_api_key}"}, timeout=timeout) as c:
    with c.stream("POST", "/chat/completions", json=payload) as r:
        print("status", r.status_code, "content-type", r.headers.get("content-type"))
        for line in r.iter_lines():
            if not line.startswith("data:") or line.strip() == "data: [DONE]":
                continue
            now = time.time()
            gaps.append(now - last)
            last = now
            delta = (json.loads(line[5:])["choices"] or [{}])[0].get("delta", {})
            for key in ("reasoning_content", "reasoning", "content", "tool_calls"):
                if delta.get(key):
                    kinds[key] = kinds.get(key, 0) + 1
            text += delta.get("content") or ""
print(f"total {time.time() - started:.0f}s, {len(gaps)} chunks, first chunk after {gaps[0]:.1f}s, largest gap {max(gaps[1:] or [0]):.1f}s, chunk kinds {kinds}")
try:
    print("content is valid JSON with", len(json.loads(text).get("requirements", [])), "requirements")
except json.JSONDecodeError as exc:
    print("content is not valid JSON:", exc)
