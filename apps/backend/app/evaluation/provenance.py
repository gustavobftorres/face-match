"""Capture the code, runtime, configuration and input bytes used by a run."""

from dataclasses import asdict
from importlib import metadata
import json
import platform
from pathlib import Path
import subprocess
import sys

from .manifest import _sha256
from .models import EvaluationPlan


def collect_provenance(plan: EvaluationPlan, adapters: tuple) -> dict:
    # Snapshot all public descriptions before the runner performs any inference.
    adapter_metadata = {role: _adapter_metadata(adapter) for role, adapter in adapters}
    packages = {}
    for package in ("face-recognition", "face-recognition-models", "dlib", "numpy", "Pillow"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=normal")
    return {
        "commit": commit,
        "git_dirty": bool(status) if status is not None else None,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "adapter_config": plan.adapter_config,
        "decisions": {
            role: {**asdict(getattr(plan, role)),
                   "threshold_source": getattr(plan, role).source,
                   "comparator": getattr(plan, role).comparator,
                   "score_semantics": getattr(plan, role).score_semantics,
                   "calibrated_on": "calibration" if getattr(plan, role).policy == "calibrate_f1" else None}
            for role, _ in adapters
        },
        "adapters": adapter_metadata,
        "dataset": {
            "references": [_media(item, plan) for item in plan.manifest.references],
            "scans": [_media(item, plan) for item in plan.manifest.scans],
        },
    }


def _adapter_metadata(adapter) -> dict:
    result = {"name": adapter.name,
              "identity": f"{type(adapter).__module__}:{type(adapter).__qualname__}"}
    describe = getattr(adapter, "describe", None)
    if describe is not None:
        if not callable(describe):
            raise ValueError("adapter describe must be callable")
        description = describe()
        if not isinstance(description, dict):
            raise ValueError("adapter describe() must return a finite JSON object")
        try:
            result["metadata"] = json.loads(json.dumps(description, allow_nan=False))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("adapter describe() must return a finite JSON object") from exc
    return result


def _media(item, plan: EvaluationPlan) -> dict:
    row = asdict(item)
    row["path"] = str(item.path.resolve().relative_to(plan.manifest.media_root.resolve()))
    row["sha256"] = _sha256(item.path)
    return row


def _git(*arguments: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *arguments], cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
