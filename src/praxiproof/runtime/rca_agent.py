import json
from typing import Any

from praxiproof.ir.verification import Status
from praxiproof.runtime.tool import STRING, tool, tool_message
from praxiproof.service import PraxiProof
from praxiproof.store import NotFound

SYSTEM_PROMPT = (
    "You are the PraxiProof Root Cause Analysis agent. A calling agent has delegated you a single "
    "failing rule verdict and wants to know WHY it failed, using the raw observation and alignment "
    "data behind the verdict — not just its rendered reason text. Call the tools before deciding; "
    "never classify from the reason text alone.\n\n"
    "Classify into exactly one category:\n"
    "- VIDEO_GAP: no event resembling this step appears anywhere in the observation, confident or weak.\n"
    "- LOW_CONFIDENCE: a matching event exists but its confidence is below the run's verification "
    "threshold — a borderline VLM call, not a clear miss.\n"
    "- LABEL_MISMATCH: an event exists under a raw_label that the alignment step marked 'unmatched' or "
    "mapped to a different step, so it never reached this rule's vocabulary label.\n"
    "- BOUNDARY_UNCERTAINTY: a timing rule was exceeded by a margin no larger than the event's "
    "time_uncertainty.\n"
    "- GENUINE_VIOLATION: none of the above apply; the step really was skipped, out of order, or too slow.\n\n"
    "Your final message must be exactly one line starting with 'RCA_RESULT:' followed by a single-line "
    "JSON object with keys category, confidence (low/medium/high), explanation, recommendation — "
    "nothing else, no other text before or after it."
)

TOOLS = [
    tool(
        "get_verdict_detail",
        "Full detail for one rule's verdict in this run: status, reason code, measured values, and which "
        "observed events (if any) were cited. Defaults to the rule under analysis; pass rule_id to inspect "
        "a related rule instead.",
        {"rule_id": STRING},
        [],
    ),
    tool(
        "get_raw_observation",
        "Every observed event for this run, including ones below the confidence threshold, with raw_label "
        "(the label before alignment) and time_uncertainty.",
        {},
        [],
    ),
    tool(
        "get_alignment",
        "How each observed raw label was mapped — or failed to map — onto the procedure's vocabulary.",
        {},
        [],
    ),
    tool("show_evidence", "Show the full evidence record for an evidence id.", {"evidence_id": STRING}, ["evidence_id"]),
]


class RCAAgent:
    """A specialist sub-agent the ComplianceAgent delegates to for "why did this fail" questions.
    It gets deeper, rawer tools than ComplianceAgent (unfiltered observation, alignment records) and
    a strict machine-parsed return contract, mirroring how NVIDIA's sop-rca-plugin is delegated as a
    sub-agent rather than hand-authored inline."""

    def __init__(self, app: PraxiProof, max_steps: int = 6):
        self.app = app
        self.max_steps = max_steps

    def analyze(self, run_id: str, rule_id: str) -> dict[str, Any]:
        report = self.app.report(run_id)
        verdict = next((v for v in report.verdicts if v.rule_id == rule_id), None)
        if verdict is None:
            return {"status": "failed", "error": f"no verdict for rule {rule_id} in run {run_id}"}
        if verdict.status == Status.PASS:
            return {
                "status": "ok",
                "category": "NOT_APPLICABLE",
                "confidence": "high",
                "explanation": f"{rule_id} is PASS; there is nothing to analyze.",
                "recommendation": "",
            }

        handlers = {
            "get_verdict_detail": lambda rule_id=rule_id: self._verdict_detail(run_id, rule_id),
            "get_raw_observation": lambda: self._raw_observation(run_id),
            "get_alignment": lambda: self.app.report(run_id).alignment,
            "show_evidence": self.show_evidence,
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyze run {run_id}, rule {rule_id} (status {verdict.status}: {verdict.reason}). "
                    f"This run's verification confidence threshold is {self.app.settings.min_confidence}."
                ),
            },
        ]
        for _ in range(self.max_steps):
            reply = self.app.llm.chat(self.app.settings.llm_model, messages, tools=TOOLS)
            messages.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                return self._parse(reply.get("content", ""))
            for call in calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments") or {}
                if isinstance(arguments, str):
                    arguments = json.loads(arguments or "{}")
                result = self._call(handlers, name, arguments)
                messages.append(tool_message(call, name, result))
        return {"status": "failed", "error": "root cause analysis did not conclude within the tool-call limit"}

    def _call(self, handlers: dict[str, Any], name: str, arguments: dict[str, Any]) -> Any:
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            return handler(**arguments)
        except (NotFound, ValueError, TypeError, OSError) as exc:
            return {"error": str(exc)}

    def _verdict_detail(self, run_id: str, rule_id: str) -> dict[str, Any]:
        report = self.app.report(run_id)
        v = next((v for v in report.verdicts if v.rule_id == rule_id), None)
        if v is None:
            raise ValueError(f"no verdict for rule {rule_id} in run {run_id}")
        return {
            "rule_id": v.rule_id,
            "status": v.status,
            "reason": v.reason,
            "reason_code": v.reason_code,
            "reason_params": v.reason_params,
            "measured": v.measured,
            "constraint": v.constraint.signature(),
            "category": v.category,
            "severity": v.severity,
            "observed_event_ids": v.observed_event_ids,
            "requirement_evidence_ids": v.requirement_evidence_ids,
            "observation_evidence_ids": v.observation_evidence_ids,
        }

    def _raw_observation(self, run_id: str) -> list[dict[str, Any]]:
        run = self.app.store.get("runs", run_id)
        events = (run.get("observation") or {}).get("events", [])
        return [
            {
                "event_id": e["event_id"],
                "label": e["label"],
                "raw_label": e.get("raw_label"),
                "start": e["start"],
                "end": e["end"],
                "time_uncertainty": e.get("time_uncertainty", 0.0),
                "confidence": e["confidence"],
            }
            for e in events
        ]

    def show_evidence(self, evidence_id: str) -> dict[str, Any]:
        item = self.app.store.evidence([evidence_id]).get(evidence_id)
        if item is None:
            raise ValueError(f"evidence {evidence_id} not found")
        return item.model_dump(mode="json") | {"citation": item.citation()}

    def _parse(self, content: str) -> dict[str, Any]:
        marker = "RCA_RESULT:"
        idx = content.find(marker)
        if idx == -1:
            return {"status": "failed", "error": "agent did not return an RCA_RESULT block", "raw": content[:2000]}
        try:
            payload = json.loads(content[idx + len(marker) :].strip())
        except json.JSONDecodeError:
            return {"status": "failed", "error": "RCA_RESULT block was not valid JSON", "raw": content[idx:2000]}
        return {"status": "ok"} | {k: payload.get(k) for k in ("category", "confidence", "explanation", "recommendation")}
