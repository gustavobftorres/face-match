from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from typing import Any

from .models import EvaluationManifest, EvaluationRun


def write_run_bundle(run: EvaluationRun, manifest: EvaluationManifest) -> None:
    output_dir = run.output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(f"evaluation output already exists: {output_dir}")
    staging_dir = Path(
        tempfile.mkdtemp(dir=output_dir.parent, prefix=f".{output_dir.name}.")
    )
    try:
        _write_bundle_files(run, manifest, staging_dir)
        _fsync_directory(staging_dir)
        os.replace(staging_dir, output_dir)
        _fsync_directory(output_dir.parent)
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _write_bundle_files(
    run: EvaluationRun, manifest: EvaluationManifest, output_dir: Path
) -> None:
    system_summary = {
        role: {"name": system.name} for role, system in run.systems.items()
    }
    _write_json(
        output_dir / "run.json",
        {
            "schema_version": 1,
            "run_id": run.run_id,
            "created_at": run.created_at,
            "evaluation_mode": run.evaluation_mode,
            "manifest": {
                "references": len(manifest.references),
                "scans": len(manifest.scans),
                "calibration_scans": sum(s.split == "calibration" for s in manifest.scans),
                "test_scans": sum(s.split == "test" for s in manifest.scans),
                "identity_disjoint": True,
            },
            "systems": system_summary,
            "provenance": run.provenance,
        },
    )
    _write_json(
        output_dir / "threshold.json",
        {
            role: {
                "name": system.name,
                "threshold": _finite_or_none(system.threshold),
                "policy": system.decision_policy.policy,
                "comparator": system.decision_policy.comparator,
                "score_semantics": system.decision_policy.score_semantics,
                "distance_threshold": (system.decision_policy.threshold
                                       if system.decision_policy.policy == "production_distance" else None),
                "threshold_source": system.decision_policy.source,
                "calibrated_on": "calibration" if system.decision_policy.policy == "calibrate_f1" else None,
                "frozen_on": "test",
            }
            for role, system in run.systems.items()
        },
    )
    decision_rows = []
    timing_rows = []
    for role, system in run.systems.items():
        for decision in system.decisions:
            row = asdict(decision)
            row.update({"system": role, "system_name": system.name})
            decision_rows.append(row)
            timing_rows.append(
                {
                    "system": role,
                    "system_name": system.name,
                    "scan_id": decision.scan_id,
                    "split": decision.split,
                    "latency_ms": decision.latency_ms,
                }
            )
    _write_ndjson(output_dir / "decisions.ndjson", decision_rows)
    _write_json(
        output_dir / "metrics.json",
        {
            "split": "test",
            "evaluation_mode": run.evaluation_mode,
            "systems": {
                role: {"name": system.name, **asdict(system.metrics)}
                for role, system in run.systems.items()
            },
        },
    )
    _write_ndjson(output_dir / "timings.ndjson", timing_rows)
    _atomic_write(output_dir / "report.md", _report(run))


def _report(run: EvaluationRun) -> str:
    lines = [
        "# Face Search Evaluation",
        "",
        f"Run `{run.run_id}`. F1 thresholds use calibration only; distance and similarity policies use fixed thresholds. All thresholds are frozen for test.",
        "",
        "| System | Threshold | Precision | Recall | FPIR | FNIR | TPIR | p95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if run.evaluation_mode == "test_only":
        lines[2] = (
            f"Run `{run.run_id}`. Mode `test_only`: holdout evaluation with fixed "
            "thresholds; this run performs no calibration or threshold selection on these labels. "
            "Results describe this corpus and do not establish generalization to other identities or datasets."
        )
    for role, system in run.systems.items():
        metrics = system.metrics
        threshold = f"{system.threshold:.6g}" if isfinite(system.threshold) else "none"
        lines.append(
            f"| {role} ({system.name}) | {threshold} | {metrics.precision:.4f} | "
            f"{metrics.recall:.4f} | {metrics.fpir:.4f} | {metrics.fnir:.4f} | "
            f"{metrics.tpir:.4f} | {metrics.latency_ms['p95']:.3f} |"
        )
    lines.extend(["", "Decision policies:", ""])
    for role, system in run.systems.items():
        policy = system.decision_policy
        lines.append(
            f"- {role}: `{policy.policy}`, score semantics `{policy.score_semantics}`, "
            f"comparator `{policy.comparator}`, score threshold `{system.threshold}`; "
            f"threshold source `{policy.source}`. Adapter `{system.adapter_identity}`."
        )
    lines.extend(
        [
            "",
            "Errors are excluded from TP/FP/FN/TN. A no-face result is a miss for a "
            "positive scan and a true negative for a negative scan.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(
        json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows
    )
    _atomic_write(path, text)


def _atomic_write(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(os.fspath(path), flags)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            unsupported = {errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL)}
            if exc.errno not in unsupported:
                raise
    finally:
        os.close(descriptor)


def _finite_or_none(value: float) -> float | None:
    return value if isfinite(value) else None
