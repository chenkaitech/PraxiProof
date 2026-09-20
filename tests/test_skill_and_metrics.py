import io
import json
import re
import zipfile

from praxiproof.compiler.agent_skill import build_skill_ir, slugify, write_skill, zip_dir
from praxiproof.constraints.engine import evaluate
from praxiproof.eval.metrics import citation_accuracy, event_detection, temporal_iou, verification_accuracy
from praxiproof.ir.observation import ObservedEvent
from praxiproof.ir.verification import VerificationReport
from praxiproof.service import observation_with_evidence


def _report(reference, observation_fixture, name):
    requirement_set, _, manual_evidence, _ = reference
    fixture, _ = observation_fixture(name)
    observation, video_evidence = observation_with_evidence(fixture["observation"], "V-001")
    report = VerificationReport(
        run_id="V-001", manual_id=requirement_set.source_id, video_id=None, procedure=requirement_set.procedure,
        verdicts=evaluate(requirement_set, observation),
    )
    evidence = {e.evidence_id: e for e in manual_evidence + video_evidence}
    return fixture, observation, report, evidence


def test_skill_package(tmp_path, reference, observation_fixture):
    requirement_set = reference[0]
    _, observation, report, evidence = _report(reference, observation_fixture, "fan_replacement_B")
    skill = build_skill_ir(requirement_set, report, observation)
    assert skill.name == "dgx-h100-front-fan-module-replacement"
    assert [s.event for s in skill.steps] == [
        "bezel_removed", "failed_fan_identified", "new_fan_unpacked", "fan_unlocked",
        "fan_removed", "fan_inserted", "fan_health_verified", "bezel_installed",
    ]

    root = write_skill(skill, requirement_set, report, evidence, tmp_path, {"r-006.jpg": b"jpg"})
    text = (root / "SKILL.md").read_text()
    front = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert front and front.group(1) == root.name
    assert len(json.loads(front.group(2))) <= 1024
    assert "within 30 seconds" in (root / "references" / "evidence.md").read_text()
    assert "## Deviations seen in practice" in text and "R-006" not in text.split("## Deviations")[0]
    assert "_(manual Replacing and Returning the Front Fan Module)_" in text

    cases = json.loads((root / "evals" / "evals.json").read_text())
    assert len(cases) == len(requirement_set.requirements) + 3
    negative = [c for c in cases if c["negative"]]
    assert len(negative) == 3
    assert all(c["rule_id"] is None and not c["must_flag_problem"] for c in negative)
    assert all(not c["negative"] for c in cases if c["rule_id"])

    card = (root / "references" / "skill-card.md").read_text()
    assert "Skill Card" in card and report.run_id in card

    assert (root / "assets" / "r-006.jpg").read_bytes() == b"jpg"

    names = zipfile.ZipFile(io.BytesIO(zip_dir(root))).namelist()
    assert f"{root.name}/SKILL.md" in names
    assert f"{root.name}/references/skill-card.md" in names
    assert f"{root.name}/evals/evals.json" in names


def test_slugify():
    assert slugify("  DGX H100: Front Fan / Module  ") == "dgx-h100-front-fan-module"
    assert slugify("!!!") == "procedure"
    assert len(slugify("a" * 100)) == 64


def test_metrics(reference, observation_fixture):
    fixture, _, report, evidence = _report(reference, observation_fixture, "fan_replacement_C")
    assert verification_accuracy(report, fixture["expected"])["accuracy"] == 1.0
    assert verification_accuracy(report, fixture["expected"])["violation_recall"] == 1.0
    assert citation_accuracy(report, evidence, reference[3]) == 1.0

    assert temporal_iou(0, 10, 5, 15) == 5 / 15
    assert temporal_iou(0, 1, 2, 3) == 0.0
    gold = [ObservedEvent(event_id="g1", label="a", start=0, end=10, confidence=1), ObservedEvent(event_id="g2", label="b", start=20, end=30, confidence=1)]
    predicted = [ObservedEvent(event_id="p1", label="a", start=1, end=9, confidence=0.9), ObservedEvent(event_id="p2", label="b", start=50, end=60, confidence=0.9)]
    scores = event_detection(predicted, gold)
    assert (scores["precision"], scores["recall"], scores["mean_iou"]) == (0.5, 0.5, 0.8)
