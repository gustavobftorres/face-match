import json
from pathlib import Path

import pytest

import app.evaluation.artifacts as artifact_writer
from app.evaluation import (
    EvaluationManifest,
    EvaluationPlan,
    FaceScore,
    ReferenceImage,
    Scan,
    SearchResult,
    compare,
)


class ArtifactAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, gallery, scan):
        identity = gallery[0].identity_id
        score = 0.9 if scan.expected_identity_ids else 0.1
        return SearchResult(True, (FaceScore(identity, score),))


def test_compare_atomically_writes_the_complete_run_bundle(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("alice.ref", "bob.ref", "cal-pos", "cal-neg", "test-pos", "test-neg"):
        (media / name).write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=media,
        references=(
            ReferenceImage("alice-ref", "alice", media / "alice.ref", "calibration"),
            ReferenceImage("bob-ref", "bob", media / "bob.ref", "test"),
        ),
        scans=(
            Scan("cal-pos", media / "cal-pos", "calibration", ("alice",)),
            Scan("cal-neg", media / "cal-neg", "calibration", ()),
            Scan("test-pos", media / "test-pos", "test", ("bob",)),
            Scan("test-neg", media / "test-neg", "test", ()),
        ),
    )
    output_dir = tmp_path / "run"

    run = compare(
        EvaluationPlan(manifest, output_dir),
        ArtifactAdapter("baseline-v1"),
        ArtifactAdapter("candidate-v2"),
    )

    assert {path.name for path in output_dir.iterdir()} == {
        "run.json",
        "threshold.json",
        "decisions.ndjson",
        "metrics.json",
        "timings.ndjson",
        "report.md",
    }
    assert json.loads((output_dir / "run.json").read_text())["run_id"] == run.run_id
    thresholds = json.loads((output_dir / "threshold.json").read_text())
    assert thresholds["baseline"]["calibrated_on"] == "calibration"
    assert thresholds["candidate"]["frozen_on"] == "test"
    decisions = (output_dir / "decisions.ndjson").read_text().splitlines()
    assert len(decisions) == len(manifest.scans) * 2
    assert "# Face Search Evaluation" in (output_dir / "report.md").read_text()
    assert not list(output_dir.glob("*.tmp"))


def test_artifact_failure_publishes_no_partial_bundle(tmp_path: Path, monkeypatch) -> None:
    media = tmp_path / "media"
    media.mkdir()
    names = ("alice.ref", "bob.ref", "cal-pos", "cal-neg", "test-pos")
    for name in names:
        (media / name).write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=media,
        references=(
            ReferenceImage("alice-ref", "alice", media / "alice.ref", "calibration"),
            ReferenceImage("bob-ref", "bob", media / "bob.ref", "test"),
        ),
        scans=(
            Scan("cal-pos", media / "cal-pos", "calibration", ("alice",)),
            Scan("cal-neg", media / "cal-neg", "calibration", ()),
            Scan("test-pos", media / "test-pos", "test", ("bob",)),
        ),
    )
    output_dir = tmp_path / "run"

    def fail_during_bundle(path, rows):
        raise OSError("injected artifact failure")

    monkeypatch.setattr(artifact_writer, "_write_ndjson", fail_during_bundle)

    with pytest.raises(OSError, match="injected artifact failure"):
        compare(
            EvaluationPlan(manifest, output_dir),
            ArtifactAdapter("baseline"),
            ArtifactAdapter("candidate"),
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".run.*"))


def test_bundle_publish_fsyncs_staging_then_parent_around_rename(
    tmp_path: Path, monkeypatch
) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("alice.ref", "bob.ref", "cal", "test"):
        (media / name).write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=media,
        references=(
            ReferenceImage("alice", "alice", media / "alice.ref", "calibration"),
            ReferenceImage("bob", "bob", media / "bob.ref", "test"),
        ),
        scans=(
            Scan("cal", media / "cal", "calibration", ("alice",)),
            Scan("test", media / "test", "test", ("bob",)),
        ),
    )
    output_dir = tmp_path / "run"
    events = []
    real_replace = artifact_writer.os.replace

    def record_fsync(path):
        events.append(("fsync", Path(path)))

    def record_replace(source, destination):
        if Path(source).is_dir():
            events.append(("rename", Path(destination)))
        return real_replace(source, destination)

    monkeypatch.setattr(artifact_writer, "_fsync_directory", record_fsync, raising=False)
    monkeypatch.setattr(artifact_writer.os, "replace", record_replace)

    compare(
        EvaluationPlan(manifest, output_dir),
        ArtifactAdapter("baseline"),
        ArtifactAdapter("candidate"),
    )

    assert [event for event, _path in events] == ["fsync", "rename", "fsync"]
    assert events[0][1].parent == tmp_path
    assert events[0][1].name.startswith(".run.")
    assert events[1][1] == output_dir
    assert events[2][1] == tmp_path
