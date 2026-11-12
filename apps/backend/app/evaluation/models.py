from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from math import isfinite
from typing import Any, Literal, Mapping


@dataclass(frozen=True)
class ReferenceImage:
    id: str
    identity_id: str
    path: Path
    split: str


@dataclass(frozen=True)
class Scan:
    id: str
    path: Path
    split: str
    expected_identity_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationManifest:
    media_root: Path
    references: tuple[ReferenceImage, ...]
    scans: tuple[Scan, ...]


@dataclass(frozen=True)
class DecisionPolicy:
    policy: Literal["calibrate_f1", "production_distance", "fixed_similarity"] = "calibrate_f1"
    threshold: float | None = None
    threshold_source: str | None = None

    def __post_init__(self) -> None:
        if self.policy not in ("calibrate_f1", "production_distance", "fixed_similarity"):
            raise ValueError(f"unknown decision policy: {self.policy}")
        if self.policy == "calibrate_f1":
            if self.threshold is not None:
                raise ValueError("calibrate_f1 cannot specify a fixed threshold")
        elif self.policy == "fixed_similarity":
            if (type(self.threshold) not in (int, float)
                    or not isfinite(self.threshold) or not -1 <= self.threshold <= 1):
                raise ValueError("fixed_similarity requires an explicit finite cosine threshold in [-1, 1]")
        elif self.threshold is None:
            object.__setattr__(self, "threshold", 0.6)
        elif (type(self.threshold) not in (int, float)
              or not isfinite(self.threshold) or self.threshold < 0):
            raise ValueError("production distance threshold must be finite and non-negative")
        if self.threshold_source not in (None, "provided_fixed", "external_calibration"):
            raise ValueError("threshold_source must be provided_fixed or external_calibration")
        if self.policy == "calibrate_f1" and self.threshold_source is not None:
            raise ValueError("calibrate_f1 cannot specify threshold_source")

    @property
    def source(self) -> str:
        if self.policy == "calibrate_f1":
            return "calibration_f1"
        return self.threshold_source or (
            "provided_fixed" if self.policy == "fixed_similarity" else "production_configuration"
        )

    @property
    def comparator(self) -> str:
        return ">" if self.policy == "production_distance" else ">="

    @property
    def score_semantics(self) -> str:
        return "negative_distance" if self.policy == "production_distance" else "higher_is_better"


@dataclass(frozen=True)
class EvaluationPlan:
    """Python callers supply JSON adapter_config for custom factory/options provenance.

    Adapter instances are never introspected for configuration. The CLI supplies
    its selected baseline/candidate TOML tables automatically.
    """

    manifest: EvaluationManifest
    output_dir: Path
    baseline: DecisionPolicy = field(default_factory=DecisionPolicy)
    candidate: DecisionPolicy = field(default_factory=DecisionPolicy)
    adapter_config: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    mode: Literal["calibration_test", "test_only"] = "calibration_test"

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, DecisionPolicy) or not isinstance(self.candidate, DecisionPolicy):
            raise ValueError("baseline and candidate must be DecisionPolicy values")
        if self.mode not in ("calibration_test", "test_only"):
            raise ValueError(f"unknown evaluation mode: {self.mode}")
        if self.mode == "test_only" and any(
            policy.policy not in ("production_distance", "fixed_similarity")
            for policy in (self.baseline, self.candidate)
        ):
            raise ValueError("test_only requires production_distance or fixed_similarity policies for baseline and candidate")
        if (not isinstance(self.adapter_config, dict)
                or set(self.adapter_config) - {"baseline", "candidate"}
                or not all(isinstance(value, dict) for value in self.adapter_config.values())):
            raise ValueError("adapter_config must be a JSON object with baseline/candidate objects")
        try:
            snapshot = json.loads(json.dumps(self.adapter_config, allow_nan=False))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("adapter_config must contain finite JSON-serializable metadata") from exc
        object.__setattr__(self, "adapter_config", snapshot)


@dataclass(frozen=True)
class FaceScore:
    identity_id: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    has_face: bool
    scores: tuple[FaceScore, ...] = ()
    error: str | None = None
    score_semantics: str = "higher_is_better"


@dataclass(frozen=True)
class SystemRun:
    name: str
    threshold: float
    metrics: EvaluationMetrics
    decisions: tuple[MatchDecision, ...] = ()
    decision_policy: DecisionPolicy = field(default_factory=DecisionPolicy)
    adapter_identity: str = ""


@dataclass(frozen=True)
class MatchDecision:
    scan_id: str
    split: str
    status: str
    expected_identity_ids: tuple[str, ...]
    predicted_identity_ids: tuple[str, ...] = ()
    scores: tuple[FaceScore, ...] = ()
    error: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class EvaluationMetrics:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    fpir: float
    fnir: float
    tpir: float
    errors: int
    no_face: int
    evaluated_images: int
    latency_ms: Mapping[str, float]


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    created_at: str
    output_dir: Path
    systems: Mapping[str, SystemRun] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    evaluation_mode: str = "calibration_test"
