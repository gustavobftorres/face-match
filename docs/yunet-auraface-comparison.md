# YuNet + AuraFace comparison: retain the current production model

Do not promote this candidate configuration. It reduced false-positive images
from 42 to 5 (88.1%) and improved precision from 45.45% to 86.11%, but reduced
true-positive images from 35 to 31 and doubled false negatives from 4 to 8.
Recall fell from 89.74% to 79.49%. Candidate search time was approximately 3.46
times the baseline on this machine. Production has not migrated to the candidate.

## Fixed comparison and aggregate results

The 12 November 2026 comparison evaluated both adapters once against the same
1,202 private scan images, one gallery reference, and the same labels: 39 positive
images and 1,163 negative images. It used `mode = "test_only"`. Baseline Dlib
retained production's strict `distance < 0.6` decision. Candidate YuNet + AuraFace
adapter v2 retained the separately calibrated cosine decision
`score >= 0.2881247749489934`; no private-label threshold fitting occurred.

| Metric | Dlib baseline | YuNet + AuraFace candidate |
| --- | ---: | ---: |
| True positives | 35 | 31 |
| False negatives | 4 | 8 |
| False positives | 42 | 5 |
| True negatives | 1,121 | 1,158 |
| Precision | 45.45% | 86.11% |
| Recall / TPIR | 89.74% | 79.49% |
| Image false-positive rate / FPIR | 3.61135% | 0.429923% |
| No-face results | 155 | 206 |
| Runtime errors | 0 | 0 |
| Search phase wall time | 237.288 s | 821.762 s |
| Per-scan p50 | 194.692 ms | 538.502 ms |
| Per-scan p95 | 227.345 ms | 1,775.554 ms |
| Per-scan p99 | 245.815 ms | 2,512.584 ms |

The false-positive-rate denominators are the 1,163 negative images, giving
42 / 1,163 = 0.0361135 and 5 / 1,163 = 0.00429923. Positive images count as true
positives when any predicted identity overlaps the expected identities; this is
an image-level evaluation rather than an accounting of every detected face.
No-face results remain in the confusion matrix. Although candidate no-face
results increased by 51, these counts do not locate the cause of each miss.
An independent audit of the stored decisions confirmed the aggregate overlap:

| Decision overlap | Positive images (39) | False-positive images among negatives (1,163) |
| --- | ---: | ---: |
| Both models accepted | 31 | 2 |
| Only baseline accepted | 4 | 40 |
| Only candidate accepted | 0 | 3 |
| Neither accepted | 4 | 1,118 |

The candidate therefore lost exactly four additional positive images and
recovered none of the baseline's four misses. It corrected 40 baseline false
positives while introducing three new false positives, for a net reduction of 37.

The repeated baseline reproduced the 11 November baseline's aggregate confusion
counts: TP 35, FP 42, FN 4 and TN 1,121. That provides a consistency check on
these aggregate results, not a claim of timing equivalence.

## Historical diagnostic slices

These slices were defined from earlier review and overlap the full corpus; they
are descriptive diagnostics, not additional independent evaluation samples.

| Historical slice | Count | Baseline matches | Candidate matches |
| --- | ---: | ---: | ---: |
| Previously reviewed false-positive images | 42 | 42 | 2 |
| Previously reviewed false-negative images | 5 | 2 | 0 |

On the 42-image false-positive slice, the candidate rejected 39 with a score
decision and one with no detected face, leaving two false-positive matches.
On the five-image false-negative slice, the candidate recovered none: three
score rejections and two no-face results. The baseline matched two of those
five in this run; a historical slice label does not mean every member is still
a false negative under the current baseline. These slice aggregates disclose no
individual image identities; the full-corpus overlap is reported above.

## Freeze and audit trail

The [public LFW protocol](lfw-calibration.md) and
[calibration result](lfw-calibration-result.md) document the threshold selected
before the private comparison. The public objective maximized completed-pair
empirical TPR under FPR ≤ 0.001, with stricter thresholds winning ties. The
candidate model hashes and preprocessing remained the frozen adapter v2 setup:
1,000-pixel image bound, fixed 320-pixel zero-face fallback, detector confidence
0.9, NMS 0.3 and top-k 5,000, with CPU ONNX execution.

| Evidence | SHA256 |
| --- | --- |
| Frozen private comparison plan | `9c2b3b5a24d521b7478f3cb1b103207f7fe10a81e065c95d68bf86c6e4a62e5f` |
| Public threshold receipt | `57fa2b2958c633fc21cb2c4cf2909c73aa9816dfbece172d386d03149ed56e1a` |
| Public calibration protocol | `a372116dd6ca97dc33a1b4d301bc9dfb6ecb14bf70b34146098e76fe9038368a` |
| Private comparison summary | `c37a8558945b87f44fd7f8c1f336bf687a11614cf9b7904ae22f6a954b8c05f8` |
| Private aggregate metrics artifact | `af1aeafcb732ce32b6a5d86e9f25ef2e264447eafad173c934568ac2fe35f5df` |

Local evidence remains outside Git in
`/private/tmp/face-match-dataset-1CluI1JKh4qjjbjYIlyAZbwzpesBeG2Dd/runs/comparison-20261112T145606584598Z`.
`comparison-validation.json` reports successful validation without repeated
inference, with 1,202 unique scan decisions per model, the same 39/1,163 label
counts, and artifact checksums. This report includes only aggregate results;
photos, identities, embeddings and individual similarity scores remain private.

## Interpretation and next experiment

This private corpus was already reviewed and reused. Its results are descriptive
evidence for this decision, not a pristine holdout or a population accuracy
estimate. LFW pair calibration differs from gallery search on private photographs
with potentially several people. Possible AuraFace pretraining overlap with LFW
is unknown; training independence is not claimed. The public 0.1% empirical
constraint therefore does not promise a 0.1% private-domain false-positive rate.

Timing used the same local machine, running baseline then candidate, with cached
reference encoding after the first search. ONNX Runtime intra-op and inter-op
threads were verified as one. This OpenCV build uses GCD and reported 11 threads
before and after requesting one; that request was ineffective. Dlib exposes no
thread setter here. These are rough local timings, with no claim that the two
pipelines were controlled single-thread benchmarks. The measured slowdown is
material, but it does not identify detection, alignment or embedding as the
bottleneck.

Retain the current production model and preserve this frozen result. The next
experiment should start with a new predeclared protocol: instrument acquisition
and component timings to locate the bottleneck, then evaluate a lighter
alternative or a cascade against explicit recall, false-positive and latency
requirements. Any new threshold should be calibrated separately; do not retune
against this reviewed corpus. Use new independent evaluation data before making
a promotion claim. No alternative model or cascade was implemented by this run.
