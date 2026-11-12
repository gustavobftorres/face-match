import hashlib
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.evaluation.models import ReferenceImage, Scan
from app.evaluation.yunet_auraface import YunetAuraFaceAdapter


def test_local_artifacts_are_validated_and_described_without_native_imports(tmp_path):
    yunet = tmp_path / "yunet.onnx"
    aura = tmp_path / "aura.onnx"
    yunet.write_bytes(b"detector")
    aura.write_bytes(b"recognizer")
    adapter = YunetAuraFaceAdapter(yunet, aura)
    metadata = adapter.describe()
    assert metadata["models"]["yunet"]["sha256"] == hashlib.sha256(b"detector").hexdigest()
    assert metadata["models"]["auraface"]["sha256"] == hashlib.sha256(b"recognizer").hexdigest()
    assert metadata["providers"] == ["CPUExecutionProvider"]
    json.dumps(metadata, allow_nan=False)
    with pytest.raises(ValueError, match="SHA256"):
        YunetAuraFaceAdapter(yunet, aura, yunet_sha256="0" * 64)
    with pytest.raises(FileNotFoundError):
        YunetAuraFaceAdapter(tmp_path / "missing", aura)


def make_adapter(tmp_path, runtime):
    detector, recognizer = tmp_path / "det.onnx", tmp_path / "rec.onnx"
    detector.write_bytes(b"detector")
    recognizer.write_bytes(b"recognizer")
    return YunetAuraFaceAdapter(detector, recognizer, _runtime=runtime)


def embedding(x, y=0):
    result = np.zeros(512, dtype=np.float32)
    result[:2] = x, y
    return result


def test_search_returns_maximum_normalized_cosine_for_each_identity(tmp_path):
    vectors = {"scan": [embedding(-2), embedding(3, 4)],
               "alice": [embedding(9)], "bob": [embedding(0, 8)]}
    adapter = make_adapter(tmp_path, SimpleNamespace(encode=lambda path: vectors[path.name]))
    gallery = [ReferenceImage("a", "alice", tmp_path / "alice", "test"),
               ReferenceImage("b", "bob", tmp_path / "bob", "test")]
    result = adapter.search(gallery, Scan("s", tmp_path / "scan", "test", ()))
    assert result.has_face and result.error is None
    assert [s.identity_id for s in result.scores] == ["alice", "bob"]
    assert [s.score for s in result.scores] == pytest.approx([0.6, 0.8])
    assert all(type(s.score) is float for s in result.scores)


@pytest.mark.parametrize("faces, error", [([], None), ([embedding(1)], None),
    ([np.zeros(512)], "nonzero"), ([np.full(512, np.nan)], "finite"),
    ([np.ones(511)], "512")])
def test_no_face_is_distinct_from_bad_embeddings(tmp_path, faces, error):
    adapter = make_adapter(tmp_path, SimpleNamespace(encode=lambda path: faces))
    result = adapter.search([], Scan("s", tmp_path / "scan", "test", ()))
    assert result.has_face == bool(faces and error is None)
    assert (result.error is None) == (error is None)
    if error:
        assert error in result.error


@pytest.mark.parametrize("reference_faces", [[], [embedding(1), embedding(0, 1)]])
def test_references_reject_missing_or_ambiguous_faces(tmp_path, reference_faces):
    adapter = make_adapter(tmp_path, SimpleNamespace(encode=lambda path:
        [embedding(1)] if path.name == "scan" else reference_faces))
    reference = ReferenceImage("r", "alice", tmp_path / "reference", "test")
    scan = Scan("s", tmp_path / "scan", "test", ())
    assert "exactly one face" in adapter.search([reference], scan).error
    assert "one reference per identity" in adapter.search([reference, reference], scan).error


def test_inference_errors_are_reported(tmp_path):
    def fail(path):
        raise RuntimeError("inference failed")
    adapter = make_adapter(tmp_path, SimpleNamespace(encode=fail))
    result = adapter.search([], Scan("s", tmp_path / "scan", "test", ()))
    assert not result.has_face and result.error == "RuntimeError: inference failed"


def test_native_pipeline_decodes_bounds_aligns_and_normalizes(tmp_path):
    from app.evaluation.yunet_auraface import _NativeRuntime, _ARCFACE_TEMPLATE
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "scan.png"
    Image.new("RGB", (224, 224), (255, 0, 0)).save(path)
    row = np.r_[0, 0, 100, 100, np.asarray(_ARCFACE_TEMPLATE).ravel(), 0.99]
    class Detector:
        def setInputSize(self, size):
            assert size == (112, 112)
        def detect(self, image):
            assert image.dtype == np.uint8
            assert image[0, 0].tolist() == [0, 0, 255]
            return 1, row[None, :]
    class Session:
        def run(self, outputs, inputs):
            blob = inputs["input"]
            assert blob.shape == (1, 3, 112, 112) and blob.dtype == np.float32
            np.testing.assert_allclose(blob[0, :, 56, 56], [1, -1, -1])
            return [embedding(3, 4)[None, :]]
    runtime = object.__new__(_NativeRuntime)
    runtime.cv2 = cv2
    runtime.detector = Detector()
    runtime.session = Session()
    runtime.input_name = "input"
    runtime.max_image_dimension = 112
    runtime.detector_fallback_max_dimension = 320
    vectors = runtime.encode(path)
    np.testing.assert_allclose(vectors[0][:2], [0.6, 0.8])
    path.write_bytes(b"invalid image")
    with pytest.raises(ValueError, match="decode"):
        runtime.encode(path)


def test_unavailable_requested_provider_is_an_error_not_silent_fallback(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(get_available_providers=lambda: []))
    adapter = make_adapter(tmp_path, None)
    result = adapter.search([], Scan("s", tmp_path / "scan", "test", ()))
    assert "CPUExecutionProvider" in result.error and "unavailable" in result.error


def test_similarity_alignment_preserves_landmark_order_and_is_deterministic():
    from app.evaluation.yunet_auraface import _similarity_transform, _ARCFACE_TEMPLATE
    template = np.asarray(_ARCFACE_TEMPLATE)
    angle = 0.23
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    source = 2 * template @ rotation.T + [17, -9]
    matrix = _similarity_transform(source)
    np.testing.assert_allclose(source @ matrix[:, :2].T + matrix[:, 2], template, atol=1e-10)
    np.testing.assert_array_equal(matrix, _similarity_transform(source))
    for invalid in (np.zeros((5, 2)), np.full((5, 2), np.nan), np.zeros((4, 2))):
        with pytest.raises(ValueError, match="landmarks"):
            _similarity_transform(invalid)


def test_exif_orientation_is_applied_before_bounded_detection(tmp_path):
    from app.evaluation.yunet_auraface import _NativeRuntime
    path = tmp_path / "rotated.png"
    image = Image.new("RGB", (224, 112), (10, 20, 30))
    exif = image.getexif()
    exif[274] = 6
    image.save(path, exif=exif)
    class Detector:
        def setInputSize(self, size):
            assert size == (56, 112)
        def detect(self, bgr):
            assert bgr.shape == (112, 56, 3)
            assert bgr[0, 0].tolist() == [30, 20, 10]
            return 1, None
    runtime = object.__new__(_NativeRuntime)
    runtime.detector = Detector()
    runtime.max_image_dimension = 112
    runtime.detector_fallback_max_dimension = 320
    assert runtime.encode(path) == ()


@pytest.mark.parametrize("reference_faces", [[], [embedding(1), embedding(0, 1)]])
def test_invalid_reference_is_reported_even_when_scan_has_no_face(tmp_path, reference_faces):
    adapter = make_adapter(tmp_path, SimpleNamespace(encode=lambda path:
        [] if path.name == "scan" else reference_faces))
    reference = ReferenceImage("r", "alice", tmp_path / "reference", "test")
    result = adapter.search([reference], Scan("s", tmp_path / "scan", "test", ()))
    assert not result.has_face
    assert result.error and "exactly one face" in result.error


@pytest.mark.parametrize("first_face, fallback_face, calls", [(False, True, 2),
    (False, False, 2), (True, False, 1)])
def test_fixed_detector_scale_fallback_remaps_coordinates(tmp_path, first_face, fallback_face, calls):
    from app.evaluation.yunet_auraface import _NativeRuntime, _ARCFACE_TEMPLATE
    cv2 = pytest.importorskip("cv2")
    row = np.r_[10, 20, 100, 200, np.asarray(_ARCFACE_TEMPLATE).ravel(), 0.99]
    sizes = []
    class Detector:
        def setInputSize(self, size):
            sizes.append(size)
        def detect(self, image):
            found = first_face if len(sizes) == 1 else fallback_face
            return 1, row[None, :].copy() if found else None
    runtime = object.__new__(_NativeRuntime)
    runtime.cv2 = cv2
    runtime.detector = Detector()
    runtime.detector_fallback_max_dimension = 320
    faces = runtime._detect_faces(np.zeros((777, 1000, 3), dtype=np.uint8))
    assert sizes == ([(1000, 777), (320, 249)] if calls == 2 else [(1000, 777)])
    if first_face or fallback_face:
        expected = row.copy()
        if not first_face:
            expected[[0, 2, 4, 6, 8, 10, 12]] *= 1000 / 320
            expected[[1, 3, 5, 7, 9, 11, 13]] *= 777 / 249
        np.testing.assert_allclose(faces[0], expected)
    else:
        assert faces.shape == (0, 15)
