from math import nextafter
from pathlib import Path

import pytest

from app.evaluation.face_search import DlibProductionAdapter, FaceSearchAdapter
from app.evaluation.models import ReferenceImage, Scan


def production_manifest(tmp_path):
    from app.evaluation import EvaluationManifest
    paths = {}
    for name in ("cal-ref", "test-ref", "cal", "boundary", "below"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    return EvaluationManifest(tmp_path, (
        ReferenceImage("a", "a", paths["cal-ref"], "calibration"),
        ReferenceImage("b", "b", paths["test-ref"], "test"),
    ), (
        Scan("cal", paths["cal"], "calibration", ("a",)),
        Scan("boundary", paths["boundary"], "test", ("b",)),
        Scan("below", paths["below"], "test", ("b",)),
    ))


def test_fixed_production_policy_has_exact_boundary_and_no_calibration(tmp_path, monkeypatch):
    import app.evaluation.runner as runner
    from app.evaluation import EvaluationPlan, compare
    from app.evaluation.models import DecisionPolicy

    def forbidden(*args):
        raise AssertionError("fixed policy must never calibrate using labels")

    monkeypatch.setattr(runner, "_calibrate_threshold", forbidden)
    manifest = production_manifest(tmp_path)
    distances = {b"cal": 0.99, b"boundary": 0.6, b"below": nextafter(0.6, 0.0)}
    adapter = DlibProductionAdapter(encoder=lambda data: [data], distance=lambda _, scan: distances[scan])
    policy = DecisionPolicy("production_distance")
    run = compare(EvaluationPlan(manifest, tmp_path / "run", policy, policy), adapter, adapter)
    baseline = run.systems["baseline"]
    assert baseline.threshold == -0.6
    assert [decision.status for decision in baseline.decisions] == ["no_match", "no_match", "match"]


@pytest.mark.parametrize("policy,threshold", [("unknown", None), ("calibrate_f1", 0.6), ("production_distance", -1), ("production_distance", float("nan")), ("production_distance", True)])
def test_invalid_decision_policies(policy, threshold):
    from app.evaluation.models import DecisionPolicy
    with pytest.raises(ValueError):
        DecisionPolicy(policy, threshold)


def test_production_policy_rejects_legacy_scores(tmp_path):
    from app.evaluation import EvaluationPlan, compare, AdapterOutputError
    from app.evaluation.models import DecisionPolicy
    adapter = FaceSearchAdapter(encoder=lambda _: [1], distance=lambda *_: 0.6)
    with pytest.raises(AdapterOutputError, match="negative_distance"):
        compare(EvaluationPlan(production_manifest(tmp_path), tmp_path / "run", DecisionPolicy("production_distance")), adapter, adapter)


@pytest.mark.parametrize("options", [{"callback": lambda: None}, {"value": object()}, {"value": float("inf")}])
def test_plan_rejects_non_json_adapter_config(tmp_path, options):
    from app.evaluation import EvaluationPlan
    with pytest.raises(ValueError, match="JSON"):
        EvaluationPlan(production_manifest(tmp_path), tmp_path / "run", adapter_config={"baseline": {"options": options}})


def test_plan_default_adapter_config_is_compatible(tmp_path):
    from app.evaluation import EvaluationPlan
    assert EvaluationPlan(production_manifest(tmp_path), tmp_path / "run").adapter_config == {}


def test_production_adapter_uses_first_reference_face_and_any_scan_face(tmp_path):
    reference = tmp_path / "ref"
    reference.write_bytes(b"ref")
    scan = tmp_path / "scan"
    scan.write_bytes(b"scan")
    calls = []

    def distance(known, observed):
        calls.append((known, observed))
        return observed if known == "first" else 0.0

    adapter = DlibProductionAdapter(
        encoder=lambda content: ["first", "second"] if content == b"ref" else [0.8, 0.6],
        distance=distance,
    )
    result = adapter.search([ReferenceImage("r", "a", reference, "test")], Scan("s", scan, "test", ()))
    assert result.score_semantics == "negative_distance"
    assert result.scores[0].score == -0.6
    assert calls == [("first", 0.8), ("first", 0.6)]


def test_legacy_adapter_keeps_one_minus_distance(tmp_path):
    path = tmp_path / "image"
    path.write_bytes(b"x")
    adapter = FaceSearchAdapter(encoder=lambda _: [1], distance=lambda *_: 0.6)
    result = adapter.search([ReferenceImage("r", "a", path, "test")], Scan("s", path, "test", ()))
    assert result.scores[0].score == 1.0 - 0.6
    assert result.score_semantics == "higher_is_better"


def test_production_adapter_rejects_multiple_references_and_distinguishes_failures(tmp_path):
    path = tmp_path / "image"
    path.write_bytes(b"x")
    gallery = [ReferenceImage("r", "a", path, "test"), ReferenceImage("r2", "a", path, "test")]
    scan = Scan("s", path, "test", ())
    adapter = DlibProductionAdapter(encoder=lambda _: [1], distance=lambda *_: 0.1)
    assert "one reference" in adapter.search(gallery, scan).error
    no_face = DlibProductionAdapter(encoder=lambda _: [], distance=lambda *_: 0.1).search(gallery[:1], scan)
    assert not no_face.has_face and no_face.error is None
    reference_path = tmp_path / "empty-ref"
    reference_path.write_bytes(b"empty")
    missing_reference_face = DlibProductionAdapter(
        encoder=lambda content: [] if content == b"empty" else [1], distance=lambda *_: 0.1,
    ).search([ReferenceImage("empty", "a", reference_path, "test")], scan)
    assert not missing_reference_face.has_face
    assert "reference image has no face" in missing_reference_face.error
    path.unlink()
    assert adapter.search(gallery[:1], scan).error is not None
