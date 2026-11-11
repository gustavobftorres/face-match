import json
from dataclasses import replace

import pytest

from app.evaluation import (
    DecisionPolicy, EvaluationManifest, EvaluationPlan, FaceScore,
    ReferenceImage, Scan, SearchResult, compare, load_manifest,
)
from app.evaluation.manifest import ManifestError
from app.evaluation.manifest import validate_manifest


def holdout(tmp_path):
    for name in ("reference", "positive", "boundary", "negative"):
        (tmp_path / name).write_bytes(name.encode())
    return EvaluationManifest(
        tmp_path,
        (ReferenceImage("target-ref", "target", tmp_path / "reference", "test"),),
        tuple(Scan(name, tmp_path / name, "test", expected) for name, expected in (
            ("positive", ("target",)), ("boundary", ("target",)), ("negative", ()),
        )),
    )


class DistanceAdapter:
    name = "fixed-distance"

    def __init__(self, name="fixed-distance"):
        self.name = name
        self.seen = []

    def search(self, gallery, scan):
        self.seen.append(scan.id)
        score = {"positive": -0.5, "boundary": -0.6, "negative": -0.7}[scan.id]
        return SearchResult(True, (FaceScore("target", score),), score_semantics="negative_distance")


def test_test_only_fixed_policy_evaluates_holdout_with_strict_boundary(tmp_path):
    policy = DecisionPolicy("production_distance")
    plan = EvaluationPlan(holdout(tmp_path), tmp_path / "run", baseline=policy,
                          candidate=policy, mode="test_only")
    baseline, candidate = DistanceAdapter(), DistanceAdapter()
    run = compare(plan, baseline, candidate)
    assert baseline.seen == candidate.seen == ["positive", "boundary", "negative"]
    assert run.systems["baseline"].threshold == -0.6
    metrics = run.systems["baseline"].metrics
    assert (metrics.tp, metrics.fn, metrics.tn, metrics.fp) == (1, 1, 1, 0)
    assert run.evaluation_mode == "test_only"
    summary = json.loads((tmp_path / "run/run.json").read_text())
    assert summary["evaluation_mode"] == "test_only"
    assert summary["manifest"]["calibration_scans"] == 0
    threshold = json.loads((tmp_path / "run/threshold.json").read_text())
    assert threshold["baseline"]["calibrated_on"] is None
    report = (tmp_path / "run/report.md").read_text()
    assert "holdout" in report and "generalization" in report


def manifest_file(tmp_path):
    manifest = holdout(tmp_path)
    path = tmp_path / "manifest.toml"
    text = 'version = 1\nmedia_root = "."\n'
    for ref in manifest.references:
        text += f'[[references]]\nid = "{ref.id}"\nidentity = "{ref.identity_id}"\npath = "{ref.path.name}"\nsplit = "test"\n'
    for scan in manifest.scans:
        text += f'[[scans]]\nid = "{scan.id}"\npath = "{scan.path.name}"\nsplit = "test"\nexpected_identities = {json.dumps(scan.expected_identity_ids)}\n'
    path.write_text(text)
    return path


def test_manifest_test_only_requires_explicit_opt_in(tmp_path):
    path = manifest_file(tmp_path)
    with pytest.raises(ManifestError, match="calibration and test scans"):
        load_manifest(path)
    assert len(load_manifest(path, mode="test_only").scans) == 3


@pytest.mark.parametrize("role", ["baseline", "candidate"])
def test_test_only_rejects_calibration_policy_before_adapter_execution(tmp_path, role):
    policy = DecisionPolicy("production_distance")
    policies = {"baseline": policy, "candidate": policy}
    policies[role] = DecisionPolicy("calibrate_f1")
    with pytest.raises(ValueError, match="test_only requires production_distance"):
        EvaluationPlan(holdout(tmp_path), tmp_path / "run", mode="test_only", **policies)
    assert not (tmp_path / "run").exists()


def test_default_plan_still_requires_calibration_scans(tmp_path):
    adapter = DistanceAdapter()
    policy = DecisionPolicy("production_distance")
    with pytest.raises(ManifestError, match="calibration and test scans"):
        compare(EvaluationPlan(holdout(tmp_path), tmp_path / "run", baseline=policy,
                               candidate=policy), adapter, adapter)
    assert adapter.seen == []


def test_cli_explicit_test_only_config(tmp_path):
    from app.evaluation.__main__ import main

    manifest_file(tmp_path)
    config = tmp_path / "evaluation.toml"
    config.write_text('''manifest = "manifest.toml"
output_dir = "run"
mode = "test_only"
[baseline]
factory = "test_holdout:DistanceAdapter"
policy = "production_distance"
[candidate]
factory = "test_holdout:DistanceAdapter"
policy = "production_distance"
''')
    assert main(["--config", str(config)]) == 0
    assert json.loads((tmp_path / "run/run.json").read_text())["evaluation_mode"] == "test_only"


@pytest.mark.parametrize("item", ["reference", "scan"])
def test_test_only_rejects_calibration_media(tmp_path, item):
    manifest = holdout(tmp_path)
    if item == "reference":
        manifest = replace(manifest, references=(
            *manifest.references, replace(manifest.references[0], id="cal-ref", identity_id="other", split="calibration"),
        ))
    else:
        manifest = replace(manifest, scans=(
            *manifest.scans, replace(manifest.scans[-1], id="cal-scan", split="calibration"),
        ))
    with pytest.raises(ManifestError, match="only test references and scans"):
        validate_manifest(manifest, mode="test_only")


@pytest.mark.parametrize("role", ["baseline", "candidate"])
def test_cli_test_only_rejects_calibration_before_factory_execution(tmp_path, role):
    from app.evaluation.__main__ import main

    manifest_file(tmp_path)
    config = tmp_path / "evaluation.toml"
    text = 'manifest = "manifest.toml"\noutput_dir = "run"\nmode = "test_only"\n'
    for name in ("baseline", "candidate"):
        policy = "calibrate_f1" if name == role else "production_distance"
        text += f'[{name}]\nfactory = "missing_factory_must_not_import:Adapter"\npolicy = "{policy}"\n'
    config.write_text(text)
    with pytest.raises(ValueError, match="test_only requires production_distance"):
        main(["--config", str(config)])
    assert not (tmp_path / "run").exists()


def test_test_only_labels_do_not_change_threshold_or_predictions(tmp_path):
    manifest = holdout(tmp_path)
    policy = DecisionPolicy("production_distance")
    runs = []
    for index, scans in enumerate((manifest.scans, tuple(
        replace(scan, expected_identity_ids=() if scan.expected_identity_ids else ("target",))
        for scan in manifest.scans
    ))):
        run = compare(EvaluationPlan(replace(manifest, scans=scans), tmp_path / f"run-{index}",
                                     baseline=policy, candidate=policy, mode="test_only"),
                      DistanceAdapter(), DistanceAdapter())
        runs.append(run.systems["baseline"])
    assert runs[0].threshold == runs[1].threshold == -0.6
    assert [d.predicted_identity_ids for d in runs[0].decisions] == [
        d.predicted_identity_ids for d in runs[1].decisions
    ]
