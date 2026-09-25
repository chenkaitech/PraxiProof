import json

from praxiproof.eval.cv_summary import summarize


def _video(gold, predicted, tp, seq=0.9, seconds=100):
    return {"gold_events": gold, "predicted_events": predicted, "matched@0.3": tp, "sequence_similarity": seq, "seconds": seconds}


def _write(path, videos):
    path.write_text(json.dumps({"summary": {"videos": len(videos)}, "videos": videos}))


def test_pooled_metrics_ci_and_untouched_subset(tmp_path):
    # 4 recordings across 2 folds; Install_12 is the "tuned-on" one and must drop out of the untouched subset.
    _write(tmp_path / "fold1.json", {"Install_1": _video(9, 9, 9), "Install_12": _video(9, 9, 9)})
    _write(tmp_path / "fold2.json", {"Install_3": _video(9, 10, 8), "Install_4": _video(9, 8, 6)})
    (tmp_path / "ckpt_fold1.txt").write_text("fold1: epoch_epoch=001-val/f1_score=0.816.ckpt")
    _write(tmp_path / "local_vlm_all12.json", {n: _video(9, 8, 4) for n in ("Install_1", "Install_12", "Install_3", "Install_4")})

    s = summarize(tmp_path)

    assert s["protocol"]["recordings"] == 4 and s["protocol"]["checkpoints"]["fold1"].endswith("0.816.ckpt")
    allv, untouched = s["ddm_vlm_cv"]["all"], s["ddm_vlm_cv"]["untouched"]
    assert (allv["recordings"], allv["gold_events"]) == (4, 36)
    assert (untouched["recordings"], untouched["gold_events"]) == (3, 27)
    # pooled, not averaged per recording: tp=32 of 36 gold, 36 predicted
    assert allv["recall"] == round(32 / 36, 3) and allv["precision"] == round(32 / 36, 3)
    lo, hi = allv["f1_ci95"]
    assert lo <= allv["f1"] <= hi
    assert s["local_vlm"]["all"]["f1"] < allv["f1"]
    diff = s["paired_f1_difference"]["all"]
    assert diff["difference"] > 0 and diff["ci95"][0] > 0 and diff["recordings"] == 4
    assert [v["video"] for v in s["per_video"]] == ["Install_1", "Install_3", "Install_4", "Install_12"]


def test_unfinished_folds_and_missing_baseline_are_left_out(tmp_path):
    _write(tmp_path / "fold1.json", {"Install_1": _video(9, 9, 9)})
    (tmp_path / "fold2.json").write_text(json.dumps({"videos": {"Install_3": _video(9, 9, 9)}}))  # no summary: still running
    s = summarize(tmp_path)
    assert s["protocol"]["recordings"] == 1 and "local_vlm" not in s
    assert s["per_video"][0]["local_vlm_f1"] is None


def test_evaluation_api_exposes_the_cv_summary_when_present(tmp_path):
    from praxiproof.evaluation import load_evaluation

    assert load_evaluation(tmp_path)["cross_validation"] is None
    (tmp_path / "cv_summary.json").write_text(json.dumps({"protocol": {"recordings": 12}}))
    assert load_evaluation(tmp_path)["cross_validation"]["protocol"]["recordings"] == 12


def test_a_recording_the_pipeline_clears_counts_as_cleared(tmp_path):
    from praxiproof.evaluation import load_evaluation

    def entry(truth, result):
        return {"truth": truth, "baseline": [{"label": "Compliant"}] * 3, "praxiproof": {"result": result}}

    (tmp_path / "baseline_vs_praxiproof.json").write_text(json.dumps({"videos": {"a": entry("Compliant", "PASS"), "b": entry("Compliant", "Needs Evidence")}}))
    assert load_evaluation(tmp_path)["baseline"]["compliant"]["praxiproof_cleared"] == 1


def test_evaluation_api_exposes_the_second_look_results(tmp_path):
    from praxiproof.evaluation import load_evaluation

    (tmp_path / "second_look.json").write_text(json.dumps({"cross_validation_recordings": {"weak_events": 9}}))
    assert load_evaluation(tmp_path)["second_look"]["cross_validation_recordings"]["weak_events"] == 9
    assert load_evaluation(tmp_path / "missing")["second_look"] is None


def test_evaluation_api_exposes_the_fragment_merge_results(tmp_path):
    from praxiproof.evaluation import load_evaluation

    (tmp_path / "fragment_merge.json").write_text(json.dumps({"tolerance": 1.2}))
    assert load_evaluation(tmp_path)["fragment_merge"] == {"tolerance": 1.2}
