from collections.abc import Mapping

from praxiproof.ir.evidence import Evidence
from praxiproof.ir.verification import Status, VerificationReport


def traceability(report: VerificationReport, evidence: Mapping[str, Evidence]) -> tuple[float, list[str]]:
    """Share of verdicts whose cited evidence all resolves to the right source kind, plus the problems found."""
    issues: list[str] = []
    traceable = 0
    for v in report.verdicts:
        problems = []
        if not v.requirement_evidence_ids:
            problems.append("no manual citation")
        for eid in v.requirement_evidence_ids:
            item = evidence.get(eid)
            if item is None or item.source_type != "document" or item.source_id != report.manual_id:
                problems.append(f"manual evidence {eid} missing or from another source")
        if v.status in (Status.PASS, Status.VIOLATION) and v.observed_event_ids and not v.observation_evidence_ids:
            problems.append("verdict relies on video events without video evidence")
        for eid in v.observation_evidence_ids:
            item = evidence.get(eid)
            if item is None or item.source_type != "video":
                problems.append(f"video evidence {eid} missing")
        if problems:
            issues.extend(f"{v.rule_id}: {p}" for p in problems)
        else:
            traceable += 1
    ratio = traceable / len(report.verdicts) if report.verdicts else 1.0
    return ratio, issues
