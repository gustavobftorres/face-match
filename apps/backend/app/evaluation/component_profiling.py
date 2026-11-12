"""Offline component timings on hash-selected public LFW images; no downloads.

Wrappers call the production/native functions unchanged. Global patches are
process-local and deliberately single-threaded; do not import into a server.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
import time
from unittest.mock import patch

from .lfw_calibration import SOURCES, digest, write_json

LIMITATIONS = (
    "Public LFW 250x250 images do not explain private 1000px multi-face workloads. "
    "Single process, sequential CPU, warm filesystem/model caches; instrumentation overhead included. "
    "No thresholds, matching decisions or embeddings are emitted. "
    "Dlib production encoder catches decode/native exceptions and returns an empty list; "
    "its no_face status therefore also includes swallowed production errors. "
    "Residual includes decode/EXIF/RGB/resize, normalization and Python overhead; "
    "these operations are not independently isolated. Dlib descriptor includes native alignment."
)


class StageTimer:
    """Exclusive spans: nested work is subtracted from its immediate parent."""

    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.seconds = defaultdict(float)
        self.stack = []

    @contextmanager
    def span(self, name):
        frame = [self.clock(), 0.0]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = self.clock() - frame[0]
            self.stack.pop()
            self.seconds[name] += elapsed - frame[1]
            if self.stack:
                self.stack[-1][1] += elapsed

    def wrap(self, name, function):
        def measured(*args, **kwargs):
            with self.span(name):
                return function(*args, **kwargs)
        return measured


class MethodProxy:
    def __init__(self, target, timer, methods):
        self.target, self.timer, self.methods = target, timer, methods

    def __getattr__(self, name):
        value = getattr(self.target, name)
        return self.timer.wrap(self.methods[name], value) if name in self.methods else value


@contextmanager
def instrument_dlib(timer, api=None):
    if api is None:
        import face_recognition.api as api
    with ExitStack() as stack:
        for name, stage in (("_raw_face_locations", "detector"),
                            ("_raw_face_landmarks", "landmarks")):
            stack.enter_context(patch.object(api, name, timer.wrap(stage, getattr(api, name))))
        stack.enter_context(patch.object(api, "face_encoder", MethodProxy(
            api.face_encoder, timer, {"compute_face_descriptor": "embedding_native_alignment"})))
        yield


@contextmanager
def instrument_yunet(timer, runtime, module=None):
    if module is None:
        from . import yunet_auraface as module
    with ExitStack() as stack:
        stack.enter_context(patch.object(runtime, "_detect_faces", timer.wrap("detector", runtime._detect_faces)))
        stack.enter_context(patch.object(module, "_similarity_transform", timer.wrap("landmarks_alignment", module._similarity_transform)))
        stack.enter_context(patch.object(runtime, "cv2", MethodProxy(runtime.cv2, timer, {"warpAffine": "landmarks_alignment"})))
        stack.enter_context(patch.object(runtime, "session", MethodProxy(runtime.session, timer, {"run": "embedding"})))
        yield


def select_images(manifest, count=100):
    """Only content hashes and public paths influence selection; no labels/scores."""
    if count < 1 or len(manifest) < count + 1:
        raise ValueError("requires separate warmup plus requested sample count")
    ordered = sorted(manifest, key=lambda name: (manifest[name], name))
    return ordered[0], ordered[1:count + 1]


def verified_public_manifest(root):
    root = Path(root).resolve(strict=True)
    protocol = json.loads((root / "protocol.json").read_text())
    if protocol.get("dataset") != "LFW View 1 pairsDevTrain":
        raise ValueError("requires public LFW View 1 source protocol")
    manifest_path = root / "image-sha256.json"
    if digest(manifest_path) != protocol["image_hash_manifest_sha256"]:
        raise ValueError("public image manifest checksum mismatch")
    for name, source in SOURCES.items():
        if digest(root / name) != source["digest"]:
            raise ValueError(f"public source checksum mismatch: {name}")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or len(manifest) != protocol["images"]:
        raise ValueError("invalid image manifest")
    for name, expected in manifest.items():
        relative = PurePosixPath(name)
        if (not re.fullmatch(r"lfw/[A-Za-z][A-Za-z_'\-]*/[A-Za-z][A-Za-z_'\-]*_[0-9]{4}\.jpg", name)
                or relative.is_absolute() or ".." in relative.parts
                or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise ValueError("invalid public LFW manifest entry")
        path = root / name
        if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.resolve().is_relative_to(root):
            raise ValueError("symlink or escaped public image path")
        if digest(path) != expected:
            raise ValueError(f"public image checksum mismatch: {name}")
    return manifest, protocol


def assert_parity(original, observed):
    import numpy as np
    original, observed = tuple(original), tuple(observed)
    if len(original) != len(observed):
        raise ValueError("instrumentation changed face count")
    for left, right in zip(original, observed):
        if not np.array_equal(np.asarray(left), np.asarray(right)):
            raise ValueError("instrumentation changed embedding")
    return {"face_count_equal": True, "embeddings_checked": len(original), "exact_equal": True}


def measure_one(name, encode, instrument, *, distance=None, reference=None, clock=time.perf_counter):
    timer = StageTimer(clock)
    result = {"image": name, "status": "error", "faces": None}
    started = clock()
    try:
        with instrument(timer), timer.span("decode_exif_rgb_resize_and_python_residual"):
            vectors = tuple(encode(timer))
        result.update(status="completed" if vectors else "no_face", faces=len(vectors))
        if reference is not None and vectors and distance is not None:
            with timer.span("distance"):
                # Fixed warmup reference against every observed face, no threshold.
                for vector in vectors:
                    distance(reference, vector)
            result["distance_comparisons"] = len(vectors)
        else:
            result["distance_comparisons"] = 0
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    total = clock() - started
    measured = dict(timer.seconds)
    measured["instrumentation_and_dispatch_residual"] = total - sum(measured.values())
    result.update(total_seconds=total, stages_seconds=measured)
    return result


def summarize(rows):
    def stats(values):
        ordered = sorted(values)
        def percentile(q):
            position = (len(ordered) - 1) * q
            lower = math.floor(position)
            return ordered[lower] + (ordered[math.ceil(position)] - ordered[lower]) * (position - lower)
        return {"sum_seconds": sum(values), "p50_seconds": percentile(.5), "p95_seconds": percentile(.95)}
    stages = sorted({stage for row in rows for stage in row["stages_seconds"]})
    total_faces = sum(row["faces"] or 0 for row in rows)
    embedding_seconds = sum(sum(value for name, value in row["stages_seconds"].items()
                                if name in ("embedding", "embedding_native_alignment")) for row in rows)
    return {"images": len(rows), "total_observed_faces": total_faces,
            "embedding_seconds_total": embedding_seconds,
            "embedding_seconds_per_observed_face": embedding_seconds / total_faces if total_faces else None,
            "population": "all attempted images including zero-face/errors; per-face denominator is observed faces, which may differ across detectors",
            "status_counts": {key: sum(row["status"] == key for row in rows) for key in ("completed", "no_face", "error")},
            "total": stats([row["total_seconds"] for row in rows]),
            "stages": {stage: stats([row["stages_seconds"].get(stage, 0.0) for row in rows]) for stage in stages}}


def _versions():
    result = {}
    for name in ("face-recognition", "face-recognition-models", "dlib", "numpy", "Pillow", "opencv-python-headless", "onnxruntime"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def run(source, output, models):
    from .yunet_auraface import YunetAuraFaceAdapter, _NativeRuntime, _normalized
    from .face_search import _default_encoder, _default_distance
    source, output, models = Path(source).resolve(), Path(output).resolve(), Path(models).resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("output must be separate from public source")
    if (output / "protocol.json").exists():
        raise ValueError("profiling protocol already frozen; use a new output directory")
    if output.exists():
        raise ValueError("output directory already exists; use a new output directory")
    manifest, source_protocol = verified_public_manifest(source)
    warmup, selected = select_images(manifest)
    adapter = YunetAuraFaceAdapter(models / "face_detection_yunet_2023mar.onnx", models / "glintr100.onnx",
        yunet_sha256=source_protocol["adapter"]["models"]["yunet"]["sha256"],
        auraface_sha256=source_protocol["adapter"]["models"]["auraface"]["sha256"])
    if digest(Path(__file__).with_name("yunet_auraface.py")) != source_protocol["implementation_sha256"]["yunet_auraface.py"]:
        raise ValueError("YuNet implementation differs from frozen public calibration")
    import face_recognition.api as api
    import face_recognition_models
    import inspect
    dlib_models = {name: digest(getattr(face_recognition_models, name)()) for name in
        ("pose_predictor_model_location", "pose_predictor_five_point_model_location", "face_recognition_model_location", "cnn_face_detector_model_location")}
    dlib_binary = find_spec("_dlib_pybind11")
    if dlib_binary is None or dlib_binary.origin is None:
        raise ValueError("cannot locate native dlib binary for provenance")
    source_files = {Path(dlib_binary.origin), Path(__file__), Path(__file__).with_name("face_search.py"), Path(__file__).with_name("yunet_auraface.py"),
                    Path(__file__).parents[1] / "services" / "ai_service.py", Path(inspect.getfile(api))}
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "dataset": "LFW View 1 pairsDevTrain",
        "selection": "sort (image SHA256, public path); first warmup, next 100 timed; no labels or scores read",
        "source_protocol_sha256": digest(source / "protocol.json"), "image_hash_manifest_sha256": digest(source / "image-sha256.json"),
        "warmup": {"image": warmup, "sha256": manifest[warmup]},
        "selected": [{"image": name, "sha256": manifest[name]} for name in selected],
        "source_sha256": {str(path): digest(path) for path in sorted(source_files)},
        "dlib": {"adapter": "DlibProductionAdapter encoder/_default_distance", "max_image_dimension": 1000,
                 "face_encodings_defaults": {"known_face_locations": None, "num_jitters": 1, "model": "small"},
                 "detector_defaults": {"model": "hog", "number_of_times_to_upsample": 1}, "model_sha256": dlib_models},
        "yunet_auraface": adapter.describe(), "runtime_versions": _versions(), "executable": sys.executable,
        "timing": "perf_counter exclusive spans; stages include zeros for unreached work; errors included; sequential dlib then yunet",
        "parity": "one untimed baseline and wrapped warmup per model, exact vector equality; timed 100 are not repeated",
        "distance": "warmup first face fixed reference; every timed observed face; unavailable if warmup has zero faces",
        "limitations": LIMITATIONS}
    output.mkdir(parents=True, exist_ok=True)
    # This immutable receipt exists before either model's first inference.
    with (output / "protocol.json").open("x") as stream:
        stream.write(json.dumps(protocol, sort_keys=True, indent=2, allow_nan=False) + "\n")
    runtime = _NativeRuntime(adapter)
    if runtime.providers != ["CPUExecutionProvider"]:
        raise ValueError("requires active CPUExecutionProvider only")
    backends = {
        "dlib": (lambda path, timer: _default_encoder(timer.wrap("read_bytes", path.read_bytes)()), instrument_dlib, _default_distance),
        "yunet_auraface": (lambda path, timer: runtime.encode(path), lambda timer: instrument_yunet(timer, runtime),
                            lambda known, observed: float(max(-1.0, min(1.0, _normalized(known) @ _normalized(observed))))),
    }
    session_options = runtime.session.get_session_options()
    parallel_framework = [line.strip() for line in runtime.cv2.getBuildInformation().splitlines()
                          if "Parallel framework:" in line]
    receipt = {"protocol_sha256": digest(output / "protocol.json"), "active_yunet_providers": runtime.providers,
               "observed_runtime": {
                   "ort_intra_op_threads": session_options.intra_op_num_threads,
                   "ort_inter_op_threads": session_options.inter_op_num_threads,
                   "ort_providers": runtime.session.get_providers(),
                   "opencv_num_threads": runtime.cv2.getNumThreads(),
                   "opencv_parallel_framework": parallel_framework,
                   "opencv_detector_backend": "DNN_BACKEND_OPENCV/DNN_TARGET_CPU (constructor arguments; no getter available)",
                   "thread_limitations": "OpenCV getNumThreads reports configuration, not measured worker count; GCD may ignore thread limits. ORT options do not establish total process thread count."},
               "backends": {}}
    for backend, (encoder, instrument, distance) in backends.items():
        baseline = tuple(encoder(source / warmup, StageTimer()))
        with instrument(StageTimer()):
            wrapped = tuple(encoder(source / warmup, StageTimer()))
        parity = assert_parity(baseline, wrapped)
        reference = baseline[0] if baseline else None
        rows = []
        with (output / f"{backend}-timings.jsonl").open("x") as stream:
            for index, name in enumerate(selected, 1):
                row = measure_one(name, lambda timer, name=name: encoder(source / name, timer), instrument,
                                  distance=distance, reference=reference)
                rows.append(row)
                stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                if index % 10 == 0:
                    print(f"{backend}: {index}/100", flush=True)
        receipt["backends"][backend] = {"parity": parity, "distance_reference_available": reference is not None,
            "summary": summarize(rows), "timings_sha256": digest(output / f"{backend}-timings.jsonl")}
        write_json(output / "result.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.models), indent=2, allow_nan=False))
