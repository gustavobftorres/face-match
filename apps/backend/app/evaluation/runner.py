from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import inf, isfinite
from time import perf_counter_ns
from typing import Protocol, Sequence
from uuid import uuid4

from .artifacts import write_run_bundle
from .manifest import validate_manifest
from .models import (
    EvaluationPlan,
    EvaluationMetrics,
    EvaluationRun,
    FaceScore,
    MatchDecision,
    ReferenceImage,
    Scan,
    SearchResult,
    SystemRun,
)


class SearchAdapter(Protocol):
    name: str

    def search(
        self, gallery: Sequence[ReferenceImage], scan: Scan
    ) -> SearchResult: ...


class AdapterOutputError(ValueError):
    """A search adapter returned data outside the score-only contract."""


def compare(
    plan: EvaluationPlan,
    baseline: SearchAdapter,
    candidate: SearchAdapter,
) -> EvaluationRun:
    validate_manifest(plan.manifest)
    adapters = (("baseline", baseline), ("candidate", candidate))
    calibration_scans = tuple(
        scan for scan in plan.manifest.scans if scan.split == "calibration"
    )
    test_scans = tuple(scan for scan in plan.manifest.scans if scan.split == "test")
    observations_by_role: dict[str, list[_Observation]] = {}
    thresholds: dict[str, float] = {}
    for role, adapter in adapters:
        observations_by_role[role] = [
            _observe(plan, adapter, scan) for scan in calibration_scans
        ]
        thresholds[role] = _calibrate_threshold(observations_by_role[role])
    for role, adapter in adapters:
        observations_by_role[role].extend(
            _observe(plan, adapter, scan) for scan in test_scans
        )

    systems = {}
    for role, adapter in adapters:
        observations = observations_by_role[role]
        threshold = thresholds[role]
        decisions = tuple(_decide(item, threshold) for item in observations)
        systems[role] = SystemRun(
            name=adapter.name,
            threshold=threshold,
            metrics=_metrics(decisions),
            decisions=decisions,
        )
    run = EvaluationRun(
        run_id=uuid4().hex,
        created_at=datetime.now(UTC).isoformat(),
        output_dir=plan.output_dir,
        systems=systems,
    )
    write_run_bundle(run, plan.manifest)
    return run


def _observe(
    plan: EvaluationPlan, adapter: SearchAdapter, scan: Scan
) -> _Observation:
    gallery = tuple(
        reference
        for reference in plan.manifest.references
        if reference.split == scan.split
    )
    started = perf_counter_ns()
    try:
        result = adapter.search(gallery, scan)
    except Exception as exc:
        result = SearchResult(has_face=False, error=f"{type(exc).__name__}: {exc}")
    _validate_adapter_output(result, gallery)
    latency_ms = (perf_counter_ns() - started) / 1_000_000
    return _Observation(scan, result, latency_ms)


def _validate_adapter_output(
    result: object, gallery: Sequence[ReferenceImage]
) -> None:
    if not isinstance(result, SearchResult):
        raise AdapterOutputError("adapter must return SearchResult")
    if result.score_semantics != "higher_is_better":
        raise AdapterOutputError("score semantics must be higher_is_better")
    if not isinstance(result.has_face, bool):
        raise AdapterOutputError("has_face must be a boolean")
    if not isinstance(result.scores, tuple) or not all(
        isinstance(score, FaceScore) for score in result.scores
    ):
        raise AdapterOutputError("scores must be a tuple of FaceScore values")
    if result.error is not None:
        if not isinstance(result.error, str) or not result.error.strip():
            raise AdapterOutputError("error must be a non-empty string")
        if result.has_face or result.scores:
            raise AdapterOutputError("error results cannot contain a face or scores")
    elif not result.has_face and result.scores:
        raise AdapterOutputError("scores cannot be returned without a face")

    gallery_identities = {reference.identity_id for reference in gallery}
    score_identities: set[str] = set()
    for score in result.scores:
        if not isinstance(score.identity_id, str) or not score.identity_id:
            raise AdapterOutputError("score identity must be a non-empty string")
        if score.identity_id not in gallery_identities:
            raise AdapterOutputError(
                f"score identity is not present in the gallery: {score.identity_id}"
            )
        if score.identity_id in score_identities:
            raise AdapterOutputError(f"duplicate score identity: {score.identity_id}")
        score_identities.add(score.identity_id)
        if type(score.score) is not float:
            raise AdapterOutputError("score must be a JSON-serializable float")
        if not isfinite(score.score):
            raise AdapterOutputError("score must be finite")
    if result.has_face and score_identities != gallery_identities:
        missing = gallery_identities - score_identities
        suffix = f"; missing: {', '.join(sorted(missing))}" if missing else ""
        raise AdapterOutputError(
            "has_face=True requires exactly one score per Gallery identity" + suffix
        )


@dataclass(frozen=True)
class _Observation:
    scan: Scan
    result: SearchResult
    latency_ms: float


def _calibrate_threshold(observations: Sequence[_Observation]) -> float:
    calibration = [item for item in observations if item.scan.split == "calibration"]
    scores = sorted(
        {
            score.score
            for item in calibration
            if not item.result.error and item.result.has_face
            for score in item.result.scores
        }
    )
    candidates = scores + [inf]
    best_threshold = inf
    best_rank = (-1.0, -1, -1.0)
    for threshold in candidates:
        tp = fp = fn = 0
        for item in calibration:
            if item.result.error:
                continue
            expected = set(item.scan.expected_identity_ids)
            predicted = {
                score.identity_id
                for score in item.result.scores
                if item.result.has_face and score.score >= threshold
            }
            if expected:
                if expected & predicted:
                    tp += 1
                else:
                    fn += 1
            elif predicted:
                fp += 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rank = (f1, -fp, threshold)
        if rank > best_rank:
            best_rank = rank
            best_threshold = threshold
    return best_threshold


def _decide(observation: _Observation, threshold: float) -> MatchDecision:
    result = observation.result
    if result.error:
        status = "error"
        predicted = ()
    elif not result.has_face:
        status = "no_face"
        predicted = ()
    else:
        predicted = tuple(
            score.identity_id for score in result.scores if score.score >= threshold
        )
        status = "match" if predicted else "no_match"
    return MatchDecision(
        scan_id=observation.scan.id,
        split=observation.scan.split,
        status=status,
        expected_identity_ids=observation.scan.expected_identity_ids,
        predicted_identity_ids=predicted,
        scores=result.scores,
        error=result.error,
        latency_ms=observation.latency_ms,
    )


def _metrics(decisions: Sequence[MatchDecision]) -> EvaluationMetrics:
    tp = fp = fn = tn = errors = no_face = 0
    test_decisions = [item for item in decisions if item.split == "test"]
    latencies = [item.latency_ms for item in test_decisions]
    for decision in test_decisions:
        if decision.status == "error":
            errors += 1
            continue
        if decision.status == "no_face":
            no_face += 1
        expected = set(decision.expected_identity_ids)
        predicted = set(decision.predicted_identity_ids)
        if expected:
            if expected & predicted:
                tp += 1
            else:
                fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return EvaluationMetrics(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        fpir=_ratio(fp, fp + tn),
        fnir=_ratio(fn, tp + fn),
        tpir=recall,
        errors=errors,
        no_face=no_face,
        evaluated_images=tp + fp + fn + tn,
        latency_ms={
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, int(len(ordered) * percentile + 0.999999999))
    return ordered[min(rank, len(ordered)) - 1]
