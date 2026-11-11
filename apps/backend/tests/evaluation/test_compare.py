from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from app.evaluation import (
    AdapterOutputError,
    EvaluationManifest,
    EvaluationPlan,
    FaceScore,
    ReferenceImage,
    Scan,
    SearchResult,
    compare,
)


class RecordingAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[str] = []

    def search(self, gallery, scan):
        self.seen.append(scan.id)
        scores = (FaceScore(gallery[0].identity_id, 0.9),) if gallery else ()
        return SearchResult(has_face=True, scores=scores)


def test_compare_gives_baseline_and_candidate_the_same_scans(tmp_path: Path) -> None:
    reference = tmp_path / "alice.ref"
    reference.write_bytes(b"synthetic reference")
    calibration = tmp_path / "calibration.scan"
    calibration.write_bytes(b"synthetic calibration")
    test = tmp_path / "test.scan"
    test.write_bytes(b"synthetic test")
    test_reference = tmp_path / "bob.ref"
    test_reference.write_bytes(b"synthetic bob reference")
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", reference, "calibration"),
            ReferenceImage("bob-ref", "bob", test_reference, "test"),
        ),
        scans=(
            Scan("calibration", calibration, "calibration", ("alice",)),
            Scan("test", test, "test", ()),
        ),
    )
    plan = EvaluationPlan(manifest=manifest, output_dir=tmp_path / "run")
    baseline = RecordingAdapter("baseline")
    candidate = RecordingAdapter("candidate")

    run = compare(plan, baseline, candidate)

    assert baseline.seen == ["calibration", "test"]
    assert candidate.seen == baseline.seen
    assert run.systems["baseline"].name == "baseline"
    assert run.systems["candidate"].name == "candidate"


class CalibrationFirstAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[str] = []

    def search(self, gallery, scan):
        if scan.split == "test" and self.seen != ["cal-a", "cal-b"]:
            raise AssertionError("test was presented before calibration completed")
        self.seen.append(scan.id)
        identity = gallery[0].identity_id
        return SearchResult(True, (FaceScore(identity, 0.9),))


def test_compare_completes_calibration_before_presenting_any_test_scan(tmp_path: Path) -> None:
    paths = {}
    for name in ("alice.ref", "bob.ref", "test", "cal-a", "cal-b"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", paths["alice.ref"], "calibration"),
            ReferenceImage("bob-ref", "bob", paths["bob.ref"], "test"),
        ),
        scans=(
            Scan("test", paths["test"], "test", ("bob",)),
            Scan("cal-a", paths["cal-a"], "calibration", ("alice",)),
            Scan("cal-b", paths["cal-b"], "calibration", ()),
        ),
    )
    baseline = CalibrationFirstAdapter("baseline")
    candidate = CalibrationFirstAdapter("candidate")

    compare(EvaluationPlan(manifest, tmp_path / "run"), baseline, candidate)

    assert baseline.seen == ["cal-a", "cal-b", "test"]
    assert candidate.seen == baseline.seen


class ScoreByScanAdapter:
    def __init__(self, name: str, values: dict[str, tuple[str, float]]) -> None:
        self.name = name
        self.values = values

    def search(self, gallery, scan):
        identity, score = self.values[scan.id]
        return SearchResult(has_face=True, scores=(FaceScore(identity, score),))


def test_threshold_uses_only_calibration_and_is_frozen_for_test(tmp_path: Path) -> None:
    paths = {}
    for name in ("alice.ref", "bob.ref", "cal-pos", "cal-neg", "test-pos"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", paths["alice.ref"], "calibration"),
            ReferenceImage("bob-ref", "bob", paths["bob.ref"], "test"),
        ),
        scans=(
            Scan("cal-pos", paths["cal-pos"], "calibration", ("alice",)),
            Scan("cal-neg", paths["cal-neg"], "calibration", ()),
            Scan("test-pos", paths["test-pos"], "test", ("bob",)),
        ),
    )
    scores = {
        "cal-pos": ("alice", 0.8),
        "cal-neg": ("alice", 0.7),
        "test-pos": ("bob", 0.75),
    }

    run = compare(
        EvaluationPlan(manifest, tmp_path / "run"),
        ScoreByScanAdapter("baseline", scores),
        ScoreByScanAdapter("candidate", scores),
    )

    baseline = run.systems["baseline"]
    assert baseline.threshold == 0.8
    test_decision = next(item for item in baseline.decisions if item.scan_id == "test-pos")
    assert test_decision.status == "no_match"


class ResultByScanAdapter:
    name = "result-map"

    def __init__(self, results: dict[str, SearchResult]) -> None:
        self.results = results

    def search(self, gallery, scan):
        return self.results[scan.id]


def test_test_metrics_distinguish_match_no_face_no_match_and_error(tmp_path: Path) -> None:
    names = ("alice.ref", "bob.ref", "carol.ref", "cal-pos", "cal-neg", "tp", "fp", "fn", "tn", "err")
    paths = {name: tmp_path / name for name in names}
    for name, path in paths.items():
        path.write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", paths["alice.ref"], "calibration"),
            ReferenceImage("bob-ref", "bob", paths["bob.ref"], "test"),
            ReferenceImage("carol-ref", "carol", paths["carol.ref"], "test"),
        ),
        scans=(
            Scan("cal-pos", paths["cal-pos"], "calibration", ("alice",)),
            Scan("cal-neg", paths["cal-neg"], "calibration", ()),
            Scan("tp", paths["tp"], "test", ("bob",)),
            Scan("fp", paths["fp"], "test", ()),
            Scan("fn", paths["fn"], "test", ("carol",)),
            Scan("tn", paths["tn"], "test", ()),
            Scan("err", paths["err"], "test", ()),
        ),
    )
    results = {
        "cal-pos": SearchResult(True, (FaceScore("alice", 0.8),)),
        "cal-neg": SearchResult(True, (FaceScore("alice", 0.7),)),
        "tp": SearchResult(True, (FaceScore("bob", 0.9), FaceScore("carol", 0.1))),
        "fp": SearchResult(True, (FaceScore("bob", 0.9), FaceScore("carol", 0.1))),
        "fn": SearchResult(False),
        "tn": SearchResult(True, (FaceScore("bob", 0.2), FaceScore("carol", 0.2))),
        "err": SearchResult(False, error="synthetic failure"),
    }

    run = compare(
        EvaluationPlan(manifest, tmp_path / "run"),
        ResultByScanAdapter(results),
        ResultByScanAdapter(results),
    )

    system = run.systems["baseline"]
    assert {item.scan_id: item.status for item in system.decisions if item.split == "test"} == {
        "tp": "match",
        "fp": "match",
        "fn": "no_face",
        "tn": "no_match",
        "err": "error",
    }
    assert (system.metrics.tp, system.metrics.fp, system.metrics.fn, system.metrics.tn) == (1, 1, 1, 1)
    assert system.metrics.precision == system.metrics.recall == 0.5
    assert system.metrics.fpir == system.metrics.fnir == system.metrics.tpir == 0.5
    assert system.metrics.errors == 1
    assert system.metrics.latency_ms.keys() == {"p50", "p95", "p99"}


def test_test_metrics_use_asymmetric_positive_and_negative_denominators(tmp_path: Path) -> None:
    scan_specs = {
        "cal-pos": ("calibration", ("alice",), "alice", 0.8),
        "cal-neg": ("calibration", (), "alice", 0.7),
        "tp-1": ("test", ("bob",), "bob", 0.9),
        "tp-2": ("test", ("bob",), "bob", 0.9),
        "tp-3": ("test", ("bob",), "bob", 0.9),
        "fn": ("test", ("carol",), "carol", None),
        "fp-1": ("test", (), "bob", 0.9),
        "fp-2": ("test", (), "bob", 0.9),
        "tn-1": ("test", (), "bob", 0.1),
        "tn-2": ("test", (), "bob", 0.1),
        "tn-3": ("test", (), "bob", 0.1),
    }
    paths = {}
    for name in ("alice.ref", "bob.ref", "carol.ref", *scan_specs):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", paths["alice.ref"], "calibration"),
            ReferenceImage("bob-ref", "bob", paths["bob.ref"], "test"),
            ReferenceImage("carol-ref", "carol", paths["carol.ref"], "test"),
        ),
        scans=tuple(
            Scan(scan_id, paths[scan_id], split, expected)
            for scan_id, (split, expected, _identity, _score) in scan_specs.items()
        ),
    )
    results = {}
    for scan_id, (split, _expected, identity, score) in scan_specs.items():
        if score is None:
            results[scan_id] = SearchResult(False)
        elif split == "calibration":
            results[scan_id] = SearchResult(True, (FaceScore(identity, score),))
        else:
            other_identity = "carol" if identity == "bob" else "bob"
            results[scan_id] = SearchResult(
                True,
                (FaceScore(identity, score), FaceScore(other_identity, 0.1)),
            )

    metrics = compare(
        EvaluationPlan(manifest, tmp_path / "run"),
        ResultByScanAdapter(results),
        ResultByScanAdapter(results),
    ).systems["candidate"].metrics

    assert (metrics.tp, metrics.fp, metrics.fn, metrics.tn) == (3, 2, 1, 3)
    assert metrics.precision == pytest.approx(0.6)
    assert metrics.recall == metrics.tpir == pytest.approx(0.75)
    assert metrics.fpir == pytest.approx(0.4)
    assert metrics.fnir == pytest.approx(0.25)


@pytest.mark.parametrize(
    "result, message",
    [
        (SearchResult(True, (FaceScore("alice", float("nan")),)), "finite"),
        (SearchResult(True, (FaceScore("alice", float("inf")),)), "finite"),
        (SearchResult(True, (FaceScore("alice", Fraction(1, 2)),)), "float"),
        (SearchResult(True, (FaceScore("alice", Decimal("0.5")),)), "float"),
        (SearchResult(True, (FaceScore("alice", True),)), "float"),
        (SearchResult(True, ()), "exactly one score"),
        (SearchResult(True, (FaceScore("not-in-gallery", 0.5),)), "gallery"),
        (
            SearchResult(True, (FaceScore("alice", 0.5), FaceScore("alice", 0.4))),
            "duplicate",
        ),
        (
            SearchResult(
                True,
                (FaceScore("alice", 0.5),),
                score_semantics="lower_is_better",
            ),
            "higher_is_better",
        ),
        (SearchResult(False, (FaceScore("alice", 0.5),)), "without a face"),
        (SearchResult(True, (FaceScore("alice", 0.5),), error="broken"), "error"),
    ],
)
def test_compare_rejects_invalid_adapter_output_before_artifacts(
    tmp_path: Path, result: SearchResult, message: str
) -> None:
    paths = {}
    for name in ("alice.ref", "bob.ref", "cal", "test"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-ref", "alice", paths["alice.ref"], "calibration"),
            ReferenceImage("bob-ref", "bob", paths["bob.ref"], "test"),
        ),
        scans=(
            Scan("cal", paths["cal"], "calibration", ("alice",)),
            Scan("test", paths["test"], "test", ("bob",)),
        ),
    )
    adapter = ResultByScanAdapter({"cal": result, "test": result})
    output_dir = tmp_path / "run"

    with pytest.raises(AdapterOutputError, match=message):
        compare(EvaluationPlan(manifest, output_dir), adapter, adapter)

    assert not output_dir.exists()


def test_compare_requires_one_aggregated_score_for_every_gallery_identity(
    tmp_path: Path,
) -> None:
    paths = {}
    for name in ("alice-1.ref", "alice-2.ref", "amy.ref", "bob.ref", "cal", "test"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=tmp_path,
        references=(
            ReferenceImage("alice-1", "alice", paths["alice-1.ref"], "calibration"),
            ReferenceImage("alice-2", "alice", paths["alice-2.ref"], "calibration"),
            ReferenceImage("amy", "amy", paths["amy.ref"], "calibration"),
            ReferenceImage("bob", "bob", paths["bob.ref"], "test"),
        ),
        scans=(
            Scan("cal", paths["cal"], "calibration", ("alice",)),
            Scan("test", paths["test"], "test", ("bob",)),
        ),
    )
    incomplete = SearchResult(True, (FaceScore("alice", 0.8),))
    adapter = ResultByScanAdapter({"cal": incomplete, "test": incomplete})

    with pytest.raises(AdapterOutputError, match="exactly one score.*amy"):
        compare(EvaluationPlan(manifest, tmp_path / "run"), adapter, adapter)
