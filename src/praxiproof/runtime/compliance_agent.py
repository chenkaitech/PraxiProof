import json
import re
from collections.abc import Callable
from typing import Any

from praxiproof.service import PraxiProof
from praxiproof.store import NotFound

SYSTEM_PROMPT = (
    "You are the PraxiProof Compliance Agent. You answer questions about whether an operation followed its "
    "official procedure. Use the tools to look up the manual, the verification report, evidence and the verified "
    "skill. For any question about whether a rule was followed, call get_verification_report first and report its "
    "status and measured values exactly; never recompute times or overrule a verdict yourself. Every claim about a "
    "rule must cite the manual location (use show_evidence for page and quote), and every claim about what happened "
    "must cite the video time range. If a rule is UNVERIFIED or INSUFFICIENT_EVIDENCE, say so plainly instead of guessing."
)


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_STRING = {"type": "string"}

TOOLS = [
    _tool("search_manual", "Search the manual text for passages about a topic.", {"manual_id": _STRING, "query": _STRING}, ["manual_id", "query"]),
    _tool("inspect_video", "List the events observed in the video of a verification run, with time ranges.", {"run_id": _STRING}, ["run_id"]),
    _tool("get_verification_report", "Get every rule verdict for a verification run.", {"run_id": _STRING}, ["run_id"]),
    _tool("show_evidence", "Show the full evidence record (manual quote or video segment) for an evidence id.", {"evidence_id": _STRING}, ["evidence_id"]),
    _tool("load_verified_skill", "Load the SKILL.md compiled from a verification run, if one exists.", {"run_id": _STRING}, ["run_id"]),
]


class ComplianceAgent:
    def __init__(self, app: PraxiProof, max_steps: int = 6):
        self.app = app
        self.max_steps = max_steps
        self._handlers: dict[str, Callable[..., Any]] = {
            "search_manual": self.search_manual,
            "inspect_video": self.inspect_video,
            "get_verification_report": self.get_verification_report,
            "show_evidence": self.show_evidence,
            "load_verified_skill": self.load_verified_skill,
        }

    def ask(self, question: str, run_id: str | None = None) -> dict[str, Any]:
        context = ""
        if run_id:
            run = self.app.store.get("runs", run_id)
            context = f"\nCurrent run: {run_id} (manual {run['manual_id']}, video '{run['video_name']}')."
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + context},
            {"role": "user", "content": question},
        ]
        trace = []
        for _ in range(self.max_steps):
            reply = self.app.llm.chat(self.app.settings.llm_model, messages, tools=TOOLS)
            messages.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                return {"answer": reply.get("content", ""), "tool_calls": trace}
            for call in calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments") or {}
                if isinstance(arguments, str):
                    arguments = json.loads(arguments or "{}")
                result = self._call(name, arguments)
                trace.append({"tool": name, "arguments": arguments})
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)[:12000]})
        return {"answer": "I could not finish within the tool-call limit. Try a narrower question.", "tool_calls": trace}

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            return handler(**arguments)
        except (NotFound, ValueError, TypeError, OSError) as exc:
            return {"error": str(exc)}

    def search_manual(self, manual_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        doc = self.app.document(manual_id)
        terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
        scored = []
        for block in doc.blocks:
            text = block.text.lower()
            score = sum(text.count(t) for t in terms) + sum(2 for t in terms if t in (block.section or "").lower())
            if score:
                scored.append((score, block))
        scored.sort(key=lambda s: (-s[0], s[1].index))
        return [
            {"citation": doc.evidence_for(b.index).citation(), "section": b.section, "text": b.text}
            for _, b in scored[:limit]
        ]

    def inspect_video(self, run_id: str) -> list[dict[str, Any]]:
        run = self.app.store.get("runs", run_id)
        events = (run.get("observation") or {}).get("events", [])
        return [
            {"label": e["label"], "start": e["start"], "end": e["end"], "confidence": e["confidence"], "evidence_id": e.get("evidence_id")}
            for e in events
        ]

    def get_verification_report(self, run_id: str) -> list[dict[str, Any]]:
        report = self.app.report(run_id)
        return [
            {
                "rule_id": v.rule_id,
                "statement": v.statement,
                "constraint": v.constraint.signature(),
                "status": v.status,
                "reason": v.reason,
                "measured": v.measured,
                "manual_evidence": v.requirement_evidence_ids,
                "video_evidence": v.observation_evidence_ids,
                "review": v.review,
            }
            for v in report.verdicts
        ]

    def show_evidence(self, evidence_id: str) -> dict[str, Any]:
        item = self.app.store.evidence([evidence_id]).get(evidence_id)
        if item is None:
            raise ValueError(f"evidence {evidence_id} not found")
        return item.model_dump(mode="json") | {"citation": item.citation()}

    def load_verified_skill(self, run_id: str) -> dict[str, Any]:
        skill = next((s for s in self.app.store.list("skills") if s["run_id"] == run_id), None)
        if skill is None:
            return {"error": f"no skill compiled for {run_id} yet"}
        return {"skill_id": skill["id"], "name": skill["name"], "skill_md": self.app.skill_markdown(skill["id"])}
