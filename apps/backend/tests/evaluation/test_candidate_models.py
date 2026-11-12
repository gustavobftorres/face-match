from dataclasses import replace
import hashlib

import pytest

from app.evaluation.candidate_models import AURAFACE, MODEL_ASSETS, YUNET, verify_asset


def test_manifest_is_revision_pinned_and_excludes_other_bundle_models():
    assert {asset.filename for asset in MODEL_ASSETS} == {
        "glintr100.onnx", "face_detection_yunet_2023mar.onnx"}
    for asset in MODEL_ASSETS:
        assert len(asset.revision) == 40
        assert asset.revision in asset.url
        assert len(asset.sha256) == 64
    assert (YUNET.license, AURAFACE.license) == ("MIT", "Apache-2.0")


def test_integrity_checks_reject_missing_partial_and_same_size_corrupt_bytes(tmp_path):
    path = tmp_path / "model.onnx"
    asset = replace(YUNET, size_bytes=4, sha256=hashlib.sha256(b"onnx").hexdigest())
    with pytest.raises(ValueError, match="does not exist"):
        verify_asset(path, asset)
    path.write_bytes(b"on")
    with pytest.raises(ValueError, match="size mismatch"):
        verify_asset(path, asset)
    path.write_bytes(b"oops")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_asset(path, asset)
    path.write_bytes(b"onnx")
    verified = verify_asset(path, asset)
    assert verified["path"] == str(path.resolve())
    assert verified["sha256"] == asset.sha256
