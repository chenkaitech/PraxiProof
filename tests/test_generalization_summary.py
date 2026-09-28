from praxiproof.eval.generalization_summary import score


def _event(label, start, end, confidence=1.0):
    return {"label": label, "start": start, "end": end, "confidence": confidence}


def test_a_clean_two_phase_prediction_passes_every_rule_but_the_unseen_one():
    report = {
        "videos": {
            "clean": {
                "predicted": [
                    _event("toy_disassembled", 0, 100),
                    _event("parts_set_aside", 20, 120),
                    _event("toy_reassembled", 150, 250),
                    _event("toy_held_together_confirmed", 250, 260),
                ]
            }
        }
    }
    result = score(report)
    counts = result["videos"]["clean"]["counts"]
    # screws_removed is never observed, so R-001 (MUST_HAVE) and R-010 (BEFORE screws_removed) fail; the rest hold.
    assert counts == {"PASS": 8, "VIOLATION": 2}
    by_rule = {v["rule_id"]: v["status"] for v in result["videos"]["clean"]["verdicts"]}
    assert by_rule["R-001"] == "VIOLATION" and by_rule["R-006"] == "PASS" and by_rule["R-007"] == "PASS"


def test_reassembly_before_disassembly_is_flagged_as_an_order_violation():
    report = {
        "videos": {
            "backwards": {
                "predicted": [
                    _event("toy_reassembled", 0, 50),
                    _event("toy_disassembled", 100, 150),
                    _event("parts_set_aside", 100, 150),
                    _event("toy_held_together_confirmed", 50, 60),
                ]
            }
        }
    }
    by_rule = {v["rule_id"]: v["status"] for v in score(report)["videos"]["backwards"]["verdicts"]}
    assert by_rule["R-006"] == "VIOLATION"  # toy_disassembled no longer precedes toy_reassembled
