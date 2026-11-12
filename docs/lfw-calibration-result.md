# Frozen public LFW calibration result

The public LFW View 1 calibration completed on 12 November 2026 using all 2,200
predeclared `pairsDevTrain` pairs (1,100 mated and 1,100 nonmated). Inference took
14.7 minutes on CPU with embedding memoization; this is not a latency benchmark.
No private evaluation manifest, labels or images were accessed for calibration.
The protocol, source code, models and objective remained frozen throughout.

The frozen decision is **normalized cosine similarity ≥ 0.2881247749489934**.
The objective was maximum completed-pair empirical TPR subject to empirical
FPR ≤ 0.001, with stricter thresholds winning TPR ties. Both classes exceeded the
predeclared minimum of 500 completed scores.

| Pair class | Total | Completed scores | Scan no-face | Reference acquisition errors |
| --- | ---: | ---: | ---: | ---: |
| Mated | 1,100 | 991 | 9 | 100 |
| Nonmated | 1,100 | 998 | 13 | 89 |

At the frozen threshold, there were **979 true positives / 991 completed mated
pairs (98.7891% TPR)** and **0 false positives / 998 completed nonmated pairs
(0% empirical FPR)**. A single false positive among 998 would yield approximately
0.1002004%, exceeding the fixed 0.1% constraint. Consequently this sample required
zero observed false positives; the target was not changed after seeing results.
Zero observed false positives is not evidence that the population FPR is zero.

Across all 1,100 mated pairs, including acquisition failures, 979 accepted:
**89% end-to-end TPR**, with 121 misses (12 completed-score rejections, 9 scan
no-face results, and 100 reference acquisition failures). Nonmated no-face and
error results did not accept; all-pair nonmated FPR was 0 / 1,100. Failures supplied
no fabricated similarity and were excluded from threshold fitting.

All 189 acquisition errors enforced the same predeclared requirement of exactly
one detected reference face: 23 references had zero detected faces, 148 had two,
15 had three, and 3 had four. These are pair-level counts; reused references can
appear in more than one pair. No image was swapped to repair acquisition. The
22 scan no-face results are separate from those reference errors. No runtime or
decode errors appeared in the recorded results.

## Frozen configuration and provenance

The runner used the original full LFW RGB images, with 3,443 distinct images
extracted and individually SHA256 hashed. It used YuNet + AuraFace adapter v2,
one reference per pair, and maximum cosine similarity over detected scan faces.
Image bounding was 1,000 pixels; the fixed zero-face detector fallback bound was
320 pixels. Detector confidence was 0.9, NMS 0.3, top-k 5,000. Requested and active
ONNX providers were both `CPUExecutionProvider`, with one intra-op and one
inter-op thread. No sklearn grayscale conversion or crop/resize preprocessing
was used. See [the protocol description](lfw-calibration.md).

| Frozen artifact | SHA256 |
| --- | --- |
| Original `lfw.tgz` | `055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0` |
| `pairsDevTrain.txt` | `1d454dada7dfeca0e7eab6f65dc4e97a6312d44cf142207be28d688be92aabfa` |
| YuNet model | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| AuraFace model | `a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60` |
| Frozen `protocol.json` | `a372116dd6ca97dc33a1b4d301bc9dfb6ecb14bf70b34146098e76fe9038368a` |
| `threshold-result.json` receipt | `57fa2b2958c633fc21cb2c4cf2909c73aa9816dfbece172d386d03149ed56e1a` |
| Image SHA256 manifest | `d275b321d48a1ca48b58bad9b1da0d9ededcc5536b663f8e42e1b180bd49e811` |
| Calibration implementation | `fe32e172c68e518b00b9c3ef9541a0e67efeec0a45f678c74180013a9304cb2a` |
| Adapter implementation | `7c8d8576d4f7c0d8ea18965cfdeea5ba420993262f72629a6546dae8e7df09d8` |

The protocol was written at `2026-11-12T14:38:41.582680+00:00`, before inference.
Runtime versions were NumPy 2.5.4, Pillow 12.3.0, opencv-python-headless 4.14.0.94,
and ONNX Runtime 1.31.1. The full local receipt is
`/private/tmp/face-match-lfw-calibration/threshold-result.json`; its finite
threshold field is `selection.threshold`. Original data, image hashes, raw pair
records, errors, scores and decisions remain outside Git in that directory.

Post-run verification checked the unchanged protocol and implementation hashes,
output hashes, all 2,200 row counts, a recomputation of threshold selection, and
every stored decision against the frozen threshold. The LFW unit suite passed
14 tests, including parsing, threshold boundaries, constraint failure, checksum
rejection and safe extraction. No inference was repeated for this report.

## Interpretation limits

The displayed TPR and FPR are in-sample calibration statistics, not independent
validation estimates. Possible AuraFace pretraining overlap with LFW is unknown;
training independence is not claimed. LFW labels describe the central face,
whereas this application policy scores any detected scan face. Public celebrity
portraits and pair verification do not establish performance for private
multi-person photographs, different capture conditions or a gallery search
workflow. The frozen threshold can support the separately planned private
comparison; these calibration results do not establish private-domain accuracy.
