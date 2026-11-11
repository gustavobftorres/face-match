from __future__ import annotations

import argparse
import importlib
import tomllib
from pathlib import Path
from typing import Any

from . import DecisionPolicy, EvaluationPlan, compare, load_manifest
from .face_search import DlibProductionAdapter, FaceSearchAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two face-search systems offline")
    parser.add_argument("--config", required=True, type=Path, help="evaluation TOML file")
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)
    _known_fields(config, {"manifest", "output_dir", "baseline", "candidate"}, "config")
    policies = {role: _policy(config.get(role), role) for role in ("baseline", "candidate")}
    manifest_path = _relative_path(config_path, _required_text(config, "manifest"))
    output_dir = _relative_path(config_path, _required_text(config, "output_dir"))
    plan = EvaluationPlan(
        load_manifest(manifest_path), output_dir, **policies,
        adapter_config={role: config[role] for role in ("baseline", "candidate")},
    )
    baseline = _adapter(config.get("baseline"), "baseline")
    candidate = _adapter(config.get("candidate"), "candidate")
    run = compare(
        plan,
        baseline,
        candidate,
    )
    print(f"evaluation run {run.run_id} written to {run.output_dir}")
    return 0


def _adapter(value: Any, role: str):
    if not isinstance(value, dict):
        raise ValueError(f"[{role}] table is required")
    name = value.get("name", role)
    if not isinstance(name, str) or not name:
        raise ValueError(f"{role}.name must be a non-empty string")
    factory_path = value.get("factory")
    options = value.get("options", {})
    if not isinstance(options, dict):
        raise ValueError(f"{role}.options must be a table")
    if factory_path is None:
        factory = DlibProductionAdapter if value.get("policy") == "production_distance" else FaceSearchAdapter
    elif isinstance(factory_path, str) and ":" in factory_path:
        module_name, attribute = factory_path.split(":", 1)
        factory = getattr(importlib.import_module(module_name), attribute)
    else:
        raise ValueError(f"{role}.factory must use 'module:attribute' syntax")
    return factory(name=name, **options)


def _policy(value: Any, role: str) -> DecisionPolicy:
    if not isinstance(value, dict):
        raise ValueError(f"[{role}] table is required")
    _known_fields(value, {"name", "factory", "options", "policy", "threshold"}, role)
    return DecisionPolicy(value.get("policy", "calibrate_f1"), value.get("threshold"))


def _known_fields(value: dict, allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown {label} fields: {', '.join(sorted(unknown))}")


def _relative_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (config_path.parent / path).resolve()


def _required_text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
