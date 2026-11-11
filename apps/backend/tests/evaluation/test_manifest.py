from pathlib import Path
from dataclasses import replace

import pytest

from app.evaluation import (
    EvaluationManifest,
    EvaluationPlan,
    ManifestError,
    ReferenceImage,
    Scan,
    SearchResult,
    compare,
    load_manifest,
)


def test_load_manifest_resolves_local_media_relative_to_manifest(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    (media / "alice.ref").write_bytes(b"alice synthetic reference")
    (media / "bob.ref").write_bytes(b"bob synthetic reference")
    (media / "alice-cal.scan").write_bytes(b"synthetic calibration")
    (media / "bob-test.scan").write_bytes(b"synthetic test")
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(
        """
version = 1
media_root = "media"

[[references]]
id = "alice-reference"
identity = "alice"
path = "alice.ref"
split = "calibration"

[[references]]
id = "bob-reference"
identity = "bob"
path = "bob.ref"
split = "test"

[[scans]]
id = "alice-calibration"
path = "alice-cal.scan"
split = "calibration"
expected_identities = ["alice"]

[[scans]]
id = "bob-test"
path = "bob-test.scan"
split = "test"
expected_identities = ["bob"]
""".strip(),
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)

    assert manifest.references[0].path == (media / "alice.ref").resolve()
    assert manifest.scans[1].expected_identity_ids == ("bob",)
    assert manifest.media_root == media.resolve()


def test_load_manifest_rejects_identity_leakage_between_splits(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("alice-cal.ref", "alice-test.ref", "cal.scan", "test.scan"):
        (media / name).write_bytes(name.encode())
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(
        """
version = 1
media_root = "media"
[[references]]
id = "cal-ref"
identity = "alice"
path = "alice-cal.ref"
split = "calibration"
[[references]]
id = "test-ref"
identity = "alice"
path = "alice-test.ref"
split = "test"
[[scans]]
id = "cal"
path = "cal.scan"
split = "calibration"
expected_identities = ["alice"]
[[scans]]
id = "test"
path = "test.scan"
split = "test"
expected_identities = ["alice"]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="identity-disjoint"):
        load_manifest(manifest_path)


def test_compare_rejects_in_memory_media_outside_its_declared_root(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    outside = tmp_path / "outside.scan"
    outside.write_bytes(b"outside")
    for name in ("alice.ref", "bob.ref", "cal.scan"):
        (media / name).write_bytes(name.encode())
    manifest = EvaluationManifest(
        media_root=media,
        references=(
            ReferenceImage("alice-ref", "alice", media / "alice.ref", "calibration"),
            ReferenceImage("bob-ref", "bob", media / "bob.ref", "test"),
        ),
        scans=(
            Scan("cal", media / "cal.scan", "calibration", ("alice",)),
            Scan("test", outside, "test", ("bob",)),
        ),
    )

    class Adapter:
        name = "unused"

        def search(self, gallery, scan):
            return SearchResult(False)

    with pytest.raises(ManifestError, match="outside media_root"):
        compare(EvaluationPlan(manifest, tmp_path / "run"), Adapter(), Adapter())


def test_compare_rejects_malformed_in_memory_manifest_fields(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("alice.ref", "bob.ref", "cal.scan", "test.scan"):
        (media / name).write_bytes(name.encode())
    valid = EvaluationManifest(
        media_root=media,
        references=(
            ReferenceImage("alice-ref", "alice", media / "alice.ref", "calibration"),
            ReferenceImage("bob-ref", "bob", media / "bob.ref", "test"),
        ),
        scans=(
            Scan("cal", media / "cal.scan", "calibration", ("alice",)),
            Scan("test", media / "test.scan", "test", ("bob",)),
        ),
    )
    malformed = (
        (replace(valid, scans=(replace(valid.scans[0], id=""), valid.scans[1])), "non-empty"),
        (
            replace(
                valid,
                references=(valid.references[0], replace(valid.references[1], id="alice-ref")),
            ),
            "duplicate reference id",
        ),
        (
            replace(
                valid,
                scans=(valid.scans[0], replace(valid.scans[1], path=media / "missing")),
            ),
            "does not exist",
        ),
        (replace(valid, references=list(valid.references)), "tuple of ReferenceImage"),
    )

    class Adapter:
        name = "unused"

        def search(self, gallery, scan):
            raise AssertionError("validation must run first")

    for index, (manifest, message) in enumerate(malformed):
        with pytest.raises(ManifestError, match=message):
            compare(
                EvaluationPlan(manifest, tmp_path / f"run-{index}"),
                Adapter(),
                Adapter(),
            )


def test_load_manifest_rejects_media_copied_across_splits(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    (media / "alice.ref").write_bytes(b"alice-reference")
    (media / "bob.ref").write_bytes(b"bob-reference")
    (media / "cal.scan").write_bytes(b"same-media-content")
    (media / "copied-test.scan").write_bytes(b"same-media-content")
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(
        """
version = 1
media_root = "media"
[[references]]
id = "alice-ref"
identity = "alice"
path = "alice.ref"
split = "calibration"
[[references]]
id = "bob-ref"
identity = "bob"
path = "bob.ref"
split = "test"
[[scans]]
id = "cal"
path = "cal.scan"
split = "calibration"
expected_identities = ["alice"]
[[scans]]
id = "test"
path = "copied-test.scan"
split = "test"
expected_identities = ["bob"]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="media reused across calibration and test"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("mystery = true\n", "unknown manifest fields: mystery"),
        ("reference_typo", "unknown reference fields: identitiy"),
        ("missing_expected", "missing required scan fields: expected_identities"),
        ("scan_typo", "unknown scan fields: expected_identity"),
    ],
)
def test_load_manifest_rejects_unknown_or_missing_schema_fields(
    tmp_path: Path, mutation: str, message: str
) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("alice.ref", "bob.ref", "cal.scan", "test.scan"):
        (media / name).write_bytes(name.encode())
    top_extra = mutation if mutation.startswith("mystery") else ""
    reference_identity = (
        'identitiy = "alice"' if mutation == "reference_typo" else 'identity = "alice"'
    )
    expected_line = {
        "missing_expected": "",
        "scan_typo": 'expected_identity = ["bob"]',
    }.get(mutation, 'expected_identities = ["bob"]')
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(
        f"""
version = 1
media_root = "media"
{top_extra}
[[references]]
id = "alice-ref"
{reference_identity}
path = "alice.ref"
split = "calibration"
[[references]]
id = "bob-ref"
identity = "bob"
path = "bob.ref"
split = "test"
[[scans]]
id = "cal"
path = "cal.scan"
split = "calibration"
expected_identities = ["alice"]
[[scans]]
id = "test"
path = "test.scan"
split = "test"
{expected_line}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_path)
