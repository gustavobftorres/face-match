import json

import pytest

from app.evaluation import DecisionPolicy, EvaluationPlan, FaceScore, SearchResult, compare
from dataclasses import replace

from test_holdout import DistanceAdapter, holdout, manifest_file


class SimilarityAdapter:
    name = "cosine"

    def __init__(self, name="cosine"):
        self.name = name

    def search(self, gallery, scan):
        score = {"positive": 0.7, "boundary": 0.5, "negative": 0.4}[scan.id]
        return SearchResult(True, (FaceScore("target", score),))


def test_fixed_similarity_uses_inclusive_explicit_threshold_without_calibration(tmp_path):
    run = compare(EvaluationPlan(
        holdout(tmp_path), tmp_path / "run", mode="test_only",
        baseline=DecisionPolicy("production_distance"),
        candidate=DecisionPolicy("fixed_similarity", 0.5),
    ), DistanceAdapter(), SimilarityAdapter())
    candidate = run.systems["candidate"]
    assert candidate.threshold == 0.5
    assert (candidate.metrics.tp, candidate.metrics.tn, candidate.metrics.fp) == (2, 1, 0)
    policy = json.loads((tmp_path / "run/threshold.json").read_text())["candidate"]
    assert policy["comparator"] == ">="
    assert policy["score_semantics"] == "higher_is_better"
    assert policy["calibrated_on"] is None
    assert policy["threshold_source"] == "provided_fixed"
    assert policy["distance_threshold"] is None


def test_adapter_metadata_is_a_snapshot_taken_before_any_inference(tmp_path):
    events = []

    class DescribedAdapter(SimilarityAdapter):
        metadata = {"models": {"face": {"sha256": "abc"}}, "providers": ["CPU"]}

        def describe(self):
            events.append("describe")
            return self.metadata

        def search(self, gallery, scan):
            events.append("search")
            self.metadata["providers"].append("mutated")
            return super().search(gallery, scan)

    baseline, candidate = DescribedAdapter(), DescribedAdapter()
    policy = DecisionPolicy("fixed_similarity", 0.5, "external_calibration")
    run = compare(EvaluationPlan(holdout(tmp_path), tmp_path / "run", mode="test_only",
                                 baseline=policy, candidate=policy), baseline, candidate)
    assert events[:2] == ["describe", "describe"]
    assert run.provenance["adapters"]["candidate"]["metadata"]["providers"] == ["CPU"]
    recorded = run.provenance["decisions"]["candidate"]
    assert recorded["threshold_source"] == "external_calibration"
    assert recorded["calibrated_on"] is None
    assert recorded["comparator"] == ">="
    assert recorded["score_semantics"] == "higher_is_better"


@pytest.mark.parametrize("metadata", [None, [], {"value": float("nan")},
                                      {"value": float("inf")}, {"value": object()}])
def test_invalid_public_metadata_rejects_run_before_either_adapter_search(tmp_path, metadata):
    class InvalidDescription(SimilarityAdapter):
        def describe(self):
            return metadata

    baseline = DistanceAdapter()
    with pytest.raises(ValueError, match="finite JSON object"):
        compare(EvaluationPlan(holdout(tmp_path), tmp_path / "run", mode="test_only",
                               baseline=DecisionPolicy("production_distance"),
                               candidate=DecisionPolicy("fixed_similarity", 0.5)),
                baseline, InvalidDescription())
    assert baseline.seen == []
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("threshold", [None, True, "0.5", float("nan"),
                                       float("inf"), float("-inf"), -1.01, 1.01])
def test_fixed_similarity_requires_explicit_finite_cosine_threshold(threshold):
    with pytest.raises(ValueError, match="explicit finite cosine threshold"):
        DecisionPolicy("fixed_similarity", threshold)


@pytest.mark.parametrize("threshold", [-1, 0, 1])
def test_fixed_similarity_accepts_cosine_domain_endpoints(threshold):
    assert DecisionPolicy("fixed_similarity", threshold).threshold == threshold


def test_external_calibration_is_declarative_and_holdout_labels_do_not_tune(tmp_path):
    manifest = holdout(tmp_path)
    policy = DecisionPolicy("fixed_similarity", 0.5, "external_calibration")
    systems = []
    for index, scans in enumerate((manifest.scans, tuple(
        replace(scan, expected_identity_ids=() if scan.expected_identity_ids else ("target",))
        for scan in manifest.scans
    ))):
        run = compare(EvaluationPlan(replace(manifest, scans=scans), tmp_path / f"run-{index}",
                                     baseline=policy, candidate=policy, mode="test_only"),
                      SimilarityAdapter(), SimilarityAdapter())
        systems.append(run.systems["candidate"])
    assert systems[0].threshold == systems[1].threshold == 0.5
    assert [d.predicted_identity_ids for d in systems[0].decisions] == [
        d.predicted_identity_ids for d in systems[1].decisions
    ]


@pytest.mark.parametrize("source", ["magic", "calibration_f1", "production_configuration", 1])
def test_fixed_similarity_rejects_unknown_threshold_source(source):
    with pytest.raises(ValueError, match="threshold_source"):
        DecisionPolicy("fixed_similarity", 0.5, source)


def test_cli_supports_explicit_fixed_cosine_policy_and_external_source(tmp_path):
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
name = "candidate-public-name"
factory = "test_candidate_policy:SimilarityAdapter"
policy = "fixed_similarity"
threshold = 0.5
threshold_source = "external_calibration"
''')
    assert main(["--config", str(config)]) == 0
    policy = json.loads((tmp_path / "run/threshold.json").read_text())["candidate"]
    assert policy["name"] == "candidate-public-name"
    assert policy["threshold_source"] == "external_calibration"
    assert policy["calibrated_on"] is None
