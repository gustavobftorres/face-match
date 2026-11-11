# Face Match Context

## Purpose

Face Match searches a local or remote photo collection for images containing a
person represented by reference media. The evaluation boundary runs this search
offline against declared local media so two implementations can be compared
without using a test set to tune their behavior.

## Ubiquitous language

- **Face Search**: a system that compares detected faces with a Gallery and
  returns a score for each identity. It does not decide whether a score is a
  match.
- **Reference Image**: local image associated with exactly one known identity.
- **Gallery**: the Reference Images available to Face Search for one split. A
  Gallery may contain multiple Reference Images for the same identity.
- **Scan**: one local image submitted to Face Search, with zero or more expected
  identities.
- **Evaluation Manifest**: versioned TOML inventory of Reference Images and
  Scans, including their `calibration` or `test` split and ground truth.
- **Evaluation Run**: one comparison in which baseline and candidate receive
  the same Scans and produce a durable artifact bundle.
- **Match Decision**: evaluator-owned interpretation of scores using a threshold
  calibrated on `calibration` and then frozen for `test`. Its result is
  `match`, `no_match`, `no_face`, or `error`.

## Evaluation rules

- Calibration and test identities are disjoint.
- Media paths are local, contained by the manifest's `media_root`, and exist
  before a run starts.
- Media content is SHA-256 checked and cannot be reused across calibration and
  test, even under different file names.
- Baseline and candidate see the same ordered Scans and the Gallery belonging
  to each Scan's split.
- When a face is found, Face Search returns exactly one aggregated Python
  `float` score per distinct Gallery identity, regardless of how many Reference
  Images represent that identity. Scores are finite and higher-is-better; only
  the evaluator creates a Match Decision.
- Test data never selects or changes a threshold.
- Errors are reported separately from image-level TP/FP/FN/TN.

## Example dialogue

> **Operator:** Compare the candidate Face Search with the baseline using this
> Evaluation Manifest.
>
> **Evaluator:** The calibration and test identities are disjoint. I will give
> both systems the same Scans, calibrate each threshold only on calibration,
> freeze it for test, and write the Evaluation Run artifacts.
>
> **Operator:** Did the candidate treat a photo without a detectable face as a
> failed match?
>
> **Evaluator:** Its Match Decision is `no_face`. For a positive Scan that
> contributes a false negative; it remains distinguishable from `no_match` and
> `error` in the decisions artifact.
