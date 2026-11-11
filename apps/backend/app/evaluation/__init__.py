"""Offline, reproducible comparison of face-search implementations."""

from .manifest import ManifestError, load_manifest, validate_manifest
from .face_search import DlibProductionAdapter, FaceSearchAdapter
from .models import (
    EvaluationManifest,
    EvaluationMetrics,
    EvaluationPlan,
    DecisionPolicy,
    EvaluationRun,
    FaceScore,
    MatchDecision,
    ReferenceImage,
    Scan,
    SearchResult,
    SystemRun,
)
from .runner import AdapterOutputError, compare

__all__ = [
    "EvaluationManifest",
    "EvaluationMetrics",
    "EvaluationPlan",
    "DecisionPolicy",
    "DlibProductionAdapter",
    "EvaluationRun",
    "FaceScore",
    "FaceSearchAdapter",
    "MatchDecision",
    "ReferenceImage",
    "Scan",
    "SearchResult",
    "SystemRun",
    "compare",
    "load_manifest",
    "ManifestError",
    "validate_manifest",
    "AdapterOutputError",
]
