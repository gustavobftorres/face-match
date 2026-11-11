# Import the reviewed public Drive corpus

Run from `apps/backend` using the existing backend environment:

```bash
venv/bin/python -m app.evaluation.drive_import --output /path/to/private-corpus
```

Choose an output directory outside the repository and keep it private and outside
Git. The command only reads public Drive
resources. It never uploads, changes sharing, loads `.env`, reads browser tokens,
or invokes the app's scan endpoints.

The importer uses the public embedded folder view because ordinary Drive HTML
bootstrap data includes only 50 entries. This reviewed snapshot must contain
1,205 complete-corpus entries, 39 positive copies, 42 false-positive copies,
5 false-negative copies, and one reference. Every folder must match its expected
count, have a complete HTML response, and contain no nested folder or pagination
marker. A changed or truncated snapshot stops import; update these expectations
only after reviewing a new snapshot. Shortcut IDs resolve through public file-view
redirects to canonical target IDs. The bootstrap parser independently supports
the `row[131][0]` target metadata and never treats bootstrap rows as complete.

The default uses one worker, spacing uncached public shortcut resolutions by
two seconds; two to four workers are optional. HTTP 429 and transient server
responses wait at least 60 seconds and respect a longer `Retry-After`. Persistent
rate limits stop the import after three attempts; obtain an authorized API export
or ZIP rather than repeatedly retrying an unavailable public endpoint.
Downloads use bounded
timeouts and retries, and a 50 MiB per-image ceiling. PIL verifies image bytes;
HTML confirmation/login pages are rejected. Original bytes are stored once per
SHA-256 under `media/`. Per-ID checksum metadata and resolved shortcut targets
allow reruns to resume. Corrupt cached media is downloaded again. Failed partial
downloads never become accepted images. Use the same output directory to resume.

`inventory.json`, `resolved.json`, and `media.json` preserve source IDs, canonical
IDs, original names, hashes, byte counts, and paths. `import-summary.json` records
completion, errors, conflicts, raw folder counts, unique scans, duplicates,
reference exclusions, labels, and historical false-positive/false-negative slices.
It can contain sensitive provenance and must remain alongside the private data.

The labels rely on the user's explicit review of every complete-corpus image:
positives and false negatives contain the target; false positives and remaining
images do not. Positive/negative copy correspondence uses exact image hashes,
never filenames. Any label copy absent from the complete corpus, conflicting
positive/negative labels, a false-negative hash outside the positive subset, or
missing/ambiguous reference stops manifest creation. Duplicate media is one scan;
reference bytes are excluded from scans, including renamed copies.

`manifest.toml` is published atomically only after the complete inventory,
downloads, and label reconciliation succeed. A failed rerun withholds the current
manifest and preserves the old one as `manifest.previous.toml`; do not use that
backup to treat an incomplete rerun as successful. A successful manifest has
version 1 and only `test` records. Load it with
`load_manifest(path, mode="test_only")`, and evaluate with fixed policies only.
This importer does not run the benchmark or calibrate thresholds.

## Official ZIP export fallback

If the public file-view endpoint is rate limited, an official Drive download
can supply the original media without making more public metadata requests.
After all export parts have finished downloading, import them offline:

```bash
venv/bin/python -m app.evaluation.drive_import --output /path/to/private-corpus --zip /path/to/export-part1.zip /path/to/export-part2.zip
```

Supply one path for a single archive or every path for a multipart export. The
importer expects the folders `data-set-completo`, `positivos`, `falso-positivos`,
`falso-negativo`, and `referencia`, optionally underneath an export root such as
`avaliacao/`. Frozen counts remain 1205 / 39 / 42 / 5 / 1; missing parts or
shortcut placeholders cannot produce a runnable manifest.

Archive paths are never extracted. The importer rejects path traversal,
symlinks, special files, encrypted or split-volume ZIPs, unsupported compression,
overlapping members, excessive compression ratios, images over 50 MiB, and
combined decompressed contents over 4 GiB. Image reads check ZIP CRCs and PIL
validity. Original bytes are stored under their SHA-256 as with the public
import; labels and reference exclusions use the same reconciliation rules.
ZIP provenance records archive SHA-256 and member path instead of inventing
Drive target IDs. This mode makes no network requests.
