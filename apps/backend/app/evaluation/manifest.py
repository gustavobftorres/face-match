from __future__ import annotations

import tomllib
from hashlib import sha256
from pathlib import Path
from typing import Any

from .models import EvaluationManifest, ReferenceImage, Scan


class ManifestError(ValueError):
    """The evaluation manifest is invalid or unsafe to evaluate."""


def load_manifest(path: str | Path) -> EvaluationManifest:
    manifest_path = Path(path).resolve()
    with manifest_path.open("rb") as stream:
        document = tomllib.load(stream)
    _validate_keys(
        document,
        "manifest",
        required={"version", "media_root", "references", "scans"},
    )
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ManifestError("manifest version must be 1")

    root_value = document.get("media_root", ".")
    if not isinstance(root_value, str) or not root_value.strip():
        raise ManifestError("media_root must be a local path")
    media_root = (manifest_path.parent / root_value).resolve()
    if not media_root.is_dir():
        raise ManifestError(f"media_root is not a directory: {media_root}")

    references = tuple(
        _reference(item, media_root) for item in _tables(document, "references")
    )
    scans = tuple(_scan(item, media_root) for item in _tables(document, "scans"))
    _unique_ids(references, "reference")
    _unique_ids(scans, "scan")
    manifest = EvaluationManifest(
        media_root=media_root,
        references=references,
        scans=scans,
    )
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: EvaluationManifest) -> None:
    if not isinstance(manifest, EvaluationManifest):
        raise ManifestError("manifest must be an EvaluationManifest")
    if not isinstance(manifest.media_root, Path):
        raise ManifestError("media_root must be a Path")
    media_root = manifest.media_root.resolve()
    if not media_root.is_dir():
        raise ManifestError(f"media_root is not a directory: {media_root}")
    if not isinstance(manifest.references, tuple) or not all(
        isinstance(item, ReferenceImage) for item in manifest.references
    ):
        raise ManifestError("references must be a tuple of ReferenceImage values")
    if not isinstance(manifest.scans, tuple) or not all(
        isinstance(item, Scan) for item in manifest.scans
    ):
        raise ManifestError("scans must be a tuple of Scan values")
    _unique_ids(manifest.references, "reference")
    _unique_ids(manifest.scans, "scan")
    identities_by_split: dict[str, set[str]] = {
        "calibration": set(),
        "test": set(),
    }
    references_by_split: dict[str, set[str]] = {
        "calibration": set(),
        "test": set(),
    }
    scans_by_split = {"calibration": 0, "test": 0}
    for reference in manifest.references:
        _validate_id(reference.id, "reference id")
        _validate_id(reference.identity_id, "reference identity")
        _validate_media(reference.path, media_root)
        _validate_split(reference.split, "reference")
        identities_by_split[reference.split].add(reference.identity_id)
        references_by_split[reference.split].add(reference.identity_id)
    for scan in manifest.scans:
        _validate_id(scan.id, "scan id")
        _validate_media(scan.path, media_root)
        if not isinstance(scan.expected_identity_ids, tuple) or not all(
            isinstance(identity, str) and identity.strip()
            for identity in scan.expected_identity_ids
        ):
            raise ManifestError(
                "expected_identity_ids must be a tuple of non-empty strings"
            )
        if len(scan.expected_identity_ids) != len(set(scan.expected_identity_ids)):
            raise ManifestError(f"duplicate expected identity in scan {scan.id!r}")
        _validate_split(scan.split, "scan")
        scans_by_split[scan.split] += 1
        identities_by_split[scan.split].update(scan.expected_identity_ids)
        missing = set(scan.expected_identity_ids) - references_by_split[scan.split]
        if missing:
            raise ManifestError(
                f"scan {scan.id!r} has identities without a {scan.split} reference: "
                f"{', '.join(sorted(missing))}"
            )
    if not all(scans_by_split.values()):
        raise ManifestError("manifest needs calibration and test scans")
    overlap = identities_by_split["calibration"] & identities_by_split["test"]
    if overlap:
        raise ManifestError(
            "calibration and test must be identity-disjoint; overlap: "
            + ", ".join(sorted(overlap))
        )
    _validate_split_media_is_distinct(manifest)


def _validate_id(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a non-empty string")


def _validate_split(value: object, label: str) -> None:
    if not isinstance(value, str) or value not in {"calibration", "test"}:
        raise ManifestError(f"invalid {label} split: {value}")


def _validate_media(path: object, media_root: Path) -> None:
    if not isinstance(path, Path):
        raise ManifestError("media path must be a Path")
    resolved = path.resolve()
    if not resolved.is_relative_to(media_root):
        raise ManifestError(f"media path is outside media_root: {path}")
    if not resolved.is_file():
        raise ManifestError(f"media file does not exist: {resolved}")


def _validate_split_media_is_distinct(manifest: EvaluationManifest) -> None:
    hashes: dict[str, tuple[str, Path]] = {}
    items = (*manifest.references, *manifest.scans)
    for item in items:
        path = item.path.resolve()
        digest = _sha256(path)
        previous = hashes.get(digest)
        if previous is not None and previous[0] != item.split:
            raise ManifestError(
                "media reused across calibration and test: "
                f"{previous[1]} and {path}"
            )
        hashes[digest] = (item.split, path)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tables(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ManifestError(f"{key} must be an array of tables")
    return value


def _reference(item: dict[str, Any], root: Path) -> ReferenceImage:
    _validate_keys(
        item,
        "reference",
        required={"id", "identity", "path", "split"},
    )
    return ReferenceImage(
        id=_text(item, "id"),
        identity_id=_text(item, "identity"),
        path=_media_path(root, _text(item, "path")),
        split=_split(item),
    )


def _scan(item: dict[str, Any], root: Path) -> Scan:
    _validate_keys(
        item,
        "scan",
        required={"id", "path", "split", "expected_identities"},
    )
    identities = item["expected_identities"]
    if not isinstance(identities, list) or not all(
        isinstance(identity, str) and identity.strip() for identity in identities
    ):
        raise ManifestError("expected_identities must be an array of non-empty strings")
    return Scan(
        id=_text(item, "id"),
        path=_media_path(root, _text(item, "path")),
        split=_split(item),
        expected_identity_ids=tuple(identities),
    )


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{key} must be a non-empty string")
    return value


def _split(item: dict[str, Any]) -> str:
    split = _text(item, "split")
    if split not in {"calibration", "test"}:
        raise ManifestError("split must be 'calibration' or 'test'")
    return split


def _media_path(root: Path, value: str) -> Path:
    if "://" in value:
        raise ManifestError("media paths must be local")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ManifestError(f"media path escapes media_root: {value}")
    if not path.is_file():
        raise ManifestError(f"media file does not exist: {path}")
    return path


def _unique_ids(items: tuple[ReferenceImage, ...] | tuple[Scan, ...], label: str) -> None:
    ids = [item.id for item in items]
    if not all(isinstance(item_id, str) and item_id.strip() for item_id in ids):
        raise ManifestError(f"{label} id must be a non-empty string")
    if len(ids) != len(set(ids)):
        raise ManifestError(f"duplicate {label} id")


def _validate_keys(
    value: dict[str, Any], label: str, *, required: set[str]
) -> None:
    unknown = set(value) - required
    if unknown:
        raise ManifestError(f"unknown {label} fields: {', '.join(sorted(unknown))}")
    missing = required - set(value)
    if missing:
        raise ManifestError(
            f"missing required {label} fields: {', '.join(sorted(missing))}"
        )
