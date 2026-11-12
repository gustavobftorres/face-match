"""Evaluation-only, local ONNX YuNet + AuraFace; never downloads weights.

One reference image per identity is supported, with exactly one detected face.
Multiple scan faces are scored by maximum normalized cosine similarity. This
module makes no threshold/match decisions. Native dependencies load on first
search; importing it and describing artifacts does not import cv2/onnxruntime.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import math
from pathlib import Path

from .models import FaceScore, SearchResult


class YunetAuraFaceAdapter:
    name = "yunet-auraface"
    score_semantics = "higher_is_better"

    def __init__(self, yunet_model_path, auraface_model_path, *,
                 name="yunet-auraface",
                 yunet_sha256=None, auraface_sha256=None,
                 max_image_dimension=1000, detector_fallback_max_dimension=320,
                 score_threshold=0.9,
                 nms_threshold=0.3, top_k=5000,
                 providers=("CPUExecutionProvider",), intra_op_threads=1,
                 inter_op_threads=1, _runtime=None):
        for key, value in (("max_image_dimension", max_image_dimension),
                           ("detector_fallback_max_dimension", detector_fallback_max_dimension),
                           ("top_k", top_k), ("intra_op_threads", intra_op_threads),
                           ("inter_op_threads", inter_op_threads)):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
        for key, value in (("score_threshold", score_threshold), ("nms_threshold", nms_threshold)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{key} must be finite in (0, 1]")
        if isinstance(providers, str) or not providers or any(not isinstance(p, str) or not p for p in providers):
            raise ValueError("providers must be a non-empty sequence of provider names")
        self._models = {}
        for label, path, expected in (("yunet", yunet_model_path, yunet_sha256),
                                      ("auraface", auraface_model_path, auraface_sha256)):
            path = Path(path).expanduser().resolve(strict=True)
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"{label} model must be a non-empty file")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or expected.lower() != digest):
                raise ValueError(f"{label} model SHA256 mismatch")
            self._models[label] = {"path": str(path), "sha256": digest}
        self.max_image_dimension = max_image_dimension
        self.detector_fallback_max_dimension = detector_fallback_max_dimension
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.top_k = top_k
        self.providers = tuple(providers)
        self.intra_op_threads = intra_op_threads
        self.inter_op_threads = inter_op_threads
        self._runtime = _runtime
        self._reference_cache = {}
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self.name = name

    def search(self, gallery, scan):
        """Return score-only cosine similarities; malformed media is an error."""
        try:
            identities = [reference.identity_id for reference in gallery]
            if len(set(identities)) != len(identities):
                raise ValueError("requires one reference per identity")
            if self._runtime is None:
                self._runtime = _NativeRuntime(self)
            prepared = []
            for reference in sorted(gallery, key=lambda item: item.identity_id):
                known_vector = self._reference_cache.get(reference.path)
                if known_vector is None:
                    known = tuple(self._runtime.encode(reference.path))
                    if len(known) != 1:
                        raise ValueError(f"reference image requires exactly one face: {reference.id} (found {len(known)})")
                    known_vector = _normalized(known[0])
                    self._reference_cache[reference.path] = known_vector
                prepared.append((reference.identity_id, known_vector))
            unknown = tuple(_normalized(vector) for vector in self._runtime.encode(scan.path))
            if not unknown:
                return SearchResult(False)
            scores = []
            for identity_id, known_vector in prepared:
                scores.append(FaceScore(identity_id, max(
                    float(max(-1.0, min(1.0, known_vector @ observed))) for observed in unknown
                )))
            return SearchResult(True, tuple(scores))
        except Exception as exc:
            return SearchResult(False, error=f"{type(exc).__name__}: {exc}")

    def describe(self):
        def installed(package):
            try:
                return version(package)
            except PackageNotFoundError:
                return None
        return {"name": self.name, "adapter_version": 2,
                "models": {key: dict(value) for key, value in self._models.items()},
                "preprocessing_version": "exif-rgb-bgr-bound-v1/yunet-zero-face-scale-fallback-v1/arcface112-similarity-v1/rgb-nchw-127.5-v1",
                "max_image_dimension": self.max_image_dimension,
                "detector": {"score_threshold": self.score_threshold, "nms_threshold": self.nms_threshold,
                             "top_k": self.top_k, "input_size": "bounded-image-size", "backend": "opencv-cpu",
                             "fallback_max_dimension": self.detector_fallback_max_dimension,
                             "fallback_policy": "only-if-zero-faces-and-image-larger;remap-to-bounded-image"},
                "providers": list(self.providers),
                "active_providers": getattr(self._runtime, "providers", None),
                "intra_op_threads": self.intra_op_threads,
                "inter_op_threads": self.inter_op_threads,
                "reference_policy": "one-image-per-identity/exactly-one-face",
                "score_semantics": "normalized-cosine-max-over-scan-faces",
                "runtime_versions": {p: installed(p) for p in ("numpy", "Pillow", "opencv-python-headless", "opencv-python", "onnxruntime")}}


def _normalized(vector):
    import numpy as np

    vector = np.asarray(vector, dtype=np.float64)
    if vector.shape != (512,) or not np.isfinite(vector).all():
        raise ValueError("embedding must contain 512 finite values")
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("embedding must have a finite nonzero norm")
    return vector / norm


_ARCFACE_TEMPLATE = ((38.2946, 51.6963), (73.5318, 51.5014),
                     (56.0252, 71.7366), (41.5493, 92.3655),
                     (70.7299, 92.2041))


def _similarity_transform(landmarks):
    """Least-squares, orientation-preserving similarity, with no random RANSAC.

    YuNet emits subject right eye (image left), left eye, nose, right and
    left mouth corners, in the same order as the standard ArcFace template.
    """
    import numpy as np

    points = np.asarray(landmarks, dtype=np.float64)
    if points.shape != (5, 2) or not np.isfinite(points).all():
        raise ValueError("landmarks must be five finite coordinate pairs")
    if np.linalg.matrix_rank(points - points.mean(axis=0)) != 2:
        raise ValueError("landmarks must be nondegenerate")
    design = np.zeros((10, 4), dtype=np.float64)
    design[0::2, 0], design[0::2, 1], design[0::2, 2] = points[:, 0], -points[:, 1], 1
    design[1::2, 0], design[1::2, 1], design[1::2, 3] = points[:, 1], points[:, 0], 1
    a, b, tx, ty = np.linalg.lstsq(design, np.asarray(_ARCFACE_TEMPLATE).ravel(), rcond=None)[0]
    if not np.isfinite([a, b, tx, ty]).all() or a * a + b * b < 1e-12:
        raise ValueError("landmarks produce a degenerate similarity transform")
    return np.array([[a, -b, tx], [b, a, ty]], dtype=np.float64)


class _NativeRuntime:
    """Lazy native boundary. Explicit local artifacts only; never downloads."""

    def __init__(self, adapter):
        import cv2
        import onnxruntime as ort

        available = ort.get_available_providers()
        missing = set(adapter.providers) - set(available)
        if missing:
            raise RuntimeError(f"requested ONNX providers unavailable: {sorted(missing)}; available: {available}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = adapter.intra_op_threads
        options.inter_op_num_threads = adapter.inter_op_threads
        self.session = ort.InferenceSession(adapter._models["auraface"]["path"],
                                            sess_options=options, providers=list(adapter.providers))
        self.session.disable_fallback()
        if self.session.get_providers() != list(adapter.providers):
            raise RuntimeError(f"ONNX provider fallback: requested {adapter.providers}, active {self.session.get_providers()}")
        self.providers = self.session.get_providers()
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].type != "tensor(float)"
                or len(inputs[0].shape) != 4
                or tuple(inputs[0].shape[1:]) != (3, 112, 112)):
            raise ValueError("AuraFace model must accept one float32 NCHW RGB input (1,3,112,112)")
        if len(outputs) != 1:
            raise ValueError("AuraFace model must expose one 512-dimensional embedding output")
        self.input_name = inputs[0].name
        self.cv2 = cv2
        self.max_image_dimension = adapter.max_image_dimension
        self.detector_fallback_max_dimension = adapter.detector_fallback_max_dimension
        self.detector = cv2.FaceDetectorYN.create(
            adapter._models["yunet"]["path"], "", (320, 320),
            adapter.score_threshold, adapter.nms_threshold, adapter.top_k,
            cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)

    def encode(self, path):
        import numpy as np
        from PIL import Image, ImageOps

        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                width, height = image.size
                scale = min(1.0, self.max_image_dimension / max(width, height))
                if scale < 1:
                    image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                         Image.Resampling.BILINEAR)
                bgr = np.ascontiguousarray(np.asarray(image, dtype=np.uint8)[:, :, ::-1])
        except Exception as exc:
            raise ValueError(f"image decode failed: {path}: {exc}") from exc
        faces = self._detect_faces(bgr)
        embeddings = []
        for face in faces:
            if (face[2:4] <= 0).any() or not 0 <= face[14] <= 1:
                raise ValueError("YuNet returned invalid bounding box or confidence")
            matrix = _similarity_transform(face[4:14].reshape(5, 2))
            aligned = self.cv2.warpAffine(bgr, matrix, (112, 112),
                                          flags=self.cv2.INTER_LINEAR,
                                          borderMode=self.cv2.BORDER_CONSTANT, borderValue=0)
            rgb = aligned[:, :, ::-1].astype(np.float32)
            blob = np.ascontiguousarray(((rgb - 127.5) / 127.5).transpose(2, 0, 1)[None])
            result = self.session.run(None, {self.input_name: blob})
            if len(result) != 1 or np.asarray(result[0]).shape != (1, 512):
                raise ValueError("AuraFace output must have shape (1, 512)")
            embeddings.append(_normalized(result[0][0]))
        return tuple(embeddings)

    def _detect_faces(self, bgr):
        """Retry one fixed smaller scale only on zero detections.

        YuNet's documented training range is approximately 10–300 pixel faces:
        https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
        Recognition always samples the original bounded image, after mapping
        detection coordinates back with the actual rounded x/y resize ratios.
        """
        import numpy as np

        def detect(image):
            self.detector.setInputSize((image.shape[1], image.shape[0]))
            _, rows = self.detector.detect(image)
            if rows is None:
                return np.empty((0, 15), dtype=np.float64)
            rows = np.asarray(rows, dtype=np.float64)
            if rows.ndim != 2 or rows.shape[1] != 15 or not np.isfinite(rows).all():
                raise ValueError("YuNet must return finite face rows of 15 values")
            return rows

        faces = detect(bgr)
        height, width = bgr.shape[:2]
        bound = self.detector_fallback_max_dimension
        if len(faces) or max(height, width) <= bound:
            return faces
        scale = bound / max(height, width)
        resized_width, resized_height = max(1, round(width * scale)), max(1, round(height * scale))
        smaller = self.cv2.resize(bgr, (resized_width, resized_height), interpolation=self.cv2.INTER_AREA)
        faces = detect(smaller).copy()
        faces[:, [0, 2, 4, 6, 8, 10, 12]] *= width / resized_width
        faces[:, [1, 3, 5, 7, 9, 11, 13]] *= height / resized_height
        return faces
