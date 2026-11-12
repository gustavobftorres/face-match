"""Replay recorded Dlib scores with an independently approved public LFW threshold.

This module never imports an inference adapter or opens dataset media.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .models import MatchDecision, FaceScore
from .runner import _metrics

IDENTITY = 'app.evaluation.face_search:DlibProductionAdapter'
PACKAGES = ('face-recognition', 'face-recognition-models', 'dlib', 'numpy', 'Pillow')
TIMING_NOTE = 'original inference timings; not remeasured by replay'
LIMITATION = ('The historical baseline did not record Dlib weight/binary hashes. '
              'Historical weights cannot be cryptographically verified; recorded scores '
              'are authoritative for this replay. Public calibration is in-sample and '
              'does not establish private-domain generalization. No new inference or latency benchmark.')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def checked(path, expected):
    require(isinstance(expected, str) and len(expected) == 64 and digest(path) == expected,
            f'checksum mismatch: {path}')
    return load(path)


def public_receipt(path, approved):
    path = Path(path).resolve()
    receipt = checked(path, approved)
    protocol_path = Path(receipt['protocol_path'])
    protocol = checked(protocol_path, receipt['protocol_sha256'])
    require(digest(protocol_path.parent / 'scores.jsonl') == receipt['scores_sha256'], 'public scores checksum mismatch')
    rows = [json.loads(line) for line in (protocol_path.parent / 'scores.jsonl').read_text().splitlines()]
    decisions = checked(protocol_path.parent / 'decisions.json', receipt['decisions_sha256'])
    require(protocol['dataset'] == 'LFW View 1 pairsDevTrain'
            and protocol['minimum_completed_per_class'] == 500, 'not the approved LFW protocol')
    selection = receipt['selection']
    threshold = selection['score_threshold']
    require(finite(threshold) and threshold <= 0 and selection['distance_threshold'] == -threshold,
            'invalid negative distance threshold')
    for obj in (selection, protocol):
        require(obj['score_semantics'] == 'negative_distance' and obj['comparator'] == '>'
                and obj['distance_comparator'] == '<' and obj['target_fpr'] == .001,
                'invalid score semantics or public objective')
    require(receipt['adapter']['identity'] == protocol['adapter'] == IDENTITY
            and receipt['adapter']['score_semantics'] == 'negative_distance'
            and receipt['adapter']['runtime'] == protocol['runtime'], 'public adapter mismatch')
    runtime = protocol['runtime']
    for name in ('dlib_lfw_calibration.py', 'lfw_calibration.py', 'face_search.py', 'ai_service.py'):
        current = (Path(__file__).parents[1] / 'services' / name if name == 'ai_service.py'
                   else Path(__file__).with_name(name))
        require(digest(current) == runtime['implementation_sha256'][name], f'public implementation mismatch: {name}')
    for name in ('face_recognition_api', 'dlib_python', 'dlib_binary', 'landmarks_small_5',
                 'face_descriptor_resnet', 'model_locator'):
        record = runtime['runtime_files'][name]
        require(digest(record['path']) == record['sha256'], f'public runtime file mismatch: {name}')
    require(len(rows) == protocol['pairs'] and len(decisions) == len(rows), 'public pair count mismatch')
    require(len({row['index'] for row in rows}) == len(rows), 'duplicate public pair id')
    for row, decision in zip(rows, decisions):
        score = row['score']
        require(type(row['mated']) is bool, 'invalid public label')
        require((score is None and row['status'] in ('error', 'no_face') and not row['has_face'])
                or (finite(score) and score <= 0 and row['status'] == 'completed' and row['has_face'] is True and not row['error']),
                'invalid public score/status')
        require((row['status'] == 'error' and isinstance(row['error'], str) and bool(row['error'].strip()))
                or (row['status'] != 'error' and row['error'] is None), 'public failure semantics mismatch')
        require(decision == dict(row, accepted=score is not None and score > threshold), 'public decision mismatch')
    positive = [r['score'] for r in rows if r['mated'] and r['score'] is not None]
    negative = [r['score'] for r in rows if not r['mated'] and r['score'] is not None]
    require(min(len(positive), len(negative)) >= 500, 'insufficient public completion')
    candidates = set(positive + negative)
    lower = math.nextafter(min(candidates), -math.inf)
    if math.isfinite(lower):
        candidates.add(lower)
    tp, selected, fp = max((sum(s > t for s in positive), t, sum(s > t for s in negative))
                           for t in candidates if sum(s > t for s in negative) / len(negative) <= .001)
    expected = dict(score_threshold=selected, distance_threshold=-selected, comparator='>', distance_comparator='<',
                    score_semantics='negative_distance', target_fpr=.001, tp=tp, fp=fp,
                    completed_mated=len(positive), completed_nonmated=len(negative),
                    empirical_tpr=tp / len(positive), empirical_fpr=fp / len(negative))
    require(selection == expected, 'public selection does not reproduce approved objective')
    return receipt, protocol


def decision(row, threshold):
    scores = tuple(FaceScore(s['identity_id'], s['score']) for s in row['scores'])
    predicted = tuple(s.identity_id for s in scores if s.score > threshold)
    status = row['status'] if row['status'] in ('error', 'no_face') else ('match' if predicted else 'no_match')
    return MatchDecision(row['scan_id'], row['split'], status, tuple(row['expected_identity_ids']),
                         predicted, scores, row['error'], row['latency_ms'])


def summary(decisions):
    result = asdict(_metrics(decisions))
    positives = sum(bool(d.expected_identity_ids) for d in decisions)
    negatives = len(decisions) - positives
    errors_positive = sum(d.status == 'error' and bool(d.expected_identity_ids) for d in decisions)
    result.update(total_images=len(decisions), positive_images=positives, negative_images=negatives,
                  face_score_coverage=(len(decisions) - result['errors'] - result['no_face']) / len(decisions),
                  end_to_end_misses=result['fn'] + errors_positive,
                  end_to_end_recall=result['tp'] / positives if positives else 0,
                  end_to_end_fpr=result['fp'] / negatives if negatives else 0,
                  timing_note=TIMING_NOTE)
    return result


def validate_source(source, approved, receipt):
    source = Path(source).resolve()
    plan = checked(source / 'compare-plan.json', approved)
    artifacts = source / 'artifacts'
    paths = {name: artifacts / name for name in ('run.json', 'threshold.json', 'metrics.json', 'decisions.ndjson')}
    hashes = {name: digest(path) for name, path in paths.items()}
    run, thresholds, stored = (load(paths[name]) for name in ('run.json', 'threshold.json', 'metrics.json'))
    provenance = run['provenance']
    require(plan['mode'] == run['evaluation_mode'] == stored['evaluation_mode'] == 'test_only', 'source must be test_only')
    require(provenance['adapter_config'] == plan['adapter_config'], 'source adapter config mismatch')
    require(plan['policies']['baseline']['policy'] == 'production_distance'
            and plan['policies']['baseline']['threshold'] == .6, 'source plan policy mismatch')
    require(run['systems']['baseline']['name'] == thresholds['baseline']['name']
            == stored['systems']['baseline']['name'] == 'dlib-production-baseline', 'source baseline name mismatch')
    baseline = plan['adapter_config']['baseline']
    require(baseline == {'factory': IDENTITY, 'name': 'dlib-production-baseline', 'production_module': 'app.services.ai_service',
                         'max_image_dimension': 1000, 'distance_threshold': .6}, 'unsupported baseline config')
    require(plan['baseline_description'] == {'reference_policy': 'first-encoding-one-reference-per-identity',
                'scan_policy': 'any-face', 'score_semantics': 'negative_distance', 'comparator': 'distance < 0.6'}, 'source semantics mismatch')
    policy = provenance['decisions']['baseline']
    require(policy['policy'] == 'production_distance' and policy['threshold'] == .6 and policy['comparator'] == '>'
            and policy['score_semantics'] == 'negative_distance', 'source policy mismatch')
    t = thresholds['baseline']
    require(t['threshold'] == -.6 and t['distance_threshold'] == .6 and t['comparator'] == '>'
            and t['score_semantics'] == 'negative_distance' and t['policy'] == 'production_distance', 'source threshold mismatch')
    runtime = receipt['adapter']['runtime']
    require(runtime['preprocessing'] == {
        'exif_transpose': True, 'mode': 'RGB', 'max_dimension': 1000,
        'resize': 'Pillow thumbnail LANCZOS when dimension exceeds maximum',
        'face_encodings_defaults': {'num_jitters': 1, 'model': 'small'},
        'face_locations_defaults': {'model': 'hog', 'number_of_times_to_upsample': 1}},
        'calibration preprocessing differs from historical production defaults')
    for key in ('python', 'platform'):
        require(runtime[key] == provenance[key] == plan['runtime'][key], f'runtime mismatch: {key}')
    for package in PACKAGES:
        require(runtime['packages'][package] == provenance['packages'][package] == plan['runtime']['packages'][package], f'package mismatch: {package}')
    root = Path(__file__).resolve().parents[4]
    for name in ('runner.py', 'face_search.py', 'ai_service.py'):
        relative = 'apps/backend/app/' + ('services/' if name == 'ai_service.py' else 'evaluation/') + name
        require(digest(root / relative) == plan['source_sha256'][relative], f'historical code mismatch: {name}')
        if name != 'runner.py':
            require(runtime['implementation_sha256'][name] == plan['source_sha256'][relative], f'calibration code mismatch: {name}')
    rows = [json.loads(line) for line in paths['decisions.ndjson'].read_text().splitlines()]
    rows = [row for row in rows if row['system'] == 'baseline']
    counts = plan['dataset']
    require(len(rows) == counts['scans'] and len({r['scan_id'] for r in rows}) == len(rows), 'source count or duplicate id mismatch')
    scans = {s['id']: s for s in provenance['dataset']['scans']}
    require(set(scans) == {r['scan_id'] for r in rows} and run['manifest']['test_scans'] == len(rows), 'source manifest mismatch')
    identities = {r['identity_id'] for r in provenance['dataset']['references']}
    require(len(identities) == counts['references'] == 1, 'unsupported source gallery')
    for row in rows:
        require(row['split'] == scans[row['scan_id']]['split'] == 'test'
                and row['expected_identity_ids'] == scans[row['scan_id']]['expected_identity_ids'], 'source labels mismatch')
        require(set(row['expected_identity_ids']) <= identities, 'unknown expected identity')
        require(row['status'] in ('error', 'no_face', 'match', 'no_match') and finite(row['latency_ms']) and row['latency_ms'] >= 0, 'invalid source status/timing')
        scores = row['scores']
        if row['status'] in ('error', 'no_face'):
            require(not scores and not row['predicted_identity_ids'] and (
                (row['status'] == 'error' and isinstance(row['error'], str) and bool(row['error'].strip()))
                or (row['status'] == 'no_face' and row['error'] is None)), 'failure cannot contain invented scores')
        else:
            require(not row['error'] and len(scores) == len(identities) and {s['identity_id'] for s in scores} == identities
                    and all(finite(s['score']) and s['score'] <= 0 for s in scores), 'invalid source negative distance scores')
        reproduced = decision(row, -.6)
        require(row['status'] == reproduced.status and row['predicted_identity_ids'] == list(reproduced.predicted_identity_ids), 'original strict decisions mismatch')
    require(sum(bool(r['expected_identity_ids']) for r in rows) == counts['positive']
            and len(rows) - counts['positive'] == counts['negative'], 'source class count mismatch')
    original = tuple(decision(row, -.6) for row in rows)
    require(asdict(_metrics(original)) == {k: v for k, v in stored['systems']['baseline'].items() if k != 'name'}, 'stored source metrics mismatch')
    return plan, hashes, rows, original


def replay(calibration_receipt, approved_receipt_sha256, source_run, output, approved_source_plan_sha256):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'replay output already exists: {output}')
    output = output.resolve()
    for input_root in (Path(source_run).resolve(), Path(calibration_receipt).resolve().parent):
        require(not output.is_relative_to(input_root) and not input_root.is_relative_to(output),
                'output must be separate from source and calibration directories')
    receipt, protocol = public_receipt(calibration_receipt, approved_receipt_sha256)
    source_plan, source_hashes, rows, original = validate_source(source_run, approved_source_plan_sha256, receipt)
    threshold = receipt['selection']['score_threshold']
    output.mkdir(parents=True, exist_ok=False)
    plan = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'recorded_score_replay',
            'calibration_receipt': str(Path(calibration_receipt).resolve()), 'calibration_receipt_sha256': approved_receipt_sha256,
            'protocol_sha256': receipt['protocol_sha256'], 'public_scores_sha256': receipt['scores_sha256'],
            'public_decisions_sha256': receipt['decisions_sha256'], 'source_run': str(Path(source_run).resolve()),
            'source_plan_sha256': approved_source_plan_sha256, 'source_artifact_sha256': source_hashes,
            'source_provenance': source_plan, 'score_threshold': threshold, 'comparator': '>',
            'implementation_sha256': {'dlib_threshold_replay.py': digest(__file__), 'runner.py': digest(Path(__file__).with_name('runner.py'))},
            'limitation': LIMITATION, 'timing_note': TIMING_NOTE}
    write(output / 'replay-plan.json', plan)
    calibrated = tuple(decision(row, threshold) for row in rows)
    with (output / 'decisions.ndjson').open('x') as stream:
        for item in calibrated:
            stream.write(json.dumps(asdict(item), sort_keys=True, allow_nan=False) + '\n')
    result = {'original': summary(original), 'calibrated': summary(calibrated),
              'changed_decisions': sum(a.predicted_identity_ids != b.predicted_identity_ids for a, b in zip(original, calibrated)),
              'replay_plan_sha256': digest(output / 'replay-plan.json'), 'decisions_sha256': digest(output / 'decisions.ndjson'),
              'limitation': LIMITATION, 'timing_note': TIMING_NOTE}
    write(output / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('calibration-receipt', 'approved-receipt-sha256', 'source-run', 'output', 'approved-source-plan-sha256'):
        parser.add_argument('--' + arg, required=True)
    replay(**vars(parser.parse_args()))
