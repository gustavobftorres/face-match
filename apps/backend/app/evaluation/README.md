# Offline face-search evaluation

This package compares a baseline and a candidate face-search adapter against a
local, labeled dataset. Each role declares a fixed production distance threshold
or an F1 threshold selected on `calibration`. Both thresholds are frozen for
`test`. These evaluation policies do not change the production face-distance
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
name = "dlib-production-baseline"
policy = "production_distance"
threshold = 0.6

[candidate]
name = "face-search-candidate"
policy = "calibrate_f1"
```

Policy settings belong inside `[baseline]` or `[candidate]`, independently:

- `policy = "calibrate_f1"` is the default when omitted. Do not provide
  `threshold` with this policy. Without `factory`, it selects the legacy
  `FaceSearchAdapter`, with `1 - distance` scores and a `>=` score comparator.
- `policy = "production_distance"` defaults to raw distance `threshold = 0.6`.
  Without `factory`, it selects `DlibProductionAdapter`, returning `-distance`
  scores. The evaluator applies `score > -threshold`, preserving production's
  strict `distance < 0.6` boundary. This adapter requires exactly one reference
  per identity, uses only its first encoded face, and compares it with all
  detected scan faces. Prepare references containing exactly one face.

The example compares production decisions with a recalibrated policy using the
same underlying face model. This is a policy comparison, not a model
improvement; the adapters also differ in reference aggregation when multiple
faces or references are allowed. No real benchmark result is supplied.

To compare another implementation, set `factory = "module:attribute"`; the callable is
constructed with `name` and any values in `[candidate.options]`. An adapter must
return one finite, higher-is-better score per gallery identity and must not make
its own thresholded match decision. No ONNX adapter is bundled or implied by the
current CLI.

For a complete six-file placeholder manifest and manual ground-truth workflow,
see [dataset preparation](../../../../docs/evaluation-dataset.md). The snippet
below illustrates the schema; its paths are placeholders.

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

For each `calibrate_f1` role, the runner evaluates calibration scans and chooses the
higher-is-better score threshold with the best F1, breaking ties by fewer false
positives and then the higher threshold. It then freezes that threshold for the
test split. A `production_distance` role retains its fixed distance threshold;
calibration never tunes it. Precision, recall, FPIR, FNIR, TPIR, error/no-face counts, and p50,
p95, and p99 latency are computed from test decisions. Errors are excluded from
the confusion matrix; a no-face result is a false negative for a positive scan
and a true negative for a negative scan.

These are image-level metrics. A positive is a TP when any predicted identity
overlaps its expected identities; extra incorrect identities on that positive
are not separately counted as FP. Start with one target per search and inspect
per-scan output and excluded error counts.

## Artifacts

The output directory must not already exist. A successful run writes the bundle
atomically:

- `run.json` — run metadata, system names, split counts, and provenance
- `threshold.json` — each role's score threshold, policy, comparator, score
  semantics, raw distance threshold where applicable, and calibration source
- `decisions.ndjson` — per-scan scores, decisions, errors, and latency
- `metrics.json` — test metrics for baseline and candidate
- `timings.ndjson` — per-scan latency rows
- `report.md` — human-readable comparison table

Use a new `output_dir` for every run so prior evidence is never overwritten.

Provenance records dataset labels and SHA-256 hashes of reference/scan bytes,
adapter identities, decision policies, Python/platform and selected installed
package versions, Git commit, and dirty status when available. It does not hash
model weights or capture the full uncommitted source diff. Retain exact code
and model environments separately for reproduction. Latencies are local
observations affected by hardware, caching, and run conditions, not a portable
performance benchmark. Keep artifacts private with the dataset.
