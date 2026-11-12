# Public LFW component profiling result

Run frozen at `2026-11-12T16:27:34.175465+00:00` with the [offline component profiler](component-profiling.md). Both native backends used `/private/tmp/face-match-candidate-venv/bin/python` in one process, sequentially: dlib then YuNet/AuraFace. This is one diagnostic run, with no repeat or confidence interval.

The 100 timed images were selected before inference by ascending `(image SHA256, public path)` from the checksum-verified public LFW View 1 image manifest. Rank zero was reserved for warmup and excluded from the timed sample. No labels, scores, thresholds or private media influenced selection. Production/configuration/source files were unchanged during the run.

| Backend | Timed images | Completed / no face / error | Observed faces | Total (s) | Image p50 (ms) | Image p95 (ms) | Embedding / observed face (ms) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| dlib | 100 | 100 / 0 / 0 | 111 | 2.127178 | 20.583 | 26.971 | 6.070 |
| yunet_auraface | 100 | 98 / 2 / 0 | 106 | 26.473998 | 249.847 | 495.726 | 246.843 |

Dlib spent 64.12% of timed wall time in HOG detection and 31.67% in the native descriptor call, which includes alignment. AuraFace spent 98.83% in ONNX embedding inference; YuNet detection accounted for 0.85%. The detectors observed different face counts, so embedding costs include different amounts of detected-face work. Neither timing implies an accuracy advantage.

| Backend / exclusive stage | Sum (s) | Per-image p50 (ms) | Per-image p95 (ms) |
| --- | ---: | ---: | ---: |
| dlib / decode_exif_rgb_resize_and_python_residual | 0.032498 | 0.3121 | 0.4004 |
| dlib / detector | 1.363899 | 13.6469 | 13.7317 |
| dlib / distance | 0.001719 | 0.0164 | 0.0222 |
| dlib / embedding_native_alignment | 0.673736 | 6.0910 | 12.0663 |
| dlib / instrumentation_and_dispatch_residual | 0.002131 | 0.0212 | 0.0253 |
| dlib / landmarks | 0.047046 | 0.4390 | 0.7218 |
| dlib / read_bytes | 0.006150 | 0.0560 | 0.0711 |
| yunet_auraface / decode_exif_rgb_resize_and_python_residual | 0.063601 | 0.6302 | 0.7110 |
| yunet_auraface / detector | 0.225545 | 2.2474 | 2.4544 |
| yunet_auraface / distance | 0.001465 | 0.0140 | 0.0199 |
| yunet_auraface / embedding | 26.165396 | 246.7468 | 492.3231 |
| yunet_auraface / instrumentation_and_dispatch_residual | 0.003778 | 0.0372 | 0.0434 |
| yunet_auraface / landmarks_alignment | 0.014213 | 0.1363 | 0.2584 |

All stage percentiles include all 100 attempted images, with zero for unreached work. Exclusive spans subtract nested detector work from dlib landmarks. The decode/EXIF/RGB/resize/Python residual includes normalization and packaging; these operations were not separately isolated. Dlib file reads are separately timed; YuNet file reads are included in its residual. Instrumentation/dispatch residual completes total wall-clock accounting. All 200 per-image stage sums reconciled exactly to their recorded total, and every recorded stage was nonnegative.

Both backends passed exact baseline-versus-instrumented warmup parity: equal face count and one equal embedding per backend. This validates that warmup only; the 100 timed images were each encoded once without baseline reruns. The fixed warmup reference was available in both models; distance was computed for all 111 dlib and 106 AuraFace observed faces. Embeddings and individual distance/similarity values were never written. Dlib production catches internal exceptions and returns an empty list, so its no-face category can include swallowed production errors.

Runtime metadata: active ONNX provider was `CPUExecutionProvider`, with observed intra-op/inter-op settings both 1. OpenCV reported 11 configured threads and `GCD`; that does not measure actual worker count, and GCD can ignore thread limits. YuNet was constructed with `DNN_BACKEND_OPENCV` and `DNN_TARGET_CPU` (there is no runtime getter for those detector settings). Package versions: dlib 20.0.1, face-recognition 1.3.0, face-recognition-models 0.3.0, NumPy 2.5.4, Pillow 12.3.0, OpenCV headless 4.14.0.94, ONNX Runtime 1.31.1.

Public LFW images are 250×250, predominantly centered portraits. These measurements do not explain or predict the 821-second private workload with images bounded at 1000px and multiple faces. Run order, warm caches, native scheduling, different detection coverage and instrumentation overhead limit comparisons. No production model, threshold or matching behavior changed.

Local artifacts remain outside Git at `/private/tmp/face-match-component-profile`. The audit verified frozen source hashes (including dlib binary/HOG), protocol linkage, both timing-file hashes, exactly 100 unique ordered selections, warmup exclusion, face/distance counts and zero propagated errors. Runtime emitted telemetry/cache persistence warnings; inference completed successfully without retries.

| Artifact | SHA256 |
| --- | --- |
| protocol.json | `d026f0755679a917b981b4e15b6c10559ccc47c39fa4dedba45ec952902148c1` |
| result.json | `f147c98fe3e019d218a745a20af73e7ea158bff65a913efb07db9854d9a2414e` |
| dlib-timings.jsonl | `728682f572bbb989bda66d95e096a05f74ae6005288491585350456641f1c45a` |
| yunet_auraface-timings.jsonl | `fdaed33f41ef5c62d987cf3bb98a806783eb118dcc1c21da46404d044462d447` |
| Public image manifest | `d275b321d48a1ca48b58bad9b1da0d9ededcc5536b663f8e42e1b180bd49e811` |
