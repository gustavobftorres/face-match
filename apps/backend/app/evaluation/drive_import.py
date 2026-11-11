"""Read-only import of the explicitly reviewed public Drive evaluation corpus.

Uses the public embedded folder listing (all entries, unlike the 50-row Drive
bootstrap), HTTP redirects to resolve shortcuts, and unmodified original bytes.
No browser credentials, environment files, uploads, or application scans.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html import unescape
from io import BytesIO
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import time
import zipfile

import requests
from PIL import Image

ROOT = "1CluI1JKh4qjjbjYIlyAZbwzpesBeG2Dd"
FOLDERS = {
    "complete": "1SqJ50abrz50PBSlkCh67GXF2UX9Bji5R",
    "positive": "1vtAEDg4ybPdA-V4NkGedC-eRNjcMdquQ",
    "false_positive": "1kw0n4gcLyAV9Gm684HEVWXw8frEpifrv",
    "false_negative": "1pZCPd9xiDxcas5kge7DDe-bvgCUYd_c0",
    "reference": "1qyCtYrIHTPArqc237aSKBxC1jEMI6UnC",
}
MAX_BYTES = 50 * 1024 * 1024
EXPECTED_COUNTS = dict(complete=1205, positive=39, false_positive=42, false_negative=5, reference=1)
ZIP_FOLDERS = {'data-set-completo': 'complete', 'positivos': 'positive',
               'falso-positivos': 'false_positive', 'falso-negativo': 'false_negative',
               'referencia': 'reference'}
MAX_ARCHIVE_BYTES = 4 * 1024 ** 3


class ImportFailure(ValueError):
    pass


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ImportFailure("unsafe Drive file ID")
    return value


def parse_ivd(html):
    """Decode bootstrap rows for shortcut metadata; never implies completeness."""
    match = re.search(r"window\['_DRIVE_ivd'\] = '(.*?)';", html, re.S)
    if not match:
        raise ImportFailure("Drive bootstrap data absent")
    raw = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), match[1])
    rows = json.loads(raw.replace(r"\/", "/"))[0]
    return [dict(id=safe_id(r[0]), name=r[2], canonical_id=safe_id(r[131][0])
                 if r[3] == "application/vnd.google-apps.shortcut" else safe_id(r[0]))
            for r in rows]


def parse_embedded(html):
    if 'class="flip-entries"' not in html or not html.rstrip().endswith('</html>'):
        raise ImportFailure("public embedded folder listing absent or incomplete")
    if re.search(r'pageToken|nextPageToken|load-more|next-page', html, re.I):
        raise ImportFailure("embedded folder requires unsupported pagination")
    blocks = re.split(r'<div\b(?=[^>]*\bclass="flip-entry"(?:\s|>))', html)[1:]
    result = []
    for block in blocks:
        identity = re.search(r'id="entry-([A-Za-z0-9_-]+)"', block)
        name = re.search(r'<div class="flip-entry-title">(.*?)</div>', block, re.S)
        if not identity or not name:
            raise ImportFailure("unparseable embedded entry")
        result.append(dict(id=safe_id(identity[1]), name=unescape(name[1]),
                           shortcut='application/vnd.google-apps.shortcut' in block,
                           folder='/drive/folders/' in block or 'type/application/vnd.google-apps.folder' in block))
    if len({x['id'] for x in result}) != len(result):
        raise ImportFailure("duplicate IDs in embedded inventory")
    return result


def request(url, **kwargs):
    last = None
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=(15, 60), **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last = type(error).__name__
            if error.response is not None:
                last += f' HTTP {error.response.status_code}'
            if attempt < 2:
                delay = 2 ** attempt
                if error.response is not None and error.response.status_code in (429, 500, 502, 503, 504):
                    retry_after = error.response.headers.get('Retry-After', '')
                    delay = max(60, int(retry_after) if retry_after.isdigit() else 60)
                time.sleep(delay)
    raise ImportFailure(f"public Drive request failed: {last}")


def validate_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ImportFailure("image is empty or exceeds byte limit")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except Exception as error:
        raise ImportFailure("download is not a valid image") from error
    return sha256(data).hexdigest()


def download(identity, root, get=request):
    for attempt in range(3):
        try:
            return _download_once(identity, root, get)
        except requests.RequestException:
            if attempt == 2:
                raise ImportFailure('download stream failed after retries') from None
            time.sleep(2 ** attempt)


def _download_once(identity, root, get):
    identity = safe_id(identity)
    metadata = root / 'downloads' / f'{identity}.json'
    if metadata.exists():
        try:
            cached = json.loads(metadata.read_text())
            if not re.fullmatch(r'[0-9a-f]{64}', cached['sha256']):
                raise ImportFailure('invalid cached hash')
            path = root / 'media' / cached['sha256']
            data = path.read_bytes()
            digest = validate_image(data)
            if cached['sha256'] == digest:
                return dict(canonical_id=identity, sha256=digest, bytes=len(data), path=str(path.relative_to(root)))
        except (OSError, ValueError, KeyError):
            pass
    response = get(f'https://drive.usercontent.google.com/download?id={identity}&export=download', stream=True)
    try:
        if int(response.headers.get('Content-Length', '0')) > MAX_BYTES:
            raise ImportFailure("image exceeds byte limit")
        data = bytearray()
        for chunk in response.iter_content(256 * 1024):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ImportFailure("image exceeds byte limit")
        digest = validate_image(data)
    finally:
        response.close()
    path = root / 'media' / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    partial = root / 'downloads' / f'{identity}.part'
    partial.write_bytes(data)
    partial.replace(path)
    metadata.write_text(json.dumps(dict(sha256=digest, bytes=len(data))))
    return dict(canonical_id=identity, sha256=digest, bytes=len(data), path=str(path.relative_to(root)))


def media_key(entry):
    return entry.get('canonical_id') or entry['archive_key']


def source_provenance(entry):
    if 'archive_key' in entry:
        return dict(archive_sha256=entry['archive_sha256'], archive_entry=entry['archive_entry'])
    return dict(canonical_id=entry['canonical_id'])


def reconcile(inventories, media):
    """Fail closed on unmatched label copies, name/hash disagreement or overlaps."""
    complete = inventories['complete']
    by_hash = {}
    for entry in complete:
        by_hash.setdefault(media[media_key(entry)]['sha256'], []).append(entry)
    labels = {digest: set() for digest in by_hash}
    provenance = []
    conflicts = []
    for source in ('positive', 'false_negative', 'false_positive'):
        for entry in inventories[source]:
            digest = media[media_key(entry)]['sha256']
            matches = by_hash.get(digest, [])
            if not matches:
                conflicts.append(dict(source=source, id=entry['id'], reason='label copy hash absent from complete corpus'))
                continue
            labels[digest].add(source)
            provenance.append(dict(source=source, source_id=entry['id'], **source_provenance(entry),
                                   sha256=digest, complete_ids=[x['id'] for x in matches]))
    for digest, sources in labels.items():
        if 'false_positive' in sources and sources & {'positive', 'false_negative'}:
            conflicts.append(dict(sha256=digest, reason='positive and negative labels overlap'))
    references = {media[media_key(x)]['sha256'] for x in inventories['reference']}
    positive_hashes = {media[media_key(x)]['sha256'] for x in inventories['positive']}
    fn_hashes = {media[media_key(x)]['sha256'] for x in inventories['false_negative']}
    if not fn_hashes <= positive_hashes:
        conflicts.append(dict(reason='false-negative slice is not a subset of positives', hashes=sorted(fn_hashes - positive_hashes)))
    if len(references) != 1:
        conflicts.append(dict(reason='exactly one distinct reference image required'))
    return labels, references, provenance, conflicts


def bounded_map(function, values, workers):
    """Submit at most one small worker batch, so failures cancel pending work."""
    values = iter(values)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while True:
            batch = []
            for _ in range(workers):
                value = next(values, None)
                if value is None:
                    break
                batch.append(pool.submit(function, value))
            if not batch:
                break
            for future in batch:
                yield future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def publish_manifest(root, inventories, media, summary):
    labels, references, provenance, conflicts = reconcile(inventories, media)
    summary['conflicts'] = conflicts
    summary['label_provenance'] = provenance
    if conflicts:
        raise ImportFailure('label/reference conflicts; manifest withheld')
    reference_digest = next(iter(references))
    unique_media = {item['sha256']: item for item in media.values()}
    reference = unique_media[reference_digest]
    lines = ['version = 1', f'media_root = {json.dumps(str(root))}', '', '[[references]]',
             'id = "drive-reference"', 'identity = "drive-target"', f'path = {json.dumps(reference["path"])}', 'split = "test"']
    counts = dict(positive=0, negative=0, reference_excluded=0, duplicates=0, false_negative=0, false_positive=0)
    seen = set()
    scan_provenance = []
    for entry in inventories['complete']:
        item = media[media_key(entry)]
        digest = item['sha256']
        if digest == reference_digest:
            counts['reference_excluded'] += 1
            continue
        if digest in seen:
            counts['duplicates'] += 1
            continue
        seen.add(digest)
        sources = labels[digest]
        positive = bool(sources & {'positive', 'false_negative'})
        counts['positive' if positive else 'negative'] += 1
        counts['false_negative'] += 'false_negative' in sources
        counts['false_positive'] += 'false_positive' in sources
        lines += ['', '[[scans]]', f'id = "sha256-{digest}"', f'path = {json.dumps(item["path"])}',
                  'split = "test"', f'expected_identities = {json.dumps(["drive-target"] if positive else [])}']
        scan_provenance.append(dict(scan_id=f'sha256-{digest}', sha256=digest, source_id=entry['id'],
                                    **source_provenance(entry), slices=sorted(sources), positive=positive))
    if not seen:
        raise ImportFailure('no non-reference scans')
    staging = root / 'manifest.partial.toml'
    staging.write_text('\n'.join(lines) + '\n')
    staging.replace(root / 'manifest.toml')
    summary.update(status='complete', counts=counts, unique_downloads=len(media), scans=scan_provenance,
                   manifest=str(root / 'manifest.toml'), label_basis='user reviewed all complete corpus images; positives union false negatives present, all others absent')


def run(root, workers=1):
    root = Path(root).resolve()
    if root.is_relative_to(Path(__file__).resolve().parents[4]):
        raise ImportFailure('dataset output must be outside the Git repository')
    root.mkdir(parents=True, exist_ok=True)
    summary = dict(status='incomplete', source_root=ROOT, folders=FOLDERS, errors=[], conflicts=[], downloaded_bytes=0)
    summary_path = root / 'import-summary.json'
    resolved = {}
    unique = {}
    # A failed rerun must not leave an older runnable manifest behind.
    manifest = root / 'manifest.toml'
    if manifest.exists():
        manifest.replace(root / 'manifest.previous.toml')
    try:
        inventories = {}
        for label, folder in FOLDERS.items():
            html = request(f'https://drive.google.com/embeddedfolderview?id={folder}').text
            entries = parse_embedded(html)
            if not entries or any(x['folder'] for x in entries):
                raise ImportFailure(f'{label}: missing images or unexpected nested folder')
            if len(entries) != EXPECTED_COUNTS[label]:
                raise ImportFailure(f'{label}: snapshot count mismatch, expected {EXPECTED_COUNTS[label]}, got {len(entries)}')
            inventories[label] = entries
            print(f'inventory {label}: {len(entries)} entries', flush=True)
        summary['inventory_counts'] = {k: len(v) for k, v in inventories.items()}
        summary['folder_listings_complete'] = True
        (root / 'inventory.json').write_text(json.dumps(inventories, indent=2))
        unique = {x['id']: x for entries in inventories.values() for x in entries}
        cache_path = root / 'resolved.json'
        resolved = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        def resolve(entry):
            if not entry['shortcut']:
                return entry['id'], entry['id']
            if entry['id'] in resolved:
                return entry['id'], safe_id(resolved[entry['id']])
            # Public file-view endpoints rate-limit bursts; keep the small worker
            # pool and space requests even when the preceding request was fast.
            time.sleep(2)
            try:
                response = request(f'https://drive.google.com/file/d/{entry["id"]}/view')
            except ImportFailure as error:
                raise ImportFailure(f'shortcut {entry["id"]} ({entry["name"]}): {error}') from error
            match = re.fullmatch(r'https://drive.google.com/file/d/([A-Za-z0-9_-]+)/view(?:\?.*)?', response.url)
            if not match or match[1] == entry['id']:
                raise ImportFailure('shortcut target unresolved')
            return entry['id'], safe_id(match[1])
        for count, (source, target) in enumerate(bounded_map(resolve, unique.values(), workers), 1):
            resolved[source] = target
            if count % 25 == 0:
                cache_path.write_text(json.dumps(resolved, indent=2))
                print(f'resolved {count}/{len(unique)} entries', flush=True)
        cache_path.write_text(json.dumps(resolved, indent=2))
        for entries in inventories.values():
            for entry in entries:
                entry['canonical_id'] = resolved[entry['id']]
        (root / 'inventory.json').write_text(json.dumps(inventories, indent=2))
        summary['inventory_complete'] = True
        identities = sorted(set(resolved[x] for x in unique))
        media = {}
        for count, result in enumerate(bounded_map(lambda x: download(x, root), identities, workers), 1):
            media[result['canonical_id']] = result
            summary['downloaded_bytes'] += result['bytes']
            if count % 25 == 0:
                print(f'downloaded {count}/{len(identities)}; bytes={summary["downloaded_bytes"]}', flush=True)
        (root / 'media.json').write_text(json.dumps(media, indent=2))
        publish_manifest(root, inventories, media, summary)
    except Exception as error:
        if manifest.exists():
            manifest.unlink()
        (root / 'manifest.partial.toml').unlink(missing_ok=True)
        summary['errors'].append(dict(type=type(error).__name__, message=str(error) if isinstance(error, ImportFailure) else 'import failed; inspect local execution'))
        print(f'import incomplete: {summary["errors"][-1]}', flush=True)
    finally:
        summary['resolved_source_ids'] = len(resolved)
        summary['expected_source_ids'] = len(unique)
        summary['stored_unique_images'] = len(list((root / 'media').glob('*'))) if (root / 'media').exists() else 0
        summary['stored_image_bytes'] = sum(p.stat().st_size for p in (root / 'media').glob('*') if p.is_file()) if (root / 'media').exists() else 0
        summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def zip_members(archive):
    """Validate every member before reading originals; never extract paths."""
    members = archive.infolist()
    if len(members) > 10000 or sum(x.file_size for x in members) > MAX_ARCHIVE_BYTES:
        raise ImportFailure('archive exceeds member or decompression limit')
    seen = set()
    for item in members:
        path = PurePosixPath(item.filename)
        if (not item.filename or '\\' in item.filename or path.is_absolute()
                or '..' in path.parts or ':' in item.filename or '\x00' in item.filename):
            raise ImportFailure('unsafe ZIP member path')
        if item.filename in seen:
            raise ImportFailure('duplicate ZIP member path')
        seen.add(item.filename)
        mode = item.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ImportFailure('ZIP links or special files are forbidden')
        if item.flag_bits & 1 or item.volume:
            raise ImportFailure('encrypted or split-volume ZIP is unsupported')
        if item.is_dir():
            continue
        if item.file_size > MAX_BYTES or item.file_size > max(1, item.compress_size) * 200:
            raise ImportFailure('ZIP member exceeds image or compression ratio limit')
        if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ImportFailure('unsupported ZIP compression')
        matches = [(i, ZIP_FOLDERS[part]) for i, part in enumerate(path.parts) if part in ZIP_FOLDERS]
        if len(matches) != 1 or matches[0][0] != len(path.parts) - 2:
            raise ImportFailure('ZIP image is outside a recognized corpus folder')
        yield item, matches[0][1]


def import_zip(archive_paths, root):
    """Import all parts of an official Drive ZIP export, without any network."""
    root = Path(root).resolve()
    if root.is_relative_to(Path(__file__).resolve().parents[4]):
        raise ImportFailure('dataset output must be outside the Git repository')
    root.mkdir(parents=True, exist_ok=True)
    media_dir = root / 'media'
    media_dir.mkdir(exist_ok=True)
    if not media_dir.resolve().is_relative_to(root):
        raise ImportFailure('media directory escapes dataset root')
    manifest = root / 'manifest.toml'
    if manifest.exists():
        manifest.replace(root / 'manifest.previous.toml')
    summary = dict(status='incomplete', source_kind='official_drive_zip', source_root=ROOT,
                   errors=[], conflicts=[], archives=[])
    inventories = {label: [] for label in FOLDERS}
    media = {}
    try:
        paths = [Path(p).resolve() for p in archive_paths]
        if not paths or len(set(paths)) != len(paths):
            raise ImportFailure('provide every distinct ZIP export part')
        validated = []
        logical_paths = set()
        total_bytes = 0
        for path in paths:
            if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ImportFailure('archive missing or too large')
            digest = sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            archive_hash = digest.hexdigest()
            with zipfile.ZipFile(path) as archive:
                members = list(zip_members(archive))
                for item, label in members:
                    if item.filename in logical_paths:
                        raise ImportFailure('overlapping ZIP export parts')
                    logical_paths.add(item.filename)
                    total_bytes += item.file_size
                    if total_bytes > MAX_ARCHIVE_BYTES:
                        raise ImportFailure('combined archives exceed decompression limit')
                    key = f'zip:{archive_hash}:{item.filename}'
                    entry = dict(id=key, archive_key=key, archive_sha256=archive_hash,
                                 archive_entry=item.filename, name=PurePosixPath(item.filename).name)
                    inventories[label].append(entry)
                    validated.append((path, item.filename, entry))
            summary['archives'].append(dict(path=str(path), sha256=archive_hash, bytes=path.stat().st_size))
        summary['inventory_counts'] = {label: len(entries) for label, entries in inventories.items()}
        for label, entries in inventories.items():
            if len(entries) != EXPECTED_COUNTS[label]:
                raise ImportFailure(f'{label}: snapshot count mismatch, expected {EXPECTED_COUNTS[label]}, got {len(entries)}; missing export parts or placeholders')
        summary['inventory_complete'] = True
        (root / 'inventory.json').write_text(json.dumps(inventories, indent=2))
        # Read bounded bytes through ZipFile to check CRCs. Member paths are
        # provenance only; no archive path is ever used as a filesystem target.
        for path in paths:
            with zipfile.ZipFile(path) as archive:
                for archive_path, entry_path, entry in validated:
                    if archive_path != path:
                        continue
                    with archive.open(entry_path) as stream:
                        data = stream.read(MAX_BYTES + 1)
                    digest = validate_image(data)
                    target = media_dir / digest
                    if target.is_symlink():
                        raise ImportFailure('media target is a symlink')
                    if not target.exists() or sha256(target.read_bytes()).hexdigest() != digest:
                        temporary = media_dir / f'{digest}.part'
                        temporary.write_bytes(data)
                        temporary.replace(target)
                    media[entry['archive_key']] = dict(sha256=digest, bytes=len(data), path=str(target.relative_to(root)))
        (root / 'media.json').write_text(json.dumps(media, indent=2))
        publish_manifest(root, inventories, media, summary)
    except Exception as error:
        manifest.unlink(missing_ok=True)
        (root / 'manifest.partial.toml').unlink(missing_ok=True)
        summary['errors'].append(dict(type=type(error).__name__, message=str(error) if isinstance(error, ImportFailure) else 'ZIP import failed; corrupt or incomplete archive'))
    finally:
        summary['stored_unique_images'] = len([p for p in media_dir.iterdir() if re.fullmatch('[0-9a-f]{64}', p.name)])
        summary['stored_image_bytes'] = sum(p.stat().st_size for p in media_dir.iterdir() if re.fullmatch('[0-9a-f]{64}', p.name))
        (root / 'import-summary.json').write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/private/tmp') / f'face-match-dataset-{ROOT}')
    parser.add_argument('--workers', type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument('--zip', type=Path, nargs='+', dest='archives', help='all official Drive ZIP export parts; offline import')
    args = parser.parse_args()
    summary = import_zip(args.archives, args.output) if args.archives else run(args.output, args.workers)
    raise SystemExit(0 if summary['status'] == 'complete' else 1)


if __name__ == '__main__':
    main()
