# Public Dlib calibration

This separate runner calibrates the current production Dlib adapter on exactly
LFW View 1's 2,200 development pairs: 1,100 mated and 1,100 nonmated. It reads only
the preceding public acquisition at `/private/tmp/face-match-lfw-calibration`.
It has no download or private-manifest input. Before freezing a new protocol,
it verifies the pinned archive, pair file, image-hash inventory, every required
image hash, and confined nonsymlink local paths. Existing output directories
are refused. The preceding AuraFace runner and protocol remain unchanged.

The first pair image is the reference. Production uses its first encoded face,
including when more than one face is detected. The second image is the scan;
its best match across all encoded faces supplies `score = -distance`. The scan
is encoded first; an empty scan returns before acquiring the reference. Images
are never swapped. The production preprocessing performs EXIF transpose, RGB
conversion and a 1,000-pixel maximum thumbnail with LANCZOS. Face recognition
uses its defaults: HOG detection with one upsample, small five-point landmarks,
ResNet face descriptors and one jitter.

The frozen objective maximizes completed-pair empirical TPR subject to empirical
FPR ≤ 0.001, requiring at least 500 completed pairs of each class. Higher scores
are better. Scores must be finite and nonpositive; negative distances can fall
below -1 and are not cosine values. Acceptance is strictly `score > threshold`,
exactly equivalent to `distance < -threshold`. Candidates are observed scores
plus finite `nextafter(min_score, -inf)`; the largest observed score rejects
all pairs. Equal TPR chooses the larger, stricter threshold. A selected raw
distance threshold is recorded alongside the negative score threshold.

Errors and no-face outcomes supply no invented score and are excluded from the
fitting denominator. Coverage and end-to-end metrics separately include those
failures: neither accepts, and mated failures count as misses. Production's
encoder catches internal exceptions and returns an empty encoding list, so
those outcomes cannot be distinguished from acquisition failures by this
adapter. Nonmated FPR uses completed nonmated pairs for threshold selection;
all-pair FPR is also reported. One false positive among 1,000 completed negatives
meets the target, whereas one among 999 exceeds it.

The protocol is written before the first encoding. It records input hashes,
implementation hashes, Python/platform/package versions, face-recognition API
and Dlib binary hashes, the small five-point landmark and ResNet weight hashes,
preprocessing, acquisition, comparator and selection rules. The compiled HOG
detector is covered by the Dlib binary hash. The API also loads 68-point
landmark and CNN detector weights at import; neither is used by these defaults. Calibration memoizes
ordered encodings by input byte SHA256 while retaining the production reference
cache. The resulting timings are not a performance benchmark. Public profiling
must be a separate run with its own declared cache and sample policy.

```sh
PYTHONPATH=apps/backend /private/tmp/face-match-candidate-venv/bin/python \
  -m app.evaluation.dlib_lfw_calibration \
  --source /private/tmp/face-match-lfw-calibration \
  --output /private/tmp/face-match-dlib-lfw-calibration
```

Run only after implementation and protocol review. `protocol.json` and
`image-sha256.json` freeze inputs and rules. `scores.jsonl` retains all raw pair
records, scores, statuses and errors; `decisions.json` applies the selected
strict threshold. `threshold-result.json` includes the threshold, counts,
coverage, end-to-end rates, cache counts and artifact hashes. The selection
schema exposes `score_threshold` and `distance_threshold` (its negation). It records
`comparator: ">"`, `distance_comparator: "<"`, `score_semantics`, `target_fpr`,
`completed_mated`, `completed_nonmated`, `tp`, `fp`, `empirical_tpr` and
`empirical_fpr`. The receipt also includes adapter/runtime metadata and
`protocol_path`, `protocol_sha256`, `scores_sha256` and `decisions_sha256`. Photos, embeddings
and per-pair artifacts stay outside Git.

These are in-sample calibration statistics, not independent validation. Zero
observed false positives does not establish zero population FPR. LFW labels
refer to the central face, while production searches any scan face. Possible
Dlib pretraining overlap with LFW is unknown; training independence is not
claimed. Celebrity pair verification at 250×250 does not establish accuracy or
latency for private collections, larger images, multiface photos or gallery
search. This runner does not tune a private dataset or modify production's
configured threshold.
