"""Capture the code, runtime, configuration and input bytes used by a run."""

from dataclasses import asdict
from importlib import metadata
import platform
from pathlib import Path
import subprocess
import sys

from .manifest import _sha256
from .models import EvaluationPlan


def collect_provenance(plan: EvaluationPlan, adapters: tuple) -> dict:
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
        "decisions": {role: asdict(getattr(plan, role)) for role, _ in adapters},
        "adapters": {
            role: {"name": adapter.name,
                   "identity": f"{type(adapter).__module__}:{type(adapter).__qualname__}"}
            for role, adapter in adapters
        },
        "dataset": {
            "references": [_media(item, plan) for item in plan.manifest.references],
            "scans": [_media(item, plan) for item in plan.manifest.scans],
        },
    }


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
