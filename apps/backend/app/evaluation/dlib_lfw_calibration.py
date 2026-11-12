"""Calibrate production Dlib on verified local LFW View 1 data, without downloads."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path, PurePosixPath
import platform
import sys
import time

from .face_search import DlibProductionAdapter
from .lfw_calibration import SOURCES, digest, parse_pairs, write_json
from .models import ReferenceImage, Scan

TARGET_FPR = 0.001
MIN_COMPLETED_PER_CLASS = 500
# The image inventory frozen by the preceding public LFW acquisition.
IMAGE_MANIFEST_SHA256 = "d275b321d48a1ca48b58bad9b1da0d9ededcc5536b663f8e42e1b180bd49e811"


def select_threshold(rows):
    completed = [row for row in rows if row.get("score") is not None]
    positive = [row["score"] for row in completed if row["mated"]]
    negative = [row["score"] for row in completed if not row["mated"]]
    if min(len(positive), len(negative)) < MIN_COMPLETED_PER_CLASS:
        raise ValueError("insufficient completed pairs: requires at least 500 per class")
    scores = positive + negative
    if any(type(score) not in (float, int) or not math.isfinite(score) or score > 0 for score in scores):
        raise ValueError("scores must be finite nonpositive negative distances")
    candidates = set(scores)
    accept_all = math.nextafter(min(scores), -math.inf)
    if math.isfinite(accept_all):
        candidates.add(accept_all)
    ranked = []
    for threshold in candidates:
        tp = sum(score > threshold for score in positive)
        fp = sum(score > threshold for score in negative)
        if fp / len(negative) <= TARGET_FPR:
            ranked.append((tp, threshold, fp))
    # max(observed scores) always supplies a finite reject-all candidate.
    tp, threshold, fp = max(ranked)
    return {"score_threshold": threshold, "distance_threshold": -threshold,
            "comparator": ">", "distance_comparator": "<", "score_semantics": "negative_distance",
            "target_fpr": TARGET_FPR, "tp": tp, "fp": fp,
            "completed_mated": len(positive), "completed_nonmated": len(negative),
            "empirical_tpr": tp / len(positive), "empirical_fpr": fp / len(negative)}


def confined_file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe local data path")
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("symlink local data path")
    if not candidate.resolve().is_relative_to(root) or not candidate.is_file():
        raise ValueError("missing or unconfined local data file")
    return candidate


def verify_local_data(source):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("symlink source root")
    source = source.resolve(strict=True)
    for filename, spec in SOURCES.items():
        path = confined_file(source, filename)
        if path.stat().st_size > spec["max_bytes"] or digest(path, spec["algorithm"]) != spec["digest"]:
            raise ValueError(f"pinned checksum mismatch: {filename}")
    pairs = parse_pairs(confined_file(source, "pairsDevTrain.txt").read_text())
    manifest = confined_file(source, "image-sha256.json")
    if digest(manifest) != IMAGE_MANIFEST_SHA256:
        raise ValueError("pinned image manifest checksum mismatch")
    expected = json.loads(manifest.read_text())
    required = {pair[key] for pair in pairs for key in ("reference", "scan")}
    if set(expected) != required:
        raise ValueError("image inventory differs from required pairs")
    for relative in sorted(required):
        if digest(confined_file(source, relative)) != expected[relative]:
            raise ValueError(f"image checksum mismatch: {relative}")
    return source, pairs, expected


def runtime_provenance():
    # Importing these packages loads weights but performs no image inference.
    import _dlib_pybind11
    import dlib
    import face_recognition.api as api
    import face_recognition_models as models
    from app.services import ai_service

    paths = {"face_recognition_api": Path(api.__file__),
             "dlib_python": Path(dlib.__file__), "dlib_binary": Path(_dlib_pybind11.__file__),
             "landmarks_small_5": Path(models.pose_predictor_five_point_model_location()),
             "face_descriptor_resnet": Path(models.face_recognition_model_location()),
             "model_locator": Path(models.__file__)}
    implementation = {"dlib_lfw_calibration.py": Path(__file__),
                      "lfw_calibration.py": Path(__file__).with_name("lfw_calibration.py"),
                      "face_search.py": Path(__file__).with_name("face_search.py"),
                      "ai_service.py": Path(ai_service.__file__)}
    return {"python": sys.version, "platform": platform.platform(),
            "packages": {name: metadata.version(name) for name in
                         ("face-recognition", "face-recognition-models", "dlib", "numpy", "Pillow")},
            "model_usage": {"detector": "compiled HOG detector in hashed Dlib binary",
                            "landmarks": "small five-point predictor",
                            "descriptor": "ResNet model",
                            "unused": "face_recognition.api also loads 68-point and CNN weights on import; neither is used by production defaults"},
            "runtime_files": {name: {"path": str(path), "sha256": digest(path)} for name, path in paths.items()},
            "implementation_sha256": {name: digest(path) for name, path in implementation.items()},
            "preprocessing": {"exif_transpose": True, "mode": "RGB", "max_dimension": ai_service.MAX_IMAGE_DIMENSION,
                              "resize": "Pillow thumbnail LANCZOS when dimension exceeds maximum",
                              "face_encodings_defaults": {"num_jitters": 1, "model": "small"},
                              "face_locations_defaults": {"model": "hog", "number_of_times_to_upsample": 1}}}


class MemoEncoder:
    """Cache unchanged ordered production encodings by input byte SHA256."""

    def __init__(self, encoder):
        self.encoder = encoder
        self.cache = {}
        self.calls = 0
        self.hits = 0

    def __call__(self, content):
        self.calls += 1
        key = hashlib.sha256(content).hexdigest()
        if key in self.cache:
            self.hits += 1
        else:
            try:
                self.cache[key] = tuple(self.encoder(content))
            except Exception as exc:
                self.cache[key] = exc
        result = self.cache[key]
        if isinstance(result, Exception):
            raise result
        return result


def run(source, output):
    source, pairs, image_hashes = verify_local_data(source)
    output = Path(output)
    if output.is_symlink():
        raise ValueError("symlink output directory")
    output = output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("source and output directories must be separate")
    provenance = runtime_provenance()
    from app.services.ai_service import get_face_encodings
    memo = MemoEncoder(get_face_encodings)
    adapter = DlibProductionAdapter(encoder=memo)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "image-sha256.json", image_hashes)
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(),
                "dataset": "LFW View 1 pairsDevTrain", "source_directory": str(source),
                "source_metadata": SOURCES, "image_hash_manifest_sha256": digest(output / "image-sha256.json"),
                "pairs": 2200, "mated": 1100, "nonmated": 1100, "images": len(image_hashes),
                "adapter": "app.evaluation.face_search:DlibProductionAdapter", "runtime": provenance,
                "objective": "maximum completed-pair empirical TPR with empirical FPR <= 0.001; ties choose stricter (higher) threshold",
                "target_fpr": TARGET_FPR, "minimum_completed_per_class": MIN_COMPLETED_PER_CLASS,
                "score_semantics": "negative_distance", "comparator": ">", "distance_comparator": "<",
                "candidate_thresholds": "unique observed scores plus finite nextafter(min_score,-inf); observed maximum rejects all",
                "acquisition_policy": "first image reference, first encoding even if multiple; second image scan, max negative distance across all encodings; scan encoded first; no swaps",
                "failure_policy": "errors and no-face excluded from fitting, separately reported; neither accepts; production encoder swallowed exceptions return empty encodings and cannot be distinguished from acquisition failure",
                "media": "original full 250x250 RGB LFW images; production preprocessing; no sklearn crop/grayscale",
                "timing": "encoding memoization by byte SHA256; reference cache preserved; not a performance benchmark",
                "limitations": "in-sample calibration, not independent validation; LFW central-face labels versus any scan face; possible Dlib pretraining overlap unknown; no private-domain accuracy claim"}
    write_json(output / "protocol.json", protocol)
    protocol_hash = digest(output / "protocol.json")
    rows = []
    started = time.monotonic()
    with (output / "scores.jsonl").open("x") as stream:
        for pair in pairs:
            reference = ReferenceImage(str(pair["index"]), "reference", source / pair["reference"], "calibration")
            scan = Scan(str(pair["index"]), source / pair["scan"], "calibration", ("reference",) if pair["mated"] else ())
            result = adapter.search((reference,), scan)
            row = dict(pair, score=result.scores[0].score if result.scores else None,
                       has_face=result.has_face, error=result.error,
                       status="error" if result.error else "completed" if result.scores else "no_face")
            if row["score"] is not None and (not math.isfinite(row["score"]) or row["score"] > 0):
                raise ValueError("adapter returned invalid negative distance")
            rows.append(row)
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            if pair["index"] % 100 == 0:
                print(f"{pair['index']}/2200 pairs; {(time.monotonic()-started)/60:.1f} min", flush=True)
    selection = select_threshold(rows)
    for row in rows:
        row["accepted"] = row["score"] is not None and row["score"] > selection["score_threshold"]
    write_json(output / "decisions.json", rows)
    coverage = {label: {"total": sum(row["mated"] == mated for row in rows),
                        **{status: sum(row["mated"] == mated and row["status"] == status for row in rows)
                           for status in ("completed", "no_face", "error")},
                        "end_to_end_misses": sum(row["mated"] == mated and not row["accepted"] for row in rows) if mated else None}
                for label, mated in (("mated", True), ("nonmated", False))}
    receipt = {"protocol_sha256": protocol_hash, "protocol_path": str(output / "protocol.json"),
               "source_metadata": SOURCES, "image_hash_manifest_sha256": digest(output / "image-sha256.json"),
               "adapter": {"identity": protocol["adapter"], "score_semantics": "negative_distance",
                           "runtime": provenance},
               "selection": selection, "coverage": coverage,
               "scores_sha256": digest(output / "scores.jsonl"), "decisions_sha256": digest(output / "decisions.json"),
               "end_to_end_mated_tpr": selection["tp"] / 1100, "end_to_end_nonmated_fpr": selection["fp"] / 1100,
               "end_to_end_error_policy": protocol["failure_policy"],
               "memoization": {"encoder_calls": memo.calls, "hits": memo.hits, "unique_contents": len(memo.cache)},
               "elapsed_seconds_with_memoization": time.monotonic() - started}
    write_json(output / "threshold-result.json", receipt)
    print(json.dumps(receipt, indent=2), flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/private/tmp/face-match-lfw-calibration"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
