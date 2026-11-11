# Offline face-search evaluation

This package compares a baseline and a candidate face-search adapter against a
local, labeled dataset. It calibrates each system's threshold on the
`calibration` split, freezes that threshold, and reports metrics on the `test`
split. These experimental thresholds do not change the production face-distance
threshold in `app/services/ai_service.py`.

## Run the CLI

From `apps/backend`, copy the example config and run:

```bash
cp evaluation.example.toml evaluation.toml
python -m app.evaluation --config evaluation.toml
```

The config paths are resolved relative to the config file:

```toml
manifest = "evaluation-manifest.toml"
output_dir = "evaluation-runs/example"

[baseline]
name = "face-search-baseline"

[candidate]
name = "face-search-candidate"
```

Without a `factory`, both roles use the current `FaceSearchAdapter`. To compare
another implementation, set `factory = "module:attribute"`; the callable is
constructed with `name` and any values in `[candidate.options]`. An adapter must
return one finite, higher-is-better score per gallery identity and must not make
its own thresholded match decision. No ONNX adapter is bundled or implied by the
current CLI.

## Local manifest

The manifest is TOML version 1. All media must be local files below
`media_root`; URLs and paths that escape that directory are rejected.

```toml
version = 1
media_root = "evaluation-media"

[[references]]
id = "alice-cal-reference"
identity = "alice"
path = "calibration/alice-reference.jpg"
split = "calibration"

[[references]]
id = "bob-test-reference"
identity = "bob"
path = "test/bob-reference.jpg"
split = "test"

[[scans]]
id = "alice-positive-calibration"
path = "calibration/alice-scan.jpg"
split = "calibration"
expected_identities = ["alice"]

[[scans]]
id = "bob-positive-test"
path = "test/bob-scan.jpg"
split = "test"
expected_identities = ["bob"]

[[scans]]
id = "negative-test"
path = "test/no-enrolled-identity.jpg"
split = "test"
expected_identities = []
```

Each expected identity needs a reference in the same split. Calibration and test
must contain disjoint identities, and the loader hashes media to reject the same
file content reused across the two splits. The manifest must include scans in
both splits. Keep evaluation photos private and outside source control; the CLI
only needs local paths and does not upload the dataset.

## Calibration and test

For each system, the runner evaluates calibration scans and chooses the
higher-is-better score threshold with the best F1, breaking ties by fewer false
positives and then the higher threshold. It then freezes that threshold for the
test split. Precision, recall, FPIR, FNIR, TPIR, error/no-face counts, and p50,
p95, and p99 latency are computed from test decisions. Errors are excluded from
the confusion matrix; a no-face result is a false negative for a positive scan
and a true negative for a negative scan.

## Artifacts

The output directory must not already exist. A successful run writes the bundle
atomically:

- `run.json` — run metadata, system names, and split counts
- `threshold.json` — calibrated threshold for each system
- `decisions.ndjson` — per-scan scores, decisions, errors, and latency
- `metrics.json` — test metrics for baseline and candidate
- `timings.ndjson` — per-scan latency rows
- `report.md` — human-readable comparison table

Use a new `output_dir` for every run so prior evidence is never overwritten.
