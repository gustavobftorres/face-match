import json
import math
import sys
import types

import pytest

from app.evaluation import dlib_lfw_calibration as calibration
from app.evaluation.face_search import DlibProductionAdapter
from app.evaluation.models import ReferenceImage, Scan


def rows(pos, neg):
    return ([{"mated": True, "score": value} for value in pos]
            + [{"mated": False, "score": value} for value in neg])


def test_negative_distance_strict_boundary_and_stricter_tie():
    result = calibration.select_threshold(rows([-.2] * 500, [-1.4] * 1000))
    assert result["score_threshold"] == -1.4
    assert result["distance_threshold"] == 1.4
    assert result["comparator"] == ">"
    assert result["tp"] == 500
    assert result["fp"] == 0
    assert not -1.4 > result["score_threshold"]


def test_exact_fpr_boundary_and_999_denominator():
    allowed = calibration.select_threshold(rows([-.2] * 500, [-1.4] * 999 + [-.1]))
    forbidden = calibration.select_threshold(rows([-.2] * 500, [-1.4] * 998 + [-.1]))
    assert allowed["empirical_fpr"] == .001
    assert allowed["tp"] == 500
    assert forbidden["fp"] == 0
    assert forbidden["tp"] == 0
    assert forbidden["score_threshold"] == -.1


def test_minimum_coverage_and_failures_excluded():
    data = rows([-.2] * 500, [-1.4] * 500)
    data += [{"mated": True, "score": None, "status": "no_face"}]
    assert calibration.select_threshold(data)["completed_mated"] == 500
    with pytest.raises(ValueError, match="500"):
        calibration.select_threshold(rows([-.2] * 499, [-1.4] * 500))


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, .01, True, "-.2"])
def test_reject_invalid_distance_scores(invalid):
    with pytest.raises(ValueError, match="finite nonpositive"):
        calibration.select_threshold(rows([invalid] * 500, [-1.4] * 500))


def test_zero_and_reject_all_are_finite():
    result = calibration.select_threshold(rows([-1.4] * 500, [0.] * 500))
    assert result["score_threshold"] == 0
    assert result["tp"] == result["fp"] == 0


def test_nextafter_accept_all_candidate_is_considered(monkeypatch):
    # Relax only this synthetic objective so the additional candidate is needed.
    monkeypatch.setattr(calibration, "TARGET_FPR", 1)
    result = calibration.select_threshold(rows([-1.4] * 500, [-1.4] * 500))
    assert result["score_threshold"] == math.nextafter(-1.4, -math.inf)
    assert result["tp"] == result["fp"] == 500


def test_production_first_reference_any_scan_and_content_cache(tmp_path):
    reference = tmp_path / "reference.jpg"
    scan = tmp_path / "scan.jpg"
    reference.write_bytes(b"reference")
    scan.write_bytes(b"scan")
    calls = []
    def encoder(content):
        calls.append(content)
        return [10., 1.] if content == b"reference" else [1., 9.]
    memo = calibration.MemoEncoder(encoder)
    adapter = DlibProductionAdapter(encoder=memo, distance=lambda a, b: abs(a - b))
    gallery = [ReferenceImage("r", "person", reference, "calibration")]
    query = Scan("s", scan, "calibration", ())
    assert adapter.search(gallery, query).scores[0].score == -1.
    assert adapter.search(gallery, query).scores[0].score == -1.
    assert calls == [b"scan", b"reference"]
    assert memo.hits == 1
    # A second path containing the same bytes also reuses the content cache.
    assert memo(b"reference") == (10., 1.)
    assert memo.hits == 2


def test_scan_failure_does_not_encode_or_swap_reference(tmp_path):
    reference, scan = tmp_path / "r", tmp_path / "s"
    reference.write_bytes(b"r")
    scan.write_bytes(b"s")
    calls = []
    def encoder(content):
        calls.append(content)
        return [] if content == b"s" else [1.]
    adapter = DlibProductionAdapter(encoder=calibration.MemoEncoder(encoder))
    result = adapter.search([ReferenceImage("r", "p", reference, "calibration")], Scan("s", scan, "calibration", ()))
    assert not result.has_face and result.error is None
    assert calls == [b"s"]


def test_memo_preserves_exceptions_and_empty_results():
    calls = []
    def encoder(content):
        calls.append(content)
        if content == b"bad":
            raise ValueError("bad input")
        return []
    memo = calibration.MemoEncoder(encoder)
    for _ in range(2):
        with pytest.raises(ValueError, match="bad input"):
            memo(b"bad")
        assert memo(b"empty") == ()
    assert calls == [b"bad", b"empty"]


def local_data(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    text = '\n'.join(['1100'] + ['Person_A 1 2'] * 1100 + ['Person_A 1 Person_B 1'] * 1100)
    (source / "pairsDevTrain.txt").write_text(text)
    (source / "lfw.tgz").write_bytes(b"fake pinned archive")
    images = {}
    for pair in calibration.parse_pairs(text):
        for key in ("reference", "scan"):
            path = source / pair[key]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pair[key].encode())
            images[pair[key]] = calibration.digest(path)
    calibration.write_json(source / "image-sha256.json", images)
    monkeypatch.setattr(calibration, "SOURCES", {
        name: {"algorithm": "sha256", "digest": calibration.digest(source / name), "max_bytes": 300000}
        for name in ("pairsDevTrain.txt", "lfw.tgz")})
    monkeypatch.setattr(calibration, "IMAGE_MANIFEST_SHA256", calibration.digest(source / "image-sha256.json"))
    return source


def test_verification_checks_pins_and_each_image(tmp_path, monkeypatch):
    source = local_data(tmp_path, monkeypatch)
    _, pairs, images = calibration.verify_local_data(source)
    assert len(pairs) == 2200 and len(images) == 3
    (source / pairs[0]["scan"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="image checksum"):
        calibration.verify_local_data(source)


def test_verification_rejects_archive_and_path_symlinks(tmp_path, monkeypatch):
    source = local_data(tmp_path, monkeypatch)
    image = source / "lfw/Person_A/Person_A_0001.jpg"
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(image.read_bytes())
    image.unlink()
    image.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        calibration.verify_local_data(source)
    (source / "lfw.tgz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="pinned checksum"):
        calibration.verify_local_data(source)


def test_protocol_frozen_before_encoder_and_reuse_refused(tmp_path, monkeypatch):
    source = local_data(tmp_path, monkeypatch)
    output = tmp_path / "output"
    calls = []
    def encode(content):
        protocol = json.loads((output / "protocol.json").read_text())
        assert protocol["comparator"] == ">"
        assert protocol["pairs"] == 2200
        calls.append(content)
        return [0.] if b"Person_B" not in content else [2.]
    monkeypatch.setattr(calibration, "runtime_provenance", lambda: {"fake": True})
    monkeypatch.setitem(sys.modules, "app.services.ai_service", types.SimpleNamespace(get_face_encodings=encode))
    # Supply an injected distance, so this orchestration test never imports Dlib.
    monkeypatch.setattr(calibration, "DlibProductionAdapter", lambda **kw: DlibProductionAdapter(distance=lambda a, b: abs(a-b), **kw))
    result = calibration.run(source, output)
    assert len(calls) == 3
    assert result["selection"]["tp"] == 1100
    assert result["selection"]["fp"] == 0
    assert result["protocol_sha256"] == calibration.digest(output / "protocol.json")
    assert len((output / "scores.jsonl").read_text().splitlines()) == 2200
    with pytest.raises(FileExistsError):
        calibration.run(source, output)
    assert len(calls) == 3
