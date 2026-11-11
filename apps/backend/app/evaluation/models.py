from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


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
class EvaluationPlan:
    manifest: EvaluationManifest
    output_dir: Path


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
