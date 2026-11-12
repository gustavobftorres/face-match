# Public LFW component profiling

`app.evaluation.component_profiling` instruments existing encoder calls without
changing model outputs, thresholds or production files. It never downloads data
or models. Run from `apps/backend` in the shared candidate environment:

```sh
/private/tmp/face-match-candidate-venv/bin/python -m app.evaluation.component_profiling \
  --source /private/tmp/face-match-lfw-calibration \
  --models /private/tmp/face-match-candidate-models \
  --output /private/tmp/face-match-component-profile
```

The source must contain the public LFW View 1 calibration protocol, original
checksum-verified archives and image manifest. Every manifest image is checked
against its bytes before selection. Only `(SHA256, public path)` controls order:
rank zero is a separate warmup, ranks 1–100 are the timed sample. No labels,
scores, decisions or private manifests are read. The output directory must be
separate from the public source; an existing output directory is refused, including
partial runs.

Before first inference, `protocol.json` records selection, image hashes, source
hashes (including the native dlib binary implementing HOG), package versions,
requested providers, native dlib model hashes and frozen
YuNet/AuraFace model hashes/configuration. Active CPU-only providers are verified
before encoding and recorded in the result alongside actual ORT session options,
OpenCV configured thread count and parallel framework. GCD may ignore OpenCV
thread limits, and configured counts do not measure total native workers.
Both backends run in the same Python
process/environment, sequentially, dlib first. Each backend runs one untimed
baseline and one instrumented warmup; exact vector equality is required. Zero
faces validate count only, with zero embeddings checked. The 100 timed images are
encoded once each; per-image baseline reruns are intentionally absent.

Dlib calls the unchanged production encoder. Wrappers time its raw HOG detector,
landmark predictor and native descriptor calls, including default `small` landmarks
and `num_jitters=1`. Native descriptor computation includes alignment, which is
not separable. YuNet wraps the unchanged native runtime detector (including
fallback resize and coordinate remapping), similarity transform/warp, and ONNX
session run. Proxies forward the exact arguments and return original objects.
These process-local patches require isolated single-threaded offline use.

`stages_seconds` contains exclusive spans: nested detector work is subtracted
from the enclosing landmark call. Read bytes is separate for dlib; YuNet reads
inside its encoder residual. The explicitly named decode/EXIF/RGB/resize/Python
residual also includes normalization and packaging; it is **not** a claim that
preprocessing alone has been isolated. Dispatch/instrumentation residual closes
the wall-clock accounting. Propagated failures retain elapsed stages and are counted.
The production dlib encoder catches exceptions and returns an empty list; its
`no_face` count therefore also includes swallowed production errors. Every
image's stages sum to its total; absent stages contribute zeros to p50/p95/sums.
Percentiles use linear interpolation over all 100 attempted images. Summaries
also report observed face count, total embedding time and embedding seconds per
observed face. Each detector can find a different number of faces, so per-image
embedding time alone is not a comparison at equal detection coverage.

Distance uses the warmup's first face as a fixed reference against every timed
face: production dlib distance or normalized cosine for AuraFace, without any
threshold decision. If warmup has no face, distance is unavailable; there is no
selection of a replacement. JSONL contains timing, face counts and error/status
only. Embeddings are retained in memory only and never written.

Public LFW images are 250×250 and largely centered portraits. This profile does
not explain latency on private 1000px images with many faces. Instrumentation,
filesystem caches, native initialization, CPU scheduling and backend run order
limit interpretation. Timing is diagnostic, not an independent accuracy or
throughput benchmark. No production model or threshold is changed.
