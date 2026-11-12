# Dlib threshold replay result — 2026-11-12

The public-LFW-selected Dlib operating point substantially reduced false positives in an offline replay of the existing comparison scores: **42 → 4 FP**, while true positives changed **35 → 34**. Precision increased from **45.45% to 89.47%**, with recall changing from **89.74% to 87.18%**. This is a promising operating point for further Dlib validation. Production configuration was not changed automatically.

The threshold was selected exclusively using public LFW View 1 development pairs, before replaying the private results. The objective maximized completed-pair empirical TPR subject to empirical FPR ≤ 0.001, with stricter thresholds breaking ties. The selected rule is strictly `negative_distance > -0.5567551387797269`, equivalently `distance < 0.5567551387797269`. Public calibration completed 1,090 mated and 1,089 nonmated pairs: TP 1,020, FP 1, empirical TPR 93.58%, and empirical FPR 0.09183%. Public errors/missing faces were excluded from threshold fitting and reported separately in the approved calibration receipt.

The replay ran on 2026-11-12 at 16:27:51 UTC. It reused the original comparison's 2026-11-12 recorded Dlib scores and labels: 1,202 test scans, comprising 39 positive and 1,163 negative scans with one reference identity. It performed no image reads, inference, model downloads, or private-label threshold optimization. Before applying the new threshold, it verified the approved public receipt and linked artifact hashes, source-plan hash, code/runtime compatibility, source counts and labels, original strict `score > -0.6` decisions, and stored baseline metrics. The replay plan was frozen before writing new decisions.

| Recorded system / policy | TP | FP | FN | TN | Precision | Recall | FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dlib original, distance < 0.6 | 35 | 42 | 4 | 1,121 | 45.45% | 89.74% | 3.61135% |
| Dlib public-LFW threshold replay | 34 | 4 | 5 | 1,159 | 89.47% | 87.18% | 0.34394% |
| YuNet + AuraFace, original recorded comparison | 31 | 5 | 8 | 1,158 | 86.11% | 79.49% | 0.42992% |

The new Dlib rule removed 39 previous acceptances: **38 false positives corrected (90.48% of the original 42)** and one true positive lost. It introduced **zero new acceptances**. The original and replayed Dlib outcomes both contain zero errors and 155 missing-face results; usable-score coverage is 1,047 / 1,202 = 87.10%. Missing faces remain FN for positive scans and TN for negative scans. Because this run has zero errors, end-to-end recall/FPR equal the table's recall/FPR; end-to-end positive misses changed from four to five.

The AuraFace row is a descriptive comparison using the same 1,202 saved test outcomes, with no new candidate inference or calibration. Of the 39 positives, calibrated Dlib and AuraFace both accept 31, only calibrated Dlib accepts three, only AuraFace accepts zero, and neither accepts five. Among negatives, their false-positive sets do not overlap: four are accepted only by calibrated Dlib, five only by AuraFace, and 1,154 by neither. These aggregates describe this corpus; they do not establish superiority or generalization to other identities or acquisition conditions.

**Original inference timings; not remeasured by replay.** Dlib's recorded p50 / p95 / p99 remain 194.692458 / 227.345250 / 245.814666 ms. Replay simply retains these measurements. They provide no new latency benchmark for the calibrated policy, and replay runtime is not inference latency.

Public calibration is in-sample rather than an independent validation. LFW central-face labels differ from the production any-face scan policy, Dlib pretraining overlap is unknown, and the private corpus has only 39 positives. The public FPR objective is a calibration constraint, not a promised private-domain FPR: the observed replay FPR is 0.34394%. The historical comparison did not record hashes of the Dlib weights/binary actually used. Their past bytes cannot be cryptographically verified. Current public implementation/runtime/weight hashes and historical code/version compatibility were checked, but the recorded historical scores remain authoritative for replay.

The next activity should independently validate this operating point on fresh holdout data. If appropriate after that validation, introduce a configurable production distance threshold as a separate change with explicit rollout decisions. This replay does not authorize or implement a production threshold change.

## Frozen artifacts

Private per-image replay artifacts remain outside Git at `/private/tmp/face-match-dlib-threshold-replay`; this document contains only reviewed aggregates. The approved public receipt is `/private/tmp/face-match-dlib-lfw-calibration/threshold-result.json`. See [the replay procedure](dlib-threshold-replay.md) for validation and metric conventions.

| Artifact | SHA-256 |
| --- | --- |
| Approved public calibration receipt | `5851aaeef6b698260b3e63a91473f47209fc46a889119becc4c4a58bb7fe3f3d` |
| Public calibration protocol | `29bdfa12195749771953ed58a0b09c8ddc2a5e10682049c5035c86904f67b62b` |
| Public calibration scores | `62ff9a10fbfa33e4a8d27efbd76002df437a7a57fbf82ac06d96aa8a3860ebed` |
| Public calibration decisions | `4bc08534d996b9ff05152abdd52ad822c3b3acf08cbf8e7f343d19a1b9864938` |
| Approved original comparison plan | `9c2b3b5a24d521b7478f3cb1b103207f7fe10a81e065c95d68bf86c6e4a62e5f` |
| Frozen replay plan | `077b47ebb9cd9af9fea2c4af722f67d77bff502eea7bd2b62f1d8df97013b69c` |
| Replay decisions | `a706b7523dbde4cdc686c89f4f64aa4bcab0b4d7737c58ff12d6c8906ee3ea3c` |
| Replay summary | `41ccc55a43a6a2e96d923a63eac2f7ce1470f39dc51567ed18cadd1046e70208` |
