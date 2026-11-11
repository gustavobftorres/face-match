import json

from app.evaluation import DecisionPolicy, EvaluationPlan, load_manifest
from test_holdout import DistanceAdapter, holdout


def test_evaluate_baseline_runs_each_holdout_scan_once_and_emits_only_baseline(tmp_path):
    from app.evaluation import evaluate_baseline

    policy = DecisionPolicy("production_distance")
    plan = EvaluationPlan(holdout(tmp_path), tmp_path / "run", baseline=policy,
                          candidate=policy, mode="test_only")
    adapter = DistanceAdapter()
    run = evaluate_baseline(plan, adapter)
    assert adapter.seen == ["positive", "boundary", "negative"]
    assert set(run.systems) == {"baseline"}
    assert set(run.provenance["adapters"]) == {"baseline"}
    assert set(run.provenance["decisions"]) == {"baseline"}
    assert run.evaluation_mode == "test_only"
    assert run.systems["baseline"].threshold == -0.6
    metrics = run.systems["baseline"].metrics
    assert (metrics.tp, metrics.fn, metrics.fp, metrics.tn) == (1, 1, 0, 1)
    for name in ("run.json", "metrics.json"):
        document = json.loads((tmp_path / "run" / name).read_text())
        assert set(document["systems"]) == {"baseline"}
        assert document["evaluation_mode"] == "test_only"
    thresholds = json.loads((tmp_path / "run/threshold.json").read_text())
    assert set(thresholds) == {"baseline"}
    assert thresholds["baseline"]["calibrated_on"] is None
    for name in ("decisions.ndjson", "timings.ndjson"):
        rows = [json.loads(line) for line in (tmp_path / "run" / name).read_text().splitlines()]
        assert len(rows) == 3
        assert {row["system"] for row in rows} == {"baseline"}
        assert {row["split"] for row in rows} == {"test"}


def test_evaluate_baseline_preserves_default_calibration_mode(tmp_path):
    from app.evaluation import evaluate_baseline
    from test_cli import LegacySyntheticAdapter, cli_files

    cli_files(tmp_path)
    plan = EvaluationPlan(load_manifest(tmp_path / "manifest.toml"), tmp_path / "run")
    run = evaluate_baseline(plan, LegacySyntheticAdapter("baseline"))
    baseline = run.systems["baseline"]
    assert run.evaluation_mode == "calibration_test"
    assert baseline.threshold == 0.4
    assert baseline.decision_policy.policy == "calibrate_f1"
    assert [d.split for d in baseline.decisions] == ["calibration", "test"]
    thresholds = json.loads((tmp_path / "run/threshold.json").read_text())
    assert thresholds["baseline"]["calibrated_on"] == "calibration"
