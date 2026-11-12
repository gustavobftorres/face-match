"""Pinned candidate weight identities and offline integrity verification.

This module never downloads weights or imports a native inference runtime.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class ModelAsset:
    filename: str
    revision: str
    sha256: str
    size_bytes: int
    url: str
    license: str
    license_url: str


YUNET_REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
AURAFACE_REVISION = "af6d057c9b0ec4071d4c49c80e3539258798b609"
YUNET = ModelAsset(
    "face_detection_yunet_2023mar.onnx", YUNET_REVISION,
    "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", 232589,
    f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{YUNET_REVISION}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "MIT", f"https://github.com/opencv/opencv_zoo/blob/{YUNET_REVISION}/models/face_detection_yunet/LICENSE",
)
AURAFACE = ModelAsset(
    "glintr100.onnx", AURAFACE_REVISION,
    "a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60", 260694151,
    f"https://huggingface.co/fal/AuraFace-v1/resolve/{AURAFACE_REVISION}/glintr100.onnx",
    "Apache-2.0", f"https://huggingface.co/fal/AuraFace-v1/blob/{AURAFACE_REVISION}/LICENSE.md",
)
MODEL_ASSETS = (YUNET, AURAFACE)


def verify_asset(path: Path | str, asset: ModelAsset) -> dict:
    """Reject missing, partial or altered bytes before candidate inference."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"model file does not exist: {path}")
    if path.stat().st_size != asset.size_bytes:
        raise ValueError(f"model size mismatch: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != asset.sha256:
        raise ValueError(f"model SHA-256 mismatch: {path}")
    return {**asdict(asset), "path": str(path.resolve())}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path)
    args = parser.parse_args()
    try:
        verified = [verify_asset(args.model_dir / asset.filename, asset) for asset in MODEL_ASSETS]
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps({"verified_models": verified}, indent=2))


if __name__ == "__main__":
    main()
