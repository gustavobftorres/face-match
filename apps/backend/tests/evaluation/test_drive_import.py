import json
from io import BytesIO
import zipfile

import pytest
from PIL import Image

from app.evaluation.drive_import import ImportFailure, download, parse_embedded, parse_ivd, reconcile


def test_embedded_lists_all_entries_and_preserves_shortcut_ids():
    entries = ''.join(
        f'<div class="flip-entry" id="entry-id{i}"><a href="https://drive.google.com/file/d/id{i}/view"><img src="type/application/vnd.google-apps.shortcut"><div class="flip-entry-title">image{i}.jpg</div></a></div>'
        for i in range(1205)
    )
    result = parse_embedded('<html><div class="flip-entries">' + entries + '</div></html>')
    assert len(result) == 1205
    assert result[-1]['id'] == 'id1204'
    assert result[0]['shortcut'] is True


def test_initial_drive_data_resolves_target_and_is_not_complete_listing():
    row = ['shortcut', [], 'test.jpg', 'application/vnd.google-apps.shortcut'] + [None] * 128
    row[131] = ['target']
    payload = json.dumps([ [row], None ])
    html = "window['_DRIVE_ivd'] = '" + payload + "';"
    assert parse_ivd(html)[0]['canonical_id'] == 'target'


def test_embedded_rejects_incomplete_or_login_response():
    with pytest.raises(ImportFailure):
        parse_embedded('<html>Sign in</html>')


def test_embedded_real_structure_with_photo_and_shortcut_and_attribute_order():
    html = '''<!DOCTYPE html><html><body><div class="flip-entries">
    <div id="entry-shortcut" class="flip-entry" tabindex="0" role="link"><div class="flip-entry-info"><a href="https://drive.google.com/file/d/shortcut/view?usp=drive_web" target="_blank"><div class="flip-entry-list-icon"><img src="https://drive-thirdparty.googleusercontent.com/16/type/application/vnd.google-apps.shortcut" alt=""/></div><div class="flip-entry-title">273A3416.jpg</div></a></div></div>
    <div class="flip-entry" id="entry-photo" tabindex="0" role="link"><div class="flip-entry-info"><a href="https://drive.google.com/file/d/photo/view?usp=drive_web"><div class="flip-entry-list-icon"><img src="https://drive-thirdparty.googleusercontent.com/16/type/image/jpeg"/></div><div class="flip-entry-title">person &amp; group.jpg</div></a></div></div>
    </div></body></html>'''
    entries = parse_embedded(html)
    assert [(x['id'], x['shortcut'], x['name']) for x in entries] == [
        ('shortcut', True, '273A3416.jpg'), ('photo', False, 'person & group.jpg')]


def image_bytes():
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, format='PNG')
    return buffer.getvalue()


class Response:
    headers = {}

    def __init__(self, data, fail=False):
        self.data, self.fail = data, fail

    def iter_content(self, size):
        yield self.data[:10]
        if self.fail:
            raise RuntimeError('interrupted download')
        yield self.data[10:]

    def close(self):
        pass


def test_download_validates_original_bytes_and_resumes_only_verified_checksum(tmp_path):
    data = image_bytes()
    item = download('safe-ID', tmp_path, lambda *a, **k: Response(data))
    assert (tmp_path / item['path']).read_bytes() == data
    assert download('safe-ID', tmp_path, lambda *a, **k: pytest.fail('downloaded twice')) == item
    (tmp_path / item['path']).write_bytes(b'corrupted')
    repaired = download('safe-ID', tmp_path, lambda *a, **k: Response(data))
    assert repaired == item


def test_download_rejects_html_and_does_not_commit_partial_bytes(tmp_path):
    with pytest.raises(ImportFailure):
        download('safe-ID', tmp_path, lambda *a, **k: Response(b'<html>Sign in</html>'))
    assert not list(tmp_path.rglob('*.json'))
    with pytest.raises(RuntimeError):
        download('safe-ID', tmp_path, lambda *a, **k: Response(image_bytes(), fail=True))
    assert not list(tmp_path.rglob('*.json'))


def entry(identity, name='same.jpg'):
    return dict(id=identity, canonical_id=identity, name=name)


def test_labels_use_hashes_and_fail_closed_on_copy_mismatch_or_overlap():
    inventories = dict(complete=[entry('a'), entry('b')], positive=[entry('copy')],
                       false_negative=[], false_positive=[], reference=[entry('ref')])
    media = {identity: dict(sha256=digest) for identity, digest in
             [('a', 'hash-a'), ('b', 'hash-b'), ('copy', 'hash-a'), ('ref', 'hash-ref')]}
    labels, references, provenance, conflicts = reconcile(inventories, media)
    assert labels == {'hash-a': {'positive'}, 'hash-b': set()}
    assert not conflicts
    assert provenance[0]['complete_ids'] == ['a']
    inventories['false_positive'] = [entry('a')]
    assert reconcile(inventories, media)[3]
    inventories['false_positive'] = []
    media['copy']['sha256'] = 'different-bytes-same-name'
    assert reconcile(inventories, media)[3]


def test_false_negatives_must_be_subset_of_positives_and_reference_required():
    inventories = dict(complete=[entry('a')], positive=[], false_negative=[entry('a')],
                       false_positive=[], reference=[])
    assert len(reconcile(inventories, {'a': {'sha256': 'a'}})[3]) == 2


def test_duplicate_bytes_share_one_physical_image(tmp_path):
    first = download('a', tmp_path, lambda *a, **k: Response(image_bytes()))
    second = download('b', tmp_path, lambda *a, **k: Response(image_bytes()))
    assert first['path'] == second['path']
    assert len(list((tmp_path / 'media').iterdir())) == 1


def test_incomplete_inventory_withholds_manifest(tmp_path, monkeypatch):
    from app.evaluation import drive_import as module
    monkeypatch.setattr(module, 'request', lambda *a, **k: type('R', (), {'text': '<html><div class="flip-entries"></div></html>'})())
    result = module.run(tmp_path)
    assert result['status'] == 'incomplete'
    assert not (tmp_path / 'manifest.toml').exists()
    assert result['errors']


def test_partial_download_withholds_manifest_and_never_labels_negatives(tmp_path, monkeypatch):
    from app.evaluation import drive_import as module
    monkeypatch.setattr(module, 'EXPECTED_COUNTS', {k: 1 for k in module.FOLDERS})
    html = '<html><div class="flip-entries"><div class="flip-entry" id="entry-a"><div class="flip-entry-title">a.jpg</div></div></div></html>'
    monkeypatch.setattr(module, 'request', lambda *a, **k: type('R', (), {'text': html})())
    monkeypatch.setattr(module, 'download', lambda *a, **k: (_ for _ in ()).throw(ImportFailure('incomplete image')))
    result = module.run(tmp_path)
    assert result['inventory_complete'] is True
    assert result['status'] == 'incomplete'
    assert 'counts' not in result
    assert not (tmp_path / 'manifest.toml').exists()


def test_complete_import_deduplicates_reference_and_publishes_test_only(tmp_path, monkeypatch):
    from app.evaluation import drive_import as module
    from app.evaluation.manifest import load_manifest
    folder_entries = dict(complete=['positive', 'negative', 'reference', 'duplicate'],
                          positive=['positive'], false_negative=['positive'],
                          false_positive=['negative'], reference=['reference'])
    monkeypatch.setattr(module, 'EXPECTED_COUNTS', {k: len(v) for k, v in folder_entries.items()})
    def get(url):
        label = next(k for k, v in module.FOLDERS.items() if v in url)
        blocks = ''.join(f'<div class="flip-entry" id="entry-{i}"><div class="flip-entry-title">{i}.png</div></div>' for i in folder_entries[label])
        return type('R', (), {'text': f'<html><div class="flip-entries">{blocks}</div></html>'})()
    monkeypatch.setattr(module, 'request', get)
    actual_download = download
    def media(identity, root):
        buffer = BytesIO()
        color = {'positive': 'red', 'negative': 'blue', 'reference': 'green', 'duplicate': 'red'}[identity]
        Image.new('RGB', (4, 4), color).save(buffer, format='PNG')
        return actual_download(identity, root, lambda *a, **k: Response(buffer.getvalue()))
    monkeypatch.setattr(module, 'download', media)
    result = module.run(tmp_path)
    assert result['status'] == 'complete'
    assert result['counts'] == dict(positive=1, negative=1, duplicates=1, reference_excluded=1, false_negative=1, false_positive=1)
    manifest = load_manifest(tmp_path / 'manifest.toml', mode='test_only')
    assert len(manifest.scans) == 2
    assert len(list((tmp_path / 'media').iterdir())) == 3


def test_fifty_bootstrap_sized_entries_cannot_establish_snapshot_completeness(tmp_path, monkeypatch):
    from app.evaluation import drive_import as module
    blocks = ''.join(f'<div class="flip-entry" id="entry-id{i}"><div class="flip-entry-title">img.jpg</div></div>' for i in range(50))
    monkeypatch.setattr(module, 'request', lambda *a, **k: type('R', (), {'text': f'<html><div class="flip-entries">{blocks}</div></html>'})())
    result = module.run(tmp_path)
    assert result['status'] == 'incomplete'
    assert 'snapshot count mismatch' in result['errors'][0]['message']
    assert not (tmp_path / 'manifest.toml').exists()


def test_http_rate_limit_retries_are_bounded_and_respect_retry_after(monkeypatch):
    import requests
    from app.evaluation import drive_import as module
    delays, calls = [], []
    def get(*args, **kwargs):
        response = requests.Response()
        response.status_code = 429
        response.headers['Retry-After'] = '90'
        calls.append(1)
        return response
    monkeypatch.setattr(module.requests, 'get', get)
    monkeypatch.setattr(module.time, 'sleep', delays.append)
    with pytest.raises(ImportFailure, match='HTTP 429'):
        module.request('https://drive.google.com/example')
    assert len(calls) == 3
    assert delays == [90, 90]


def test_download_rejects_path_traversal_before_request(tmp_path):
    with pytest.raises(ImportFailure, match='unsafe'):
        download('../bad', tmp_path, lambda *a, **k: pytest.fail('network requested'))


def zip_dataset(path, *, conflict=False, unsafe=False, partial=False):
    with zipfile.ZipFile(path, 'w') as archive:
        for folder, color in [('data-set-completo', 'red'), ('data-set-completo', 'blue'),
                              ('positivos', 'red'), ('falso-positivos', 'red' if conflict else 'blue'),
                              ('falso-negativo', 'red'), ('referencia', 'green')]:
            if partial and folder == 'referencia':
                continue
            buffer = BytesIO()
            Image.new('RGB', (4, 4), color).save(buffer, format='PNG')
            archive.writestr(f'avaliacao/{folder}/{color}.png', buffer.getvalue())
        if unsafe:
            archive.writestr('../escape.png', image_bytes())


def test_zip_import_reuses_hash_labels_without_inventing_drive_ids(tmp_path, monkeypatch):
    from app.evaluation import drive_import as module
    archive = tmp_path / 'download.zip'
    zip_dataset(archive)
    monkeypatch.setattr(module, 'EXPECTED_COUNTS', dict(complete=2, positive=1, false_positive=1, false_negative=1, reference=1))
    result = module.import_zip([archive], tmp_path / 'output')
    assert result['status'] == 'complete'
    assert result['counts']['positive'] == result['counts']['negative'] == 1
    assert len(result['archives']) == 1
    assert all('archive_sha256' in s and 'canonical_id' not in s for s in result['scans'])


@pytest.mark.parametrize('options', [dict(conflict=True), dict(unsafe=True), dict(partial=True)])
def test_zip_import_withholds_manifest_on_conflict_zip_slip_or_missing_volume(tmp_path, monkeypatch, options):
    from app.evaluation import drive_import as module
    archive = tmp_path / 'download.zip'
    zip_dataset(archive, **options)
    monkeypatch.setattr(module, 'EXPECTED_COUNTS', dict(complete=2, positive=1, false_positive=1, false_negative=1, reference=1))
    output = tmp_path / 'output'
    result = module.import_zip([archive], output)
    assert result['status'] == 'incomplete'
    assert not (output / 'manifest.toml').exists()
    assert not (tmp_path / 'escape.png').exists()
