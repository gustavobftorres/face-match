# Public LFW threshold calibration

The isolated runner uses LFW View 1 `pairsDevTrain.txt`: exactly 1,100 mated
pairs followed by 1,100 nonmated pairs. It never reads a private manifest or
private labels. Original full 250×250 RGB images go through the frozen YuNet +
AuraFace adapter v2 (1000-pixel bound, zero-face 320-pixel fallback, detector
confidence 0.9, CPU ONNX provider). Each pair uses its first image as the sole
reference, requiring exactly one detected face. The second image is searched
across all detected faces. Images are never swapped to repair acquisition.

The predeclared objective maximizes empirical completed-pair TPR subject to
empirical FPR ≤ 0.001, using `score >= threshold`. Equal TPR chooses the stricter
threshold. Candidates are unique observed cosine scores and the finite
`nextafter(max_score, +inf)` reject-all candidate when inside [-1,1]. Calibration
fails if either class has fewer than 500 completed scores or no bounded finite
threshold satisfies the constraint. No model, preprocessing, acquisition rule,
objective, or sample count may change after scores become available.

Errors and no-face pairs supply no invented score and are excluded from threshold
fitting. Receipts separately give completed, no-face and error counts per class.
End-to-end mated misses include all failures; nonmated acquisition failures do
not accept. Completed nonmated count is the constraint denominator. The selected
threshold's calibration performance is in-sample, not an independent estimate.
LFW labels identify the central face; max-over-scan-faces can score another
person. Possible AuraFace pretraining overlap with LFW is **unknown**; training
independence is not claimed. Embedding memoization makes timings unsuitable for
performance comparison.

Data locations and SHA256 are pinned in `lfw_calibration.py`, following the
[scikit-learn LFW loader](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/datasets/_lfw.py).
The original LFW archive and development pairs are served through its Figshare
mirror. Source documentation establishes technical provenance, not a legal grant:
see the [LFW project](https://vis-www.cs.umass.edu/lfw/) for its dataset notices;
model notices remain in `docs/candidate-models.md`. Neither photos nor scores
belong in Git.

```sh
PYTHONPATH=apps/backend /private/tmp/face-match-candidate-venv/bin/python \
  -m app.evaluation.lfw_calibration \
  --output /private/tmp/face-match-lfw-calibration \
  --models /private/tmp/face-match-candidate-models
```

Downloads are streamed with bounds, bounded attempts and timeouts, SHA256 checks,
and Retry-After handling. Extraction only copies explicitly requested JPEGs;
archive traversal, links, unexpected members, oversized members and existing
symlink directories are rejected. Each extracted image receives a SHA256 record.
`protocol.json` records model hashes, runtime/provider metadata, implementation
hashes, image-hash manifest and fixed rules **before** any image inference.
An already frozen output directory is refused rather than silently resumed.
`scores.jsonl` preserves raw pair rows, labels, statuses, errors and scores;
`decisions.json` adds the frozen threshold decisions. `threshold-result.json`
contains `selection.threshold`, constraint metrics, acquisition coverage, the
protocol SHA256 and data/score/decision hashes. Only this frozen finite threshold
may be supplied to a later, separately authorized private comparison.
