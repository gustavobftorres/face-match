# Prepare a private evaluation dataset

The offline evaluator needs manually verified local photos before a baseline
can produce useful evidence. No photos or verified identities are supplied by
this repository. The [example manifest](../apps/backend/evaluation-manifest.example.toml)
contains only explicit fictitious paths and valid TOML structure; it will fail
the loader's file checks until you replace them with real files.

## Label the media before running a model

1. Create a private directory **outside the Git repository**, for example a
   local `evaluation-media` directory with `calibration/` and `test/` children.
   Keep the mapping between pseudonymous identity IDs and real people private.
   Store labeling notes there too: who confirmed each label, the photo/session
   source, and unresolved cases. Use media you are authorized to evaluate.
2. Start with **one target person per search**: one gallery identity for
   calibration and a different gallery identity for test. Assign each person
   to exactly one split before selecting photos. Keep other recognizable people
   in the negative photos in only one split as well; the loader can check
   declared identities and duplicate bytes, not recognize unlabeled people.
3. Pick a reference showing exactly one face, belonging to the known target.
   Confirm this manually with someone who knows the person or trustworthy
   source records. Do not use the model's score to establish identity.
4. Pick positive scans whose target identity is confirmed independently. Use
   different photos from the reference, preferably from different capture
   sessions, with realistic changes in pose, light, distance, and background.
   Avoid reference crops, resized copies, bursts, and near duplicates as
   substitutes for independent examples. A positive may contain other people,
   provided the target's presence is certain.
5. Pick negative scans containing visible faces of **other people**, with the
   split's target confirmed absent. Manually inspect every face, including
   background faces. If presence or absence is uncertain, set that photo aside
   in the private notes and exclude it from the manifest until resolved.
   Uncertain absence is never a negative label. Optional photos with no faces
   can exercise `no_face`, but do not replace negatives containing other faces.
6. Record each positive's `expected_identities = ["the-target-id"]` and each
   confirmed negative's `expected_identities = []`. Every positive identity
   must have a reference in the same split. Use stable, unique reference IDs
   and scan IDs. Review labels before inspecting either model's output and
   freeze the manifest and media for a comparison.

## Copy and fill the local files

From `apps/backend`:

```bash
cp evaluation-manifest.example.toml evaluation-manifest.toml
cp evaluation.example.toml evaluation.toml
```

In `evaluation-manifest.toml`, replace `media_root` with your private directory's
absolute path and replace all six placeholder paths. Reference and scan paths
are relative to `media_root` and must stay inside it. Use six distinct real
files for the first run: one reference, one positive scan, and one negative
scan in each split. Keep the two targets disjoint. The loader checks existence,
containment, expected identities, and SHA-256 content reuse across splits;
renaming a duplicate does not make it independent. It cannot verify faces or
ground truth for you.

The root `.gitignore` protects conventional `evaluation-media/` and
`evaluation-runs/` directories at any depth, `evaluation.toml`,
`evaluation-manifest.toml`, named `evaluation-manifest-*.toml` files, and
`evaluation.local.toml` / `evaluation-*.local.toml` variants. The example
manifest remains tracked. Prefer external private storage even with these
guards; arbitrary filenames and already tracked files are not protected by
ignore rules. Check `git status --short` before committing.

In `evaluation.toml`, point `manifest` at the local manifest and choose a new,
unused `output_dir` for every run. Config paths are relative to the config
file; `media_root` is relative to the manifest unless absolute. Run:

```bash
python -m app.evaluation --config evaluation.toml
```

The example config compares `production_distance` for the baseline with
`calibrate_f1` for the candidate. The production baseline uses one reference
per identity and its first encoded face only; use a single-face reference.
Its raw distance threshold defaults to `0.6`, represented as `-distance` scores
with a strict `> -0.6` comparator. The candidate uses the legacy FaceSearch
adapter's `1 - distance` scores with a `>=` threshold calibrated on calibration.
This uses the same underlying face model and compares decision policies; it
does not demonstrate a model improvement or provide a real benchmark. See the
[evaluator README](../apps/backend/app/evaluation/README.md) for custom adapter
factories and the artifact bundle. Artifacts may contain media paths, labels,
and scores: keep them private alongside the input records. `threshold.json`
records policy, comparator, score semantics, and fixed/calibrated thresholds.
`run.json` provenance includes input SHA-256 hashes, labels, adapter identities,
policies, Python/platform, selected package versions, and Git commit/dirty
status when available. Model weights are not hashed and an uncommitted source
diff is not captured; preserve those separately for reproducibility. Timing
reflects the local machine, caches, and run conditions.

## Smoke check versus meaningful evaluation

The six-file setup has two references and four scans. Use it to check loading,
face detection, labeling, calibration, and artifact generation. A single
positive and negative per split cannot establish accuracy or select a robust
threshold.

For a real comparison, collect many more confirmed positives and negatives
from independent sessions and the conditions relevant to the intended photo
collection. For example, a next collection pass could target tens of positives
and tens of negatives per split; that is a planning quantity, not a claim of
statistical validity or a required sample size. Preserve the one-target search
setup and run separate comparisons with other disjoint target pairs to inspect
variation between people. Record actual counts, conditions, and exclusions
when reporting results. Keep test labels and media fixed; calibrate F1 thresholds
only on calibration, retain the production policy's fixed distance threshold,
freeze both for test, and use fresh held-out data after
repeated tuning against previous test results.

## Interpret the current metrics

Metrics are **image-level**, not per face or per identity. A positive scan is
a true positive if any predicted identity overlaps its expected identities;
otherwise it is a false negative. A negative scan is a false positive if any
gallery identity is predicted, otherwise a true negative. With multiple gallery
identities, extra wrong predictions on a positive image are not separately
counted as false positives. Start with one target per search so this limitation
does not hide incorrect additional identities.

`no_face` counts as a false negative on a positive and a true negative on a
negative. `error` decisions are counted separately and excluded from TP/FP/FN/TN
and the derived accuracy metrics. Inspect errors, `no_face`, evaluated-image
counts, and per-scan decisions alongside precision, recall, FPIR, FNIR, TPIR,
and latency. A high reported metric with many excluded errors is incomplete
evidence. These results do not establish per-face identification accuracy,
population-wide performance, or statistical validation.
