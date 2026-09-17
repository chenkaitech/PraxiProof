from collections.abc import Mapping

from praxiproof.ir.evidence import Evidence
from praxiproof.ir.observation import ObservedEvent
from praxiproof.ir.verification import Status, VerificationReport


def temporal_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return intersection / union if union > 0 else float(a_start == b_start and a_end == b_end)


def _prf(tp: int, predicted: int, expected: int) -> dict[str, float]:
    precision = tp / predicted if predicted else 1.0 if not expected else 0.0
    recall = tp / expected if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def match_events(
    predicted: list[ObservedEvent], gold: list[ObservedEvent], iou_threshold: float = 0.3
) -> list[tuple[ObservedEvent, ObservedEvent, float]]:
    unused = list(gold)
    matches = []
    for event in sorted(predicted, key=lambda e: -e.confidence):
        scored = [(temporal_iou(event.start, event.end, g.start, g.end), g) for g in unused if g.label == event.label]
        if not scored:
            continue
        iou, match = max(scored, key=lambda s: s[0])
        if iou >= iou_threshold:
            unused.remove(match)
            matches.append((event, match, iou))
    return matches


def event_detection(
    predicted: list[ObservedEvent], gold: list[ObservedEvent], iou_threshold: float = 0.3
) -> dict[str, float]:
    matches = match_events(predicted, gold, iou_threshold)
    ious = [iou for _, _, iou in matches]
    return _prf(len(matches), len(predicted), len(gold)) | {"mean_iou": round(sum(ious) / len(ious), 3) if ious else 0.0}


def boundary_errors(matches: list[tuple[ObservedEvent, ObservedEvent, float]]) -> dict[str, float | None]:
    if not matches:
        return {"mean_start_error_s": None, "mean_end_error_s": None}
    return {
        "mean_start_error_s": round(sum(abs(p.start - g.start) for p, g, _ in matches) / len(matches), 2),
        "mean_end_error_s": round(sum(abs(p.end - g.end) for p, g, _ in matches) / len(matches), 2),
    }


def sequence_similarity(predicted: list[str], gold: list[str]) -> float:
    if not predicted and not gold:
        return 1.0
    lcs = [[0] * (len(gold) + 1) for _ in range(len(predicted) + 1)]
    for i, p in enumerate(predicted):
        for j, g in enumerate(gold):
            lcs[i + 1][j + 1] = lcs[i][j] + 1 if p == g else max(lcs[i][j + 1], lcs[i + 1][j])
    return round(lcs[-1][-1] / max(len(predicted), len(gold)), 3)


def requirement_matching(predicted: set[str], gold: set[str]) -> dict[str, float]:
    return _prf(len(predicted & gold), len(predicted), len(gold))


def verification_accuracy(report: VerificationReport, expected: Mapping[str, str]) -> dict[str, float]:
    actual = {v.rule_id: v.status.value for v in report.verdicts}
    compared = [rule for rule in expected if rule in actual]
    correct = sum(actual[r] == expected[r] for r in compared)
    result = {"accuracy": round(correct / len(compared), 3) if compared else 0.0, "rules_compared": len(compared)}
    for status in Status:
        wanted = [r for r in compared if expected[r] == status.value]
        if wanted:
            hits = sum(actual[r] == status.value for r in wanted)
            result[f"{status.value.lower()}_recall"] = round(hits / len(wanted), 3)
    return result


def citation_accuracy(
    report: VerificationReport, evidence: Mapping[str, Evidence], expected_quotes: Mapping[str, str]
) -> float:
    by_rule = {v.rule_id: v for v in report.verdicts}
    checked = [rule for rule in expected_quotes if rule in by_rule]
    if not checked:
        return 0.0
    hits = 0
    for rule in checked:
        texts = [(evidence[e].text or "").lower() for e in by_rule[rule].requirement_evidence_ids if e in evidence]
        hits += any(expected_quotes[rule].lower() in t for t in texts)
    return round(hits / len(checked), 3)
