# Offline Dlib threshold replay

`app.evaluation.dlib_threshold_replay` applies an approved threshold selected exclusively on public LFW View 1 development pairs to already recorded Dlib negative-distance scores. It performs no inference, imports no inference adapter, opens no image, and does not select a threshold using private labels. It neither downloads models nor changes production settings.

Run from `apps/backend`, using the approved calibration receipt and original comparison plan digests:

```sh
python -m app.evaluation.dlib_threshold_replay \
  --calibration-receipt /private/tmp/public-dlib-calibration/threshold-result.json \
  --approved-receipt-sha256 APPROVED_RECEIPT_SHA256 \
  --source-run /private/tmp/comparison-run \
  --approved-source-plan-sha256 APPROVED_SOURCE_PLAN_SHA256 \
  --output /private/tmp/dlib-threshold-replay
```

The output must not exist and must be separate from both input directories. The command validates the receipt digest, linked public protocol/scores/decisions digests, negative-distance semantics (`score > threshold`, equivalent to `distance < -threshold`), minimum 500 completed pairs per class, and exact reproduction of the public maximum-TPR objective with empirical FPR ≤ 0.001 and stricter-threshold tie breaking. Errors and missing faces cannot receive synthetic scores.

The source is a `test_only` comparison bundle with `compare-plan.json` and `artifacts/{run.json,threshold.json,metrics.json,decisions.ndjson}`. The approved source-plan digest freezes its original policies, code fingerprints, adapter configuration, counts and runtime versions. Replay checks the original strict `score > -0.6` decisions against all baseline rows and recomputes the stored metrics. It checks unique scan IDs, recorded labels, complete gallery score sets and class counts from the source plan; it does not open the manifest or its media paths. Public calibration and historical source must share the recorded Python/platform and five Dlib-related package versions, production preprocessing and `face_search.py`/`ai_service.py` fingerprints. The current runner fingerprint must also match the frozen source plan. The four public calibration implementation files and the six recorded public runtime/model files are rehashed at their recorded local paths; all must match the approved public runtime snapshot. This verifies present public calibration compatibility, while leaving historical private weights unverified.

The historical source uses a wrapper adapter identity and lacks the new public calibration's richer runtime/model metadata. Matching is explicit: the frozen baseline factory/configuration/description and shared runtime fields are checked; fields absent historically are never silently treated as matches. Python executable paths, dataset paths, names of the public adapter instance, candidate runtime packages and public-only binary/weight hashes are not compared as historical evidence.

**Historical Dlib weights were not hashed by the original comparison. Their past bytes cannot be cryptographically verified. The saved scores remain the authoritative input to replay.** Matching implementation/version metadata provides compatibility evidence, not proof of past model bytes. The public calibration remains in-sample and cannot establish private-domain generalization.

After validation, `replay-plan.json` is written before any new decisions. It freezes the approved receipt/source-plan hashes, linked public hashes, source artifact hashes, replay/runner implementation hashes, original comparison provenance, new threshold and limitations. `decisions.ndjson` preserves scores, labels, errors, missing-face outcomes and per-image timings, changing only decisions for scored images. `summary.json` reports original/calibrated TP/FP/FN/TN, precision, recall, FPR (`fpir`), errors, missing faces, `face_score_coverage` (fraction with usable scores), end-to-end recall/misses/FPR and the aggregate count of changed predictions. Errors are excluded from the confusion matrix but counted as misses in positive end-to-end recall. Missing faces count as FN or TN according to their labels.

Timing is explicitly labeled **“original inference timings; not remeasured by replay.”** The identical recorded percentiles are provenance from the original inference run, not a new speed benchmark. Output contains private per-image identifiers and must remain outside Git. Publish only reviewed aggregate results.

Synthetic tests cover approved/linked checksum failures, invalid source semantics and positive scores, strict equality boundaries, preserved errors/missing faces, source counts/duplicates/runtime/code/metrics, refusing an existing output, freezing the plan before decisions, and preventing media reads.
