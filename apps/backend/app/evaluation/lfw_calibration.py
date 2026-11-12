"""Public LFW View 1 calibration, isolated from private evaluation media."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import tarfile
import time

SOURCES = {
    "pairsDevTrain.txt": {"url": "https://ndownloader.figshare.com/files/5976012", "algorithm": "sha256", "digest": "1d454dada7dfeca0e7eab6f65dc4e97a6312d44cf142207be28d688be92aabfa", "max_bytes": 300000},
    "lfw.tgz": {"url": "https://ndownloader.figshare.com/files/5976018", "algorithm": "sha256", "digest": "055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0", "max_bytes": 250000000},
}
TARGET_FPR = 0.001
MIN_COMPLETED_PER_CLASS = 500


def digest(path, algorithm="sha256"):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def parse_pairs(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "1100" or len(lines) != 2201:
        raise ValueError("requires View 1 pairsDevTrain: header 1100 and 2200 rows")
    pairs = []
    for index, raw in enumerate(lines[1:], 1):
        fields = raw.split()
        mated = index <= 1100
        if len(fields) != (3 if mated else 4):
            raise ValueError(f"invalid pair row {index}")
        name1, number1 = fields[:2]
        name2, number2 = (name1, fields[2]) if mated else fields[2:]
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z_'-]*", name) for name in (name1, name2)):
            raise ValueError("invalid LFW identity")
        if any(not re.fullmatch(r"[0-9]+", number) or not 1 <= int(number) <= 9999 for number in (number1, number2)):
            raise ValueError("invalid LFW image number")
        if (mated and number1 == number2) or (not mated and name1 == name2):
            raise ValueError("pair label contradicts identities")
        image = lambda name, number: f"lfw/{name}/{name}_{int(number):04d}.jpg"
        pairs.append({"index": index, "raw": raw, "mated": mated,
                      "reference": image(name1, number1), "scan": image(name2, number2)})
    return pairs


def select_threshold(rows):
    completed = [row for row in rows if row.get("score") is not None]
    positive = [row["score"] for row in completed if row["mated"]]
    negative = [row["score"] for row in completed if not row["mated"]]
    if min(len(positive), len(negative)) < MIN_COMPLETED_PER_CLASS:
        raise ValueError("insufficient completed pairs: requires at least 500 per class")
    scores = positive + negative
    if any(type(score) not in (float, int) or not math.isfinite(score) or not -1 <= score <= 1 for score in scores):
        raise ValueError("scores must be finite normalized cosine values")
    candidates = set(scores)
    reject_all = math.nextafter(max(scores), math.inf)
    if reject_all <= 1:
        candidates.add(reject_all)
    ranked = []
    for threshold in candidates:
        tp = sum(score >= threshold for score in positive)
        fp = sum(score >= threshold for score in negative)
        if fp / len(negative) <= TARGET_FPR:
            ranked.append((tp, threshold, fp))
    if not ranked:
        raise ValueError("no finite threshold in [-1,1] satisfies FPR constraint")
    tp, threshold, fp = max(ranked)
    return {"threshold": threshold, "comparator": ">=", "target_fpr": TARGET_FPR,
            "tp": tp, "fp": fp, "completed_mated": len(positive), "completed_nonmated": len(negative),
            "empirical_tpr": tp / len(positive), "empirical_fpr": fp / len(negative)}


def download(root, filename):
    import requests
    source = SOURCES[filename]
    target = root / filename
    if target.exists() and digest(target, source["algorithm"]) == source["digest"]:
        return target
    partial = target.with_suffix(target.suffix + ".partial")
    for attempt in range(3):
        try:
            # Query avoids a cached, expired signed object-store redirect.
            with requests.get(source["url"], params={"download": "1", "request": str(time.time_ns())},
                              stream=True, timeout=(20, 90)) as response:
                response.raise_for_status()
                total = 0
                with partial.open("wb") as stream:
                    for block in response.iter_content(1024 * 1024):
                        total += len(block)
                        if total > source["max_bytes"]:
                            raise ValueError("download exceeds declared size limit")
                        stream.write(block)
            if digest(partial, source["algorithm"]) != source["digest"]:
                raise ValueError(f"checksum mismatch: {filename}")
            partial.replace(target)
            return target
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            retry = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After", "5")
            try:
                delay = float(retry)
            except ValueError:
                delay = 30
            if delay > 60:
                raise RuntimeError("server requests long retry; retry this run later") from exc
            time.sleep(max(5, delay))
    raise RuntimeError("download failed")


def extract_images(archive, root, required):
    """Copy only explicitly listed JPEGs, never tar extract paths or links."""
    root = Path(root)
    if root.is_symlink():
        raise ValueError("symlink extraction root")
    root = root.resolve()
    required = set(required)
    found = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError("unsafe archive member")
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) != 3 or path.parts[0] != "lfw" or path.suffix != ".jpg":
                raise ValueError("unexpected archive member")
            if not 0 < member.size <= 10000000:
                raise ValueError("invalid archive image size")
            if member.name not in required:
                continue
            if member.name in found:
                raise ValueError("duplicate archive image")
            destination = root / member.name
            for parent in (root / "lfw", destination.parent):
                if parent.is_symlink():
                    raise ValueError("symlink extraction directory")
            if not destination.resolve().is_relative_to(root):
                raise ValueError("destination outside extraction root")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as stream, destination.open("xb") as output:
                output.write(stream.read(member.size + 1))
            found.add(member.name)
    if found != required:
        raise ValueError("archive missing required images")
    return {name: digest(root / name) for name in sorted(found)}


def run(root, model_root):
    from .models import ReferenceImage, Scan
    from .yunet_auraface import YunetAuraFaceAdapter, _NativeRuntime
    root.mkdir(parents=True, exist_ok=True)
    if (root / "protocol.json").exists():
        raise ValueError("run directory already frozen; use a new directory")
    pairs_path = download(root, "pairsDevTrain.txt")
    pairs = parse_pairs(pairs_path.read_text())
    archive = download(root, "lfw.tgz")
    required = {pair[key] for pair in pairs for key in ("reference", "scan")}
    image_hashes = extract_images(archive, root, required)
    write_json(root / "image-sha256.json", image_hashes)
    adapter = YunetAuraFaceAdapter(model_root / "face_detection_yunet_2023mar.onnx", model_root / "glintr100.onnx")
    adapter._runtime = _NativeRuntime(adapter)
    native = adapter._runtime
    class MemoRuntime:
        providers = native.providers
        def __init__(self):
            self.cache = {}
        def encode(self, path):
            if path not in self.cache:
                try:
                    self.cache[path] = tuple(native.encode(path))
                except Exception as exc:
                    self.cache[path] = exc
            value = self.cache[path]
            if isinstance(value, Exception):
                raise value
            return value
    adapter._runtime = MemoRuntime()
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "dataset": "LFW View 1 pairsDevTrain",
                "source_metadata": SOURCES, "source_documentation": "https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/datasets/_lfw.py",
                "pairs": 2200, "mated": 1100, "nonmated": 1100, "images": len(required),
                "image_hash_manifest_sha256": digest(root / "image-sha256.json"),
                "implementation_sha256": {"lfw_calibration.py": digest(Path(__file__)), "yunet_auraface.py": digest(Path(__file__).with_name("yunet_auraface.py"))},
                "adapter": adapter.describe(), "objective": "maximum completed-pair empirical TPR with empirical FPR <= 0.001; ties choose stricter threshold",
                "comparator": ">=", "candidate_thresholds": "unique observed scores plus nextafter(max,+inf) if <=1",
                "minimum_completed_per_class": MIN_COMPLETED_PER_CLASS,
                "acquisition_policy": "reference exactly one face; scan max cosine across any face; errors/no-face excluded from fitting and reported separately; no swaps",
                "media": "original full 250x250 RGB images; frozen adapter preprocessing; no sklearn crop/grayscale",
                "limitations": "LFW labels refer to central face; max-over-all scan faces can include other people; calibration statistics are in-sample, not independent validation; possible AuraFace pretraining overlap with LFW is UNKNOWN, training independence is not claimed",
                "timing": "embedding memoization; not a performance benchmark"}
    write_json(root / "protocol.json", protocol)
    protocol_hash = digest(root / "protocol.json")
    rows = []
    started = time.monotonic()
    with (root / "scores.jsonl").open("x") as output:
        for pair in pairs:
            reference = ReferenceImage(str(pair["index"]), "reference", root / pair["reference"], "calibration")
            scan = Scan(str(pair["index"]), root / pair["scan"], "calibration", ("reference",) if pair["mated"] else ())
            result = adapter.search((reference,), scan)
            row = dict(pair, score=result.scores[0].score if result.scores else None,
                       has_face=result.has_face, error=result.error,
                       status="error" if result.error else "completed" if result.scores else "no_face")
            rows.append(row)
            output.write(json.dumps(row, allow_nan=False) + "\n")
            output.flush()
            if pair["index"] % 100 == 0:
                print(f"{pair['index']}/2200 pairs; {(time.monotonic()-started)/60:.1f} min", flush=True)
    selection = select_threshold(rows)
    threshold = selection["threshold"]
    for row in rows:
        row["accepted"] = row["score"] is not None and row["score"] >= threshold
    write_json(root / "decisions.json", rows)
    coverage = {label: {"total": sum(row["mated"] == mated for row in rows),
                        **{status: sum(row["mated"] == mated and row["status"] == status for row in rows) for status in ("completed", "no_face", "error")},
                        "end_to_end_misses": sum(row["mated"] == mated and not row["accepted"] for row in rows) if mated else None}
                for label, mated in (("mated", True), ("nonmated", False))}
    receipt = {"protocol_sha256": protocol_hash, "protocol_path": str(root / "protocol.json"),
               "source_metadata": SOURCES, "image_hash_manifest_sha256": digest(root / "image-sha256.json"),
               "adapter": adapter.describe(), "selection": selection, "coverage": coverage,
               "scores_sha256": digest(root / "scores.jsonl"), "decisions_sha256": digest(root / "decisions.json"),
               "end_to_end_mated_tpr": selection["tp"] / 1100,
               "end_to_end_nonmated_fpr": selection["fp"] / 1100,
               "end_to_end_error_policy": "errors and no-face produce no acceptance; mated errors count as end-to-end misses"}
    write_json(root / "threshold-result.json", receipt)
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.models.resolve())
