# Collect calibration photos for YuNet + AuraFace

Initial calibration can use a public identity dataset after checking its
availability, terms and suitability. New manual collection is optional and can
wait; it is not a prerequisite for implementing the adapter. Keep the original
target and its photos out of calibration: that person is a distinct test target
for a later `test_only` run with a frozen threshold. These instructions do not
require running the full existing photo corpus or tuning on its labels.

## Public data options

Screen the actual download and allowed use before choosing a dataset; this
change does not download datasets or run a benchmark. Public availability does
not by itself establish permission for your intended use.

| Dataset | Useful evidence and limitations |
| --- | --- |
| [LFW via scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_lfw_people.html) | Identity labels for 13,233 face images of 5,749 people. The loader supports selecting people with enough images. These are face crops, so they can support an initial identity/calibration check but are a limited proxy for full event frames, tiny faces and groups. The loader's defaults further crop/resize and use grayscale; choose and document preprocessing deliberately. Check upstream dataset terms and download availability first. |
| [WIDER FACE](https://arxiv.org/abs/1511.06523) | A face detection benchmark covering scale, pose and occlusion. It does not supply the person identity labels needed for this evaluator's identity threshold calibration; use it for detection evidence separately. |
| [CelebA](https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html) | 202,599 images and 10,177 identities. Its agreement restricts use to non-commercial research, restricts redistribution and states that face identities are released upon request for research. Confirm access to identity annotations and applicable terms before choosing it. |
| [IJB-A/B/C](https://www.nist.gov/programs-projects/face-challenges) | NIST discontinued distribution on March 14, 2023. Do not assume an official automatic download is available or use an unverified mirror. |

For identity data, choose identity-disjoint calibration/test people, separate
reference and scan images, preserve source IDs and dataset provenance, and use
the single-target labeling rules below. For a generalization claim, public-data
thresholds still need a later untouched domain holdout; celebrity face crops do
not establish event photo performance.

Reusing the existing dataset as a fixed before/after benchmark is useful. Freeze
the model, preprocessing and published or externally calibrated decision
threshold before comparing it. Since its earlier errors have already been
inspected, report it as a descriptive benchmark rather than an entirely sealed,
independent holdout. Do not use its labels or observed errors to adjust candidate
parameters. Fresh independent data is needed for a later claim of generalization,
not for implementing the adapter or making a clearly scoped exploratory comparison.

## An optional collection closer to the intended photos

When you choose to collect your own photos, aim for **5–10 different calibration
people**, with **one single-face reference and 10–20 confirmed positive photos
per person**. Use photos from different
sessions, not crops, bursts or resized copies of the reference. If collecting
that many people is impractical, start with **at least 3 people** and describe
the smaller coverage when reporting results.

Collect **500–1,000 negative images** with visible faces and manually confirmed
absence of the target for the run. A negative pool can be reused for separate
target runs within calibration when each target is confirmed absent; it need
not contain 500–1,000 new images per person. Images containing another
calibration person can be negative for the current target, provided that person
is not in the current run's gallery and the current target is absent.

Cover the conditions you expect in use: frontal and turned faces, profile or
partial occlusion, night or low light, smaller distant faces, and groups with
background faces. Record the conditions, independent photo sessions and
uncertain cases in private notes. Exclude uncertain identities or uncertain
target absence until a human can resolve them. Optional no-face images are
useful checks but do not replace negatives with other people in them.

These quantities are engineering starting points for checking behavior and
between-person variation. They do not establish population-wide performance or
prove a low rare-error rate. Record the actual evaluated counts, errors and
no-face results alongside the metrics.

## Use one target per run

The current evaluator uses **image-level any-identity metrics**: a positive is
successful when any expected identity is predicted, and extra wrong identities
on that positive are not counted separately as false positives. Putting all
calibration people into one gallery would hide some mistakes.

Create separate runs with exactly one gallery identity in each split. For a
chosen calibration target, label every confirmed target-present scan with
`expected_identities = ["cal-target-id"]`; label a confirmed target-absent scan
with `expected_identities = []`, even when other known people appear. Always
label against the gallery used in that run. Never copy a person's negatives
into a run for another target without checking that the new target is absent.
Never mark a negative against a gallery that includes someone visible in it.

For example, a photo of person B alone is negative in A's single-target run
and positive in B's single-target run. It is not a negative in a gallery
containing both A and B. Keep reusable calibration photos and all people visible
in them out of the held-out split; the manifest cannot recognize undeclared
background identities or detect near-duplicate photos.

The `calibration_test` mode requires both splits, with different identities and
no identical file bytes across them. Reserve a separate evaluation person and
photos for its test split, also outside calibration; keep the original target
separate for the later descriptive benchmark. For each separate run, pair its one
calibration target with a distinct test target. Repeating tests on the same
held-out person is exploratory evidence and does not create fresh independent
validation. A common candidate threshold eventually needs a documented,
calibration-only selection process across these people; separate per-person F1
thresholds alone do not establish a shared deployment threshold.

## Configure and preserve the run

Keep photos, manifests, identity mappings and output bundles private, preferably
outside the repository. Follow the [manifest and labeling guide](evaluation-dataset.md)
and copy the [candidate configuration](../apps/backend/evaluation.candidate.example.toml).
Follow the [runtime setup](candidate-models.md#isolated-runtime): the comparison's
Dlib baseline requires both base and candidate dependency files in the same
environment; a fresh candidate-only environment is for native smoke checks.
Replace paths with verified local model artifacts; the adapter never downloads
weights. For reproducibility, record expected model SHA-256 hashes, the
preprocessing settings and the runtime providers. The adapter's public
`describe()` metadata is captured as a finite JSON snapshot before any model
inference, including model hashes, preprocessing version and available runtime
package versions. Existing adapters without `describe()` continue to work.

Use the baseline's existing `production_distance` policy and the candidate's
`calibrate_f1` policy while collecting calibration evidence. The candidate's
cosine scores are higher-is-better. F1 selects a threshold using calibration
only; it is frozen for that run's test split. Do not select a threshold by
looking at the original target's results.

For the later original-target holdout, use a separate test-only manifest and
`mode = "test_only"`. Keep the baseline `production_distance`; set the candidate
to `fixed_similarity` with an **explicit finite threshold in [-1, 1]** taken
from the documented external calibration process. A score equal to this
threshold is accepted (`>=`). There is no candidate default threshold.
`threshold_source = "external_calibration"` records your declaration; it does
not load or verify calibration evidence. An unspecified source is recorded as
`provided_fixed`. Fixed policies always record `calibrated_on = null` for the
current run, and test-only mode rejects F1 calibration policies.

Keep the model hashes and preprocessing settings unchanged between calibration
and test. Save `threshold.json`, `run.json`, per-image decisions and the
selection rationale together. Reuse the fixed benchmark for comparisons, but do
not keep adjusting the threshold against its errors and then call the result an
independent validation; further tuning needs fresh held-out data for that claim.
