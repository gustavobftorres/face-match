import io
import math
import tarfile

import pytest

from app.evaluation.lfw_calibration import extract_images, parse_pairs, select_threshold


def pair_text():
    return '\n'.join(['1100'] + ['Person_A 1 2'] * 1100 + ['Person_A 1 Person_B 1'] * 1100)


def test_parser_preserves_order_raw_and_labels():
    rows = parse_pairs(pair_text())
    assert len(rows) == 2200
    assert rows[0] == {'index': 1, 'raw': 'Person_A 1 2', 'mated': True,
                       'reference': 'lfw/Person_A/Person_A_0001.jpg', 'scan': 'lfw/Person_A/Person_A_0002.jpg'}
    assert not rows[-1]['mated']


@pytest.mark.parametrize('text', ['10\n', pair_text().replace('Person_B', '../escape'),
                                    pair_text().replace('Person_B', 'Person_A')])
def test_parser_rejects_wrong_count_paths_and_contradictory_labels(text):
    with pytest.raises(ValueError):
        parse_pairs(text)


def rows(pos, neg):
    return [{'mated': True, 'score': value} for value in pos] + [{'mated': False, 'score': value} for value in neg]


def test_threshold_boundary_constraint_and_stricter_tie():
    result = select_threshold(rows([.8] * 500, [.2] * 999 + [.7]))
    assert result['threshold'] == .8
    assert result['empirical_tpr'] == 1
    assert result['empirical_fpr'] == 0


def test_threshold_allows_exact_fpr_boundary():
    result = select_threshold(rows([.7] * 500, [.2] * 999 + [.7]))
    assert result['threshold'] == .7
    assert result['empirical_fpr'] == .001


def test_threshold_reject_all_is_finite_and_coverage_guard():
    result = select_threshold(rows([.1] * 500, [.9] * 500))
    assert result['threshold'] == math.nextafter(.9, math.inf)
    with pytest.raises(ValueError, match='insufficient'):
        select_threshold(rows([.8] * 499, [.2] * 500))
    with pytest.raises(ValueError, match='no finite threshold'):
        select_threshold(rows([.5] * 500, [1.] * 500))


@pytest.mark.parametrize('name,kind', [('../escape.jpg', tarfile.REGTYPE),
                                     ('lfw/A/A_0001.jpg', tarfile.SYMTYPE),
                                     ('lfw/A/not.txt', tarfile.REGTYPE)])
def test_archive_rejects_traversal_links_and_non_jpeg(tmp_path, name, kind):
    archive = tmp_path / 'bad.tgz'
    with tarfile.open(archive, 'w:gz') as output:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.size = 1
        output.addfile(info, io.BytesIO(b'x'))
    with pytest.raises(ValueError):
        extract_images(archive, tmp_path / 'images', {'lfw/A/A_0001.jpg'})


def test_extract_only_listed_images_and_hashes(tmp_path):
    archive = tmp_path / 'good.tgz'
    with tarfile.open(archive, 'w:gz') as output:
        for name in ['lfw/A/A_0001.jpg', 'lfw/A/A_0002.jpg']:
            info = tarfile.TarInfo(name)
            info.size = 1
            output.addfile(info, io.BytesIO(b'x'))
    result = extract_images(archive, tmp_path / 'images', {'lfw/A/A_0001.jpg'})
    assert len(result['lfw/A/A_0001.jpg']) == 64
    assert not (tmp_path / 'images/lfw/A/A_0002.jpg').exists()


def test_extract_rejects_existing_directory_symlinks(tmp_path):
    archive = tmp_path / 'good.tgz'
    with tarfile.open(archive, 'w:gz') as output:
        info = tarfile.TarInfo('lfw/A/A_0001.jpg')
        info.size = 1
        output.addfile(info, io.BytesIO(b'x'))
    root = tmp_path / 'images'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'lfw').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        extract_images(archive, root, {'lfw/A/A_0001.jpg'})
    assert not list(outside.iterdir())


def test_pinned_checksum_rejects_existing_wrong_file(tmp_path, monkeypatch):
    from app.evaluation.lfw_calibration import SOURCES, digest
    path = tmp_path / 'pairsDevTrain.txt'
    path.write_text('not the pinned pairs')
    assert digest(path) != SOURCES[path.name]['digest']
    assert all(len(source['digest']) == 64 for source in SOURCES.values())


def test_download_rejects_response_checksum_before_publishing(tmp_path, monkeypatch):
    import requests
    from app.evaluation.lfw_calibration import download
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def raise_for_status(self):
            pass
        def iter_content(self, size):
            yield b'untrusted wrong content'
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match='checksum mismatch'):
        download(tmp_path, 'pairsDevTrain.txt')
    assert not (tmp_path / 'pairsDevTrain.txt').exists()
