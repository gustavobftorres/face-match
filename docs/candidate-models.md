# YuNet + AuraFace evaluation assets

These optional weights support the offline candidate adapter. They are not bundled
with the application, fetched at inference time, or selected for production.
Keep all weights and private image datasets outside Git. Recognition thresholds
require separate calibration; the smoke checks below do not establish accuracy.

## Pinned identities

| Asset | Source revision | Bytes | SHA-256 | Publisher license |
| --- | --- | ---: | --- | --- |
| `face_detection_yunet_2023mar.onnx` | `opencv/opencv_zoo` `48b10fa505aeb51fbd127fc60a5c660040e823b7` | 232589 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | MIT |
| `glintr100.onnx` | `fal/AuraFace-v1` `af6d057c9b0ec4071d4c49c80e3539258798b609` | 260694151 | `a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60` | Apache-2.0 |

The [YuNet publisher README](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/README.md)
licenses that directory under [MIT](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/LICENSE).
The 2023mar FP32 export supports OpenCV 4.x; the 2026may export targets OpenCV 5.x.
The [AuraFace model card](https://huggingface.co/fal/AuraFace-v1/blob/af6d057c9b0ec4071d4c49c80e3539258798b609/README.md)
declares Apache-2.0 and links a [license file](https://huggingface.co/fal/AuraFace-v1/blob/af6d057c9b0ec4071d4c49c80e3539258798b609/LICENSE.md).
Only the recognition file `glintr100.onnx` is used. The repository also contains
detector and auxiliary weights; their presence is not permission to substitute
them for the explicitly selected YuNet detector. Preserve publisher notices with
any redistribution of the selected weights.

## Explicit download and verification

From the repository root, download only these two revision-pinned URLs:

```sh
mkdir -p /private/tmp/face-match-candidate-models
curl -fL --retry 2 'https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -o /private/tmp/face-match-candidate-models/face_detection_yunet_2023mar.onnx
curl -fL --retry 2 'https://huggingface.co/fal/AuraFace-v1/resolve/af6d057c9b0ec4071d4c49c80e3539258798b609/glintr100.onnx' -o /private/tmp/face-match-candidate-models/glintr100.onnx
cd apps/backend
python -m app.evaluation.candidate_models /private/tmp/face-match-candidate-models
```

The verification command checks both file length and SHA-256, fails on missing,
partial or changed bytes, and prints the verified metadata as JSON. It performs
no network access. Download completion alone is not an integrity check; run this
command before using the files. `candidate_models.py` is the executable manifest.

## Isolated runtime

For candidate-only native smoke checks, use a separate environment to preserve
the active production runtime. From the repository root:

```sh
python3.13 -m venv /private/tmp/face-match-candidate-venv
/private/tmp/face-match-candidate-venv/bin/python -m pip install -r apps/backend/requirements-candidate.txt
```

This environment does not include the Dlib baseline dependencies. To run the
[baseline/candidate comparison example](../apps/backend/evaluation.candidate.example.toml),
install both dependency files in the **same** comparison environment:

```sh
python3.13 -m venv /private/tmp/face-match-comparison-venv
/private/tmp/face-match-comparison-venv/bin/python -m pip install -r apps/backend/requirements.txt -r apps/backend/requirements-candidate.txt
```

Alternatively, install `requirements-candidate.txt` into a backend development
environment whose native `dlib`/`face_recognition` baseline already works. Do not
run the Dlib comparison with only the fresh candidate smoke environment.

Validation on macOS arm64 used Python 3.13.14, opencv-python-headless 4.14.0.94
(`cv2.__version__ == 4.14.0`), onnxruntime 1.31.1, NumPy 2.5.4 and Pillow 12.3.0.
The requirements express supported major version bounds, not a lockfile.
Tests additionally used pytest 8.4.2; graph inspection used onnx 1.23.2, neither
of which is needed for candidate inference.

Observed AuraFace ONNX interface with `CPUExecutionProvider` explicitly selected:

| Direction | Name | Shape | Type |
| --- | --- | --- | --- |
| Input | `data` | `["None", 3, 112, 112]` | float32 |
| Output | `1333` | `[1, 512]` | float32 |

The input batch dimension is a symbolic string in the exported file; the adapter
uses one face per call. Available providers on this host were CoreML, Azure and
CPU; the observed active provider was CPU only. A zero input yielded 512 finite
float32 values. YuNet `FaceDetectorYN` accepted a 320×320 blank BGR image and
returned no faces. These checks establish native loading and tensor compatibility.

## Preprocessing contract

YuNet receives BGR pixels through OpenCV `FaceDetectorYN`. Its returned row is
`x, y, width, height, right-eye-x, right-eye-y, left-eye-x, left-eye-y,
nose-x, nose-y, right-mouth-x, right-mouth-y, left-mouth-x, left-mouth-y, score`.
The eye/mouth names use the person's perspective, so this order maps directly
to the ArcFace template from image left to image right. See the primary
[OpenCV implementation](https://github.com/opencv/opencv/blob/4.x/modules/objdetect/src/face_detect.cpp).

Images are EXIF-transposed and bounded to 1000 pixels by default. If YuNet finds
zero faces and that bounded image is larger than 320 pixels, the adapter makes
one fixed retry at a 320-pixel bound, remapping the detected landmarks to the
larger image before alignment. Detector confidence stays at `0.9`; the retry is
part of the recorded preprocessing contract, not threshold calibration. Cosine
recognition decisions require a separately calibrated or explicit fixed
threshold; the adapter supplies no default recognition threshold.

AuraFace's publisher demonstrates InsightFace's recognition path. The corresponding
[InsightFace ArcFace loader](https://github.com/deepinsight/insightface/blob/c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52/python-package/insightface/model_zoo/arcface_onnx.py)
aligns five landmarks to 112×112, swaps BGR to RGB, and normalizes pixels with
`(value - 127.5) / 127.5` for graphs without an embedded initial Sub/Mul pair.
The downloaded AuraFace graph's first eight nodes are Conv, PRelu,
BatchNormalization, Conv, PRelu, Conv, Conv and Add, without that pair,
confirming this preprocessing path.
The tensor layout is NCHW. Normalize the 512-element output to unit L2 length
before cosine similarity. This describes inference compatibility, not a claim
that a production threshold transfers from another model.
