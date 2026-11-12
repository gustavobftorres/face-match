from dataclasses import asdict
import json
from pathlib import Path

import pytest

from app.evaluation import dlib_threshold_replay as replay
from app.evaluation.runner import _metrics


def put(path, value):
    path.write_text(json.dumps(value, allow_nan=False))


@pytest.fixture
def bundle(tmp_path):
    public = tmp_path / 'public'
    public.mkdir()
    runtime = {'python': 'synthetic', 'platform': 'synthetic', 'packages': dict.fromkeys(replay.PACKAGES, '1'),
               'implementation_sha256': {}, 'preprocessing': {
                   'exif_transpose': True, 'mode': 'RGB', 'max_dimension': 1000,
                   'resize': 'Pillow thumbnail LANCZOS when dimension exceeds maximum',
                   'face_encodings_defaults': {'num_jitters': 1, 'model': 'small'},
                   'face_locations_defaults': {'model': 'hog', 'number_of_times_to_upsample': 1}}}
    root = Path(replay.__file__).resolve().parents[4]
    hashes = {}
    for name in ('runner.py', 'face_search.py', 'ai_service.py'):
        relative = 'apps/backend/app/' + ('services/' if name == 'ai_service.py' else 'evaluation/') + name
        hashes[relative] = replay.digest(root / relative)
        runtime['implementation_sha256'][name] = hashes[relative]
    for name in ('dlib_lfw_calibration.py', 'lfw_calibration.py'):
        runtime['implementation_sha256'][name] = replay.digest(Path(replay.__file__).with_name(name))
    runtime_file = public / 'synthetic-runtime.bin'
    runtime_file.write_bytes(b'synthetic runtime bytes')
    runtime['runtime_files'] = {name: {'path': str(runtime_file), 'sha256': replay.digest(runtime_file)} for name in
        ('face_recognition_api', 'dlib_python', 'dlib_binary', 'landmarks_small_5', 'face_descriptor_resnet', 'model_locator')}
    rows = [dict(index=i, mated=i < 500, score=-.2 if i < 500 else -.5,
                 has_face=True, error=None, status='completed') for i in range(1000)]
    (public / 'scores.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    selection = dict(score_threshold=-.5, distance_threshold=.5, comparator='>', distance_comparator='<',
                     score_semantics='negative_distance', target_fpr=.001, tp=500, fp=0,
                     completed_mated=500, completed_nonmated=500, empirical_tpr=1., empirical_fpr=0.)
    put(public / 'decisions.json', [dict(r, accepted=r['score'] > -.5) for r in rows])
    protocol = dict(dataset='LFW View 1 pairsDevTrain', minimum_completed_per_class=500, adapter=replay.IDENTITY, runtime=runtime, pairs=1000, target_fpr=.001,
                    score_semantics='negative_distance', comparator='>', distance_comparator='<')
    put(public / 'protocol.json', protocol)
    receipt = dict(protocol_path=str(public / 'protocol.json'), protocol_sha256=replay.digest(public / 'protocol.json'),
                   scores_sha256=replay.digest(public / 'scores.jsonl'), decisions_sha256=replay.digest(public / 'decisions.json'),
                   adapter=dict(identity=replay.IDENTITY, score_semantics='negative_distance', runtime=runtime), selection=selection)
    put(public / 'receipt.json', receipt)
    source = tmp_path / 'source'
    artifacts = source / 'artifacts'
    artifacts.mkdir(parents=True)
    config = {'baseline': dict(factory=replay.IDENTITY, name='dlib-production-baseline',
                              production_module='app.services.ai_service', max_image_dimension=1000, distance_threshold=.6)}
    policy = dict(policy='production_distance', threshold=.6, comparator='>', score_semantics='negative_distance')
    source_rows = []
    for i, (score, positive, status) in enumerate([(-.2, True, 'match'), (-.5, False, 'match'), (-.6, False, 'no_match'),
                                                 (None, True, 'no_face'), (None, True, 'error')]):
        source_rows.append(dict(scan_id=str(i), split='test', expected_identity_ids=['person'] if positive else [],
                                predicted_identity_ids=['person'] if status == 'match' else [],
                                scores=[dict(identity_id='person', score=score)] if score is not None else [],
                                status=status, error='failed' if status == 'error' else None, latency_ms=float(i + 1), system='baseline'))
    (artifacts / 'decisions.ndjson').write_text(''.join(json.dumps(r) + '\n' for r in source_rows))
    plan = dict(mode='test_only', policies={'baseline': policy}, adapter_config=config, baseline_description=dict(reference_policy='first-encoding-one-reference-per-identity',
                scan_policy='any-face', score_semantics='negative_distance', comparator='distance < 0.6'), runtime=runtime,
                source_sha256=hashes, dataset=dict(scans=5, positive=3, negative=2, references=1))
    put(source / 'compare-plan.json', plan)
    run = dict(systems={'baseline': {'name': 'dlib-production-baseline'}}, evaluation_mode='test_only', manifest={'test_scans': 5}, provenance=dict(adapter_config=config,
               decisions={'baseline': policy}, python=runtime['python'], platform=runtime['platform'], packages=runtime['packages'],
               dataset=dict(references=[dict(identity_id='person', path='/never/open/ref.jpg')], scans=[
                   dict(id=r['scan_id'], split='test', expected_identity_ids=r['expected_identity_ids'], path='/never/open/' + r['scan_id'] + '.jpg') for r in source_rows])))
    put(artifacts / 'run.json', run)
    put(artifacts / 'threshold.json', {'baseline': dict(policy, threshold=-.6, distance_threshold=.6, name='dlib-production-baseline')})
    metrics = dict(name='dlib-production-baseline', **asdict(_metrics([replay.decision(r, -.6) for r in source_rows])))
    put(artifacts / 'metrics.json', dict(evaluation_mode='test_only', systems={'baseline': metrics}))
    return dict(calibration_receipt=public / 'receipt.json', approved_receipt_sha256=replay.digest(public / 'receipt.json'),
                source_run=source, output=tmp_path / 'replay', approved_source_plan_sha256=replay.digest(source / 'compare-plan.json'))


def test_replay_strict_boundary_failures_coverage_and_no_media_reads(bundle, monkeypatch):
    original_read = Path.open
    def guarded(path, *args, **kwargs):
        assert path.suffix not in ('.jpg', '.png'), 'replay must never open media'
        if path.name == 'decisions.ndjson' and path.parent == bundle['output']:
            assert (bundle['output'] / 'replay-plan.json').exists()
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    result = replay.replay(**bundle)
    assert result['original']['fp'] == 1
    assert result['calibrated']['fp'] == 0
    assert result['calibrated']['tp'] == 1
    assert result['calibrated']['no_face'] == result['calibrated']['errors'] == 1
    assert result['calibrated']['end_to_end_misses'] == 2
    assert result['calibrated']['end_to_end_recall'] == 1 / 3
    assert result['original']['latency_ms'] == result['calibrated']['latency_ms']
    decisions = [json.loads(line) for line in (bundle['output'] / 'decisions.ndjson').read_text().splitlines()]
    assert decisions[1]['status'] == 'no_match'  # score exactly equals new threshold
    assert decisions[2]['status'] == 'no_match'  # original boundary score -0.6
    assert decisions[3]['scores'] == decisions[4]['scores'] == []
    assert decisions[4]['status'] == 'error'
    assert 'Historical weights cannot be cryptographically verified' in result['limitation']


@pytest.mark.parametrize('argument', ['approved_receipt_sha256', 'approved_source_plan_sha256'])
def test_approved_hash_mismatch_has_no_output(bundle, argument):
    bundle[argument] = '0' * 64
    with pytest.raises(ValueError, match='checksum'):
        replay.replay(**bundle)
    assert not bundle['output'].exists()


@pytest.mark.parametrize('filename', ['protocol.json', 'scores.jsonl', 'decisions.json'])
def test_public_linked_hash_mismatch(bundle, filename):
    (bundle['calibration_receipt'].parent / filename).write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        replay.replay(**bundle)


def test_refuse_existing_output(bundle):
    bundle['output'].mkdir()
    (bundle['output'] / 'keep').write_text('unchanged')
    with pytest.raises(FileExistsError):
        replay.replay(**bundle)
    assert (bundle['output'] / 'keep').read_text() == 'unchanged'


@pytest.mark.parametrize('mutation', ['semantics', 'boundary', 'positive_score', 'failure_score', 'duplicate', 'count', 'metrics', 'runtime', 'code'])
def test_reject_invalid_source(bundle, mutation):
    source = bundle['source_run']
    decisions = source / 'artifacts/decisions.ndjson'
    rows = [json.loads(line) for line in decisions.read_text().splitlines()]
    if mutation == 'semantics':
        path = source / 'artifacts/threshold.json'
        data = json.loads(path.read_text()); data['baseline']['score_semantics'] = 'cosine'; put(path, data)
    elif mutation == 'boundary':
        rows[2]['predicted_identity_ids'] = ['person']; rows[2]['status'] = 'match'
    elif mutation == 'positive_score':
        rows[0]['scores'][0]['score'] = .1
    elif mutation == 'failure_score':
        rows[3]['scores'] = [dict(identity_id='person', score=-.1)]
    elif mutation == 'duplicate':
        rows[1]['scan_id'] = rows[0]['scan_id']
    elif mutation == 'metrics':
        path = source / 'artifacts/metrics.json'; data = json.loads(path.read_text()); data['systems']['baseline']['fp'] = 99; put(path, data)
    else:
        path = source / 'compare-plan.json'; data = json.loads(path.read_text())
        if mutation == 'count': data['dataset']['positive'] = 4
        if mutation == 'runtime': data['runtime']['python'] = 'different'
        if mutation == 'code': data['source_sha256']['apps/backend/app/evaluation/face_search.py'] = '0' * 64
        put(path, data); bundle['approved_source_plan_sha256'] = replay.digest(path)
    decisions.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    with pytest.raises(ValueError):
        replay.replay(**bundle)
    assert not bundle['output'].exists()


def test_public_runtime_file_changed(bundle):
    (bundle['calibration_receipt'].parent / 'synthetic-runtime.bin').write_bytes(b'changed')
    with pytest.raises(ValueError, match='public runtime file mismatch'):
        replay.replay(**bundle)
    assert not bundle['output'].exists()
