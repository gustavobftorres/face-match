from types import SimpleNamespace

import numpy as np
import pytest

from app.evaluation.component_profiling import (
    StageTimer, assert_parity, instrument_dlib, instrument_yunet,
    measure_one, select_images, summarize,
)


def test_exclusive_nested_spans_reconcile_and_record_failures():
    ticks = iter([0, 1, 4, 10])
    timer = StageTimer(lambda: next(ticks))
    with pytest.raises(RuntimeError):
        with timer.span("outer"):
            with timer.span("inner"):
                raise RuntimeError("failure")
    assert timer.seconds == {"inner": 3, "outer": 7}
    assert not timer.stack


def test_selection_has_separate_warmup_hash_order_and_path_tiebreak():
    manifest = {"z": "b", "b": "a", "a": "a", "c": "c"}
    assert select_images(manifest, 2) == ("a", ["b", "z"])
    assert select_images(dict(reversed(list(manifest.items()))), 2) == ("a", ["b", "z"])
    with pytest.raises(ValueError):
        select_images(manifest, 4)


def test_dlib_wrappers_preserve_inputs_outputs_defaults_and_restore_after_failure():
    calls = []
    def locations(image, *args, **kwargs):
        calls.append(("detector", image, args, kwargs))
        return ["rect"]
    api = SimpleNamespace(_raw_face_locations=locations)
    def landmarks(image, *args, **kwargs):
        assert api._raw_face_locations(image) == ["rect"]
        calls.append(("landmarks", image, args, kwargs))
        return ["landmark"]
    api._raw_face_landmarks = landmarks
    descriptor = SimpleNamespace(compute_face_descriptor=lambda *args, **kwargs: (args, kwargs))
    api.face_encoder = descriptor
    image = object()
    timer = StageTimer()
    with pytest.raises(RuntimeError):
        with instrument_dlib(timer, api):
            assert api._raw_face_landmarks(image, model="small") == ["landmark"]
            payload = api.face_encoder.compute_face_descriptor(image, "landmark", 1)
            assert payload == ((image, "landmark", 1), {})
            raise RuntimeError("intentional")
    assert api.face_encoder is descriptor
    assert api._raw_face_landmarks is landmarks
    assert api._raw_face_locations is locations
    assert calls == [("detector", image, (), {}), ("landmarks", image, (), {"model": "small"})]
    assert set(timer.seconds) == {"detector", "landmarks", "embedding_native_alignment"}


def test_yunet_wrappers_keep_exact_payloads_and_original_return_objects():
    sentinel = object()
    calls = []
    def called(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel
    module = SimpleNamespace(_similarity_transform=called)
    cv2, session = SimpleNamespace(warpAffine=called), SimpleNamespace(run=called)
    runtime = SimpleNamespace(_detect_faces=called, cv2=cv2, session=session)
    timer = StageTimer()
    with instrument_yunet(timer, runtime, module):
        for function in (runtime._detect_faces, module._similarity_transform, runtime.cv2.warpAffine, runtime.session.run):
            assert function(sentinel, flag=1) is sentinel
    assert runtime.cv2 is cv2 and runtime.session is session
    assert calls == [((sentinel,), {"flag": 1})] * 4
    assert set(timer.seconds) == {"detector", "landmarks_alignment", "embedding"}


def test_measure_totals_include_failure_and_summary_uses_zero_for_unreached_stages():
    from contextlib import nullcontext
    def encode(timer):
        with timer.span("detector"):
            raise ValueError("broken")
    row = measure_one("public", encode, lambda timer: nullcontext())
    assert row["status"] == "error" and row["error"] == "ValueError: broken"
    assert sum(row["stages_seconds"].values()) == pytest.approx(row["total_seconds"], abs=1e-12)
    empty = {"status": "no_face", "faces": 0, "total_seconds": 0, "stages_seconds": {}}
    summary = summarize([row, empty])
    assert summary["status_counts"] == {"completed": 0, "no_face": 1, "error": 1}
    assert summary["stages"]["detector"]["p50_seconds"] == row["stages_seconds"]["detector"] / 2


def test_distance_uses_fixed_reference_all_faces_and_persists_no_vectors():
    from contextlib import nullcontext
    calls = []
    row = measure_one("public", lambda timer: [np.ones(2), np.zeros(2)], lambda timer: nullcontext(),
                      reference="fixed", distance=lambda reference, vector: calls.append((reference, vector)))
    assert row["faces"] == row["distance_comparisons"] == len(calls) == 2
    assert all(reference == "fixed" for reference, _ in calls)
    summary = summarize([row])
    assert summary["total_observed_faces"] == 2
    assert summary["embedding_seconds_total"] == 0
    assert summary["embedding_seconds_per_observed_face"] == 0
    assert "vectors" not in row
    assert sum(row["stages_seconds"].values()) == pytest.approx(row["total_seconds"])


def test_parity_requires_exact_embeddings_and_reports_zero_faces_honestly():
    assert assert_parity([], []) == {"face_count_equal": True, "embeddings_checked": 0, "exact_equal": True}
    assert assert_parity([np.ones(128)], [np.ones(128)])["embeddings_checked"] == 1
    with pytest.raises(ValueError, match="count"):
        assert_parity([], [np.ones(128)])
    with pytest.raises(ValueError, match="embedding"):
        assert_parity([np.ones(128)], [np.ones(128) + 1e-12])


def test_protocol_and_selection_exist_before_native_runtime_or_any_inference(tmp_path, monkeypatch):
    import hashlib
    import json
    import sys
    from types import ModuleType
    from app.evaluation import component_profiling as profiler
    from app.evaluation import yunet_auraface as yunet
    source, output, models = (tmp_path / name for name in ("source", "output", "models"))
    source.mkdir()
    models.mkdir()
    manifest = {}
    for index in range(101):
        relative = f"lfw/Person/Person_{index + 1:04d}.jpg"
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(str(index).encode())
        manifest[relative] = profiler.digest(path)
    profiler.write_json(source / "image-sha256.json", manifest)
    for name in ("face_detection_yunet_2023mar.onnx", "glintr100.onnx"):
        (models / name).write_bytes(b"local model fixture")
    model_hash = hashlib.sha256(b"local model fixture").hexdigest()
    profiler.write_json(source / "protocol.json", {
        "dataset": "LFW View 1 pairsDevTrain", "images": 101,
        "image_hash_manifest_sha256": profiler.digest(source / "image-sha256.json"),
        "implementation_sha256": {"yunet_auraface.py": profiler.digest(yunet.__file__)},
        "adapter": {"models": {key: {"sha256": model_hash} for key in ("yunet", "auraface")}},
    })
    monkeypatch.setattr(profiler, "SOURCES", {})
    api = ModuleType("face_recognition.api")
    api.__file__ = __file__
    package = ModuleType("face_recognition")
    package.api = api
    monkeypatch.setitem(sys.modules, "face_recognition", package)
    monkeypatch.setitem(sys.modules, "face_recognition.api", api)
    model_module = ModuleType("face_recognition_models")
    for name in ("pose_predictor_model_location", "pose_predictor_five_point_model_location", "face_recognition_model_location", "cnn_face_detector_model_location"):
        setattr(model_module, name, lambda: models / "glintr100.onnx")
    monkeypatch.setitem(sys.modules, "face_recognition_models", model_module)
    class StopBeforeInference:
        def __init__(self, adapter):
            protocol = json.loads((output / "protocol.json").read_text())
            warmup, selected = profiler.select_images(manifest)
            assert protocol["warmup"]["image"] == warmup
            assert [row["image"] for row in protocol["selected"]] == selected
            assert len(selected) == 100 and warmup not in selected
            raise RuntimeError("stop before inference")
    monkeypatch.setattr(yunet, "_NativeRuntime", StopBeforeInference)
    with pytest.raises(RuntimeError, match="stop before inference"):
        profiler.run(source, output, models)
    with pytest.raises(ValueError, match="already frozen"):
        profiler.run(source, output, models)
    (source / next(iter(manifest))).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="image checksum"):
        profiler.run(source, tmp_path / "other", models)
    assert not (tmp_path / "other" / "protocol.json").exists()


def test_summary_embedding_total_per_face_includes_zero_face_images():
    rows = [
        {"status": "completed", "faces": 2, "total_seconds": 10, "stages_seconds": {"embedding": 6}},
        {"status": "no_face", "faces": 0, "total_seconds": 2, "stages_seconds": {}},
    ]
    result = summarize(rows)
    assert result["total_observed_faces"] == 2
    assert result["embedding_seconds_total"] == 6
    assert result["embedding_seconds_per_observed_face"] == 3
    assert result["stages"]["embedding"]["p50_seconds"] == 3
    assert summarize(rows[1:])["embedding_seconds_per_observed_face"] is None


def test_partial_existing_output_directory_is_refused_before_source_access(tmp_path):
    from app.evaluation.component_profiling import run
    output = tmp_path / "partial"
    output.mkdir()
    (output / "dlib-timings.jsonl").write_text("existing receipt\n")
    with pytest.raises(ValueError, match="directory already exists"):
        run(tmp_path / "source-never-accessed", output, tmp_path / "models")
    assert (output / "dlib-timings.jsonl").read_text() == "existing receipt\n"
