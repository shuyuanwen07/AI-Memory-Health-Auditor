"""Validate and mock-stage a frozen AC3 suite without model or database access.

This adapter intentionally does not implement live execution. The app has no
verified public fixed-question import API. Enabling real transport requires a
separate implementation and tests of authentication, idempotence, per-request
reservations and persistence. No generated answers or grades are fabricated.
"""
import argparse
import hashlib
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.ac3_evidence_paths import resolve_evidence_path, resolve_frozen_source, pilot_audits_equivalent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mock_reservation_for_suite(frozen):
    """Only for offline compile checks; never a provider charge or a hard cap."""
    config = frozen['protocol']
    model = config['model_configuration']
    remote_count = sum(model[f'{role}_provider'] == 'openrouter' for role in ('target', 'evaluator'))
    # A remote preparation pipeline is not per-test execution here. Keep one
    # conservative slot when it is the only remote role rather than dividing
    # by zero; fixed reviewed tests do not invoke that pipeline at this stage.
    if not remote_count and model['pipeline_provider'] == 'openrouter':
        remote_count = 1
    if not remote_count:
        return '0'
    configured = config['budget'].get('per_request_reservation_usd')
    if configured is not None:
        value = Decimal(str(configured))
        if not value.is_finite() or value <= 0: raise ValueError('Invalid frozen per-request reservation.')
        return str(value)
    count = sum(len(case.get('tests', [])) for case in frozen['suite']['cases'])
    maximum = Decimal(str(config['budget']['max_new_estimated_usd']))
    if count < 1 or not maximum.is_finite() or maximum <= 0:
        raise ValueError('A nonempty suite and positive mock budget are required.')
    reservation = maximum / Decimal(remote_count * count)
    if reservation * Decimal(remote_count * count) > maximum:
        reservation = reservation.next_minus()
    return str(reservation)


def _compile_stability_child(frozen_path, frozen, expected_sha, reservation, memory_snapshot):
    if memory_snapshot is not None:
        raise ValueError('Repeat subset requires reviewed multi-fact database verification.')
    logical_parent_path = Path(frozen.get('parent_frozen_path', ''))
    parent_path = resolve_frozen_source(logical_parent_path, ROOT)
    if parent_path.is_symlink() or not parent_path.is_file(): raise ValueError('Primary frozen suite is unavailable.')
    raw = parent_path.read_bytes(); parent_sha = frozen.get('parent_frozen_sha256')
    if sha(raw) != parent_sha: raise ValueError('Primary frozen suite digest changed.')
    parent = json.loads(raw)
    parent_reserve = parent['protocol']['budget'].get('per_request_reservation_usd')
    prior = compile_mock(parent_path, parent_sha, str(parent_reserve))
    sys.path.insert(0, str(ROOT))
    from scripts.prepare_ac3_stability_child import derive_child
    expected = derive_child(parent, logical_parent_path, parent_sha, frozen['frozen_at_utc'])
    if frozen != expected: raise ValueError('Repeat suite differs from the predeclared reviewed primary subset.')
    budget = frozen['protocol']['budget']
    reserve = Decimal(str(reservation)); maximum = Decimal(str(budget['max_new_estimated_usd']))
    bound = Decimal(str(budget['per_request_reservation_usd']))
    if not reserve.is_finite() or reserve <= 0 or reserve != bound or reserve * 40 > maximum:
        raise ValueError('Repeat reservation differs from its frozen planning allocation.')
    selected = set(frozen['protocol']['stability_plan']['selected_history_ids'])
    items = [dict(item, repeat_id=f"R2:{item['test_id']}", primary_test_id=item['test_id'])
             for item in prior['items'] if item['history_id'] in selected]
    if len(items) != 40 or any(item['grounding_review'] != 'valid' for item in items):
        raise ValueError('Repeat subset must contain the 40 independently reviewed primary questions.')
    fact_plan = frozen['reviewed_fact_plan']; digest = sha(json.dumps(fact_plan,ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode())
    fact_reviews = []
    for review in prior['fact_plan_reviews']:
        inherited = dict(review)
        inherited['fact_plan_sha256'] = digest
        inherited['note'] = (str(review.get('note', '')) +
            ' Exact repeat subset inherited from the reviewed primary plan; no additional human review claimed.')
        inherited['inherited_from_primary_frozen_sha256'] = parent_sha
        fact_reviews.append(inherited)
    if len(fact_reviews) != 2: raise ValueError('Primary fact review declarations are missing.')
    return {'format':'ac3-fixed-suite-mock-stage-v1','frozen_sha256':expected_sha,'mode':'mock',
        'model_called':False,'database_written':False,'responses_generated':0,'history_count':10,
        'question_count':40,'eligible_question_count':40,'memory_snapshot_checked_offline':False,
        'memory_records_verified_in_app':False,'per_request_mock_reservation_usd':str(reserve),
        'simulated_target_and_grader_reservation_usd':str(reserve*40),'max_new_estimated_usd':str(maximum),
        'model_configuration':frozen['protocol']['model_configuration'],'items':items,
        'reviewed_fact_plan':fact_plan,'fact_plan_reviews':fact_reviews,
        'study_role':'stability_repeat','primary_frozen_sha256':parent_sha,
        'limitation':'Derived subset; original reviewer identities are not independently authenticated. No model call or live budget check.'}


def compile_mock(frozen_path, expected_sha, reservation, memory_snapshot=None):
    if frozen_path.is_symlink() or not frozen_path.is_file():
        raise ValueError('Frozen suite must be an existing regular file.')
    raw = frozen_path.read_bytes()
    if sha(raw) != expected_sha:
        raise ValueError('Frozen suite does not match the separately recorded SHA-256.')
    frozen = json.loads(raw)
    if frozen.get('format') == 'ac3-stability-derived-suite-v1':
        return _compile_stability_child(frozen_path, frozen, expected_sha, reservation, memory_snapshot)
    if frozen.get('format') != 'ac3-prospective-frozen-suite-v1' or frozen.get('execution_supported') is not False or frozen.get('model_called') is not False or frozen.get('results_observed') is not False:
        raise ValueError('Expected an unexecuted, guarded frozen suite.')
    bound_paths = {}
    for name, expected in frozen['source_hashes'].items():
        path = resolve_frozen_source(name, ROOT)
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != expected:
            raise ValueError('A frozen source file changed or is unavailable.')
        key=str(path)
        if key in bound_paths and bound_paths[key] != expected:
            raise ValueError('Conflicting hashes bind the same frozen source.')
        bound_paths[key] = expected
    def evidence_bound(item):
        if not isinstance(item,dict) or not isinstance(item.get('path'),str): return False
        return bound_paths.get(str(resolve_evidence_path(item['path']))) == item.get('sha256')
    suite = frozen['suite']
    encoded = json.dumps(suite, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if sha(encoded) != frozen['canonical_suite_sha256']:
        raise ValueError('Frozen suite content changed.')
    protocol = frozen['protocol']
    config_name = frozen.get('config_source')
    if not config_name or config_name not in frozen['source_hashes']:
        raise ValueError('Protocol configuration is not bound to a frozen source.')
    config_path = resolve_frozen_source(config_name, ROOT)
    if json.loads(config_path.read_text()) != protocol:
        raise ValueError('Frozen protocol differs from the reviewed source configuration.')
    if not frozen['grounding']['grounding_ready_for_adjudication'] or protocol['human_attestations'].get('pilot_thresholds_accepted') is not True:
        raise ValueError('Human review and accepted pilot thresholds are required.')
    if frozen.get('protocol_evidence_method') == 'recorded_user_decisions_and_local_observation_not_human_attestation':
        names = frozen.get('protocol_evidence_sources', [])
        if len(names) != 3 or any(name not in frozen['source_hashes'] for name in names):
            raise ValueError('Protocol decision evidence is not fully bound.')
        from scripts.ac3_protocol_evidence import validate_protocol_evidence
        decisions = [json.loads(resolve_frozen_source(name, ROOT).read_text()) for name in names]
        validate_protocol_evidence(protocol, *decisions, frozen['input_sha256'])
        validate_protocol_evidence(protocol, decisions[0], decisions[1], frozen.get('local_observation_at_freeze', {}), frozen['input_sha256'])
    elif not all(protocol['human_attestations'].get(key) is True for key in ('held_out_outputs_not_generated_or_inspected', 'exclusions_and_abstention_policy_frozen')):
        raise ValueError('Prospective protocol evidence or human attestations are required.')
    if protocol['human_attestations'].get('pilot_provenance_reviewed') is not True:
        audit_name, selection_name = frozen.get('pilot_provenance_audit_source'), frozen.get('threshold_approval_source')
        if (frozen.get('pilot_provenance_review_method') != 'automated_source_check_not_human_attestation' or
                not audit_name or audit_name not in frozen['source_hashes'] or
                not selection_name or selection_name not in frozen['source_hashes']):
            raise ValueError('A bound pilot provenance source audit is required.')
        sys.path.insert(0, str(ROOT))
        from scripts.prepare_ac3_pilot_provenance_audit import build_audit
        audit_path, selection_path = resolve_frozen_source(audit_name,ROOT), resolve_frozen_source(selection_name,ROOT)
        audit = json.loads(audit_path.read_text())
        if not pilot_audits_equivalent(audit,build_audit()) or audit.get('user_threshold_selection_sha256') != sha(selection_path.read_bytes()):
            raise ValueError('Pilot provenance audit or threshold selection differs from current source evidence.')
    reviews = []
    expected_count = sum(len(case.get('tests', [])) for case in suite['cases'])
    for name in frozen['review_sources']:
        if name not in frozen['source_hashes']:
            raise ValueError('Reviewer path is not bound to the frozen sources.')
        path = resolve_frozen_source(name, ROOT)
        review = json.loads(path.read_text())
        labels = {q['test_id']: q['review']['question_validity'] for case in review['cases'] for q in case['questions']}
        if len(labels) != expected_count: raise ValueError('Reviewer question identities are incomplete or duplicated.')
        reviews.append(labels)
    if len(reviews) != 2 or set(reviews[0]) != set(reviews[1]) or any(reviews[0][k] != reviews[1][k] or reviews[0][k] not in {'valid', 'invalid'} for k in reviews[0]):
        raise ValueError('Every question must have an agreed valid or invalid grounding judgment.')
    fact_plan = frozen.get('reviewed_fact_plan')
    fact_reviews = None
    if fact_plan is not None:
        if __package__:
            from .ac3_reviewed_fact_map import validate_fact_plan
        else:
            from ac3_reviewed_fact_map import validate_fact_plan
        fact_source = frozen.get('fact_plan_source')
        review_sources = frozen.get('fact_review_sources')
        if (not isinstance(fact_source, str) or fact_source not in frozen['source_hashes'] or
                not isinstance(review_sources, list) or len(review_sources) != 2 or
                any(name not in frozen['source_hashes'] for name in review_sources)):
            raise ValueError('Reviewed fact plan and both reviews must be bound to frozen sources.')
        def read_source(name):
            path = resolve_frozen_source(name, ROOT)
            return json.loads(path.read_text())
        if read_source(fact_source) != fact_plan:
            raise ValueError('Frozen fact plan differs from its source.')
        fact_reviews = [read_source(name) for name in review_sources]
        validate_fact_plan(suite, fact_plan, fact_reviews)
        if memory_snapshot is not None:
            raise ValueError('Use reviewed multi-fact database verification instead of the legacy memory snapshot.')
    if frozen.get('composite_manifest_source') is not None:
        manifest_name, candidate_name = frozen['composite_manifest_source'], frozen.get('candidate_source')
        if manifest_name not in frozen['source_hashes'] or candidate_name not in frozen['source_hashes'] or not fact_reviews:
            raise ValueError('Composite manifest, source and fact declarations must all be frozen.')
        def source_path(name):
            return resolve_frozen_source(name, ROOT)
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_conflict_delta_reviews import verify_manifest
        manifest_path = source_path(manifest_name)
        manifest = json.loads(manifest_path.read_bytes())
        for item in manifest.get('inputs', []):
            if not evidence_bound(item):
                raise ValueError('Composite input is not bound to frozen sources.')
        result = verify_manifest(manifest_path, source_path(candidate_name).read_bytes(),
            [source_path(name).read_bytes() for name in frozen['review_sources']],
            [source_path(name).read_bytes() for name in frozen['fact_review_sources']])
        if result['source_sha256'] != frozen['input_sha256']:
            raise ValueError('Composite source differs from frozen source.')
    if frozen.get('expanded_manifest_source') is not None:
        manifest_name, candidate_name = frozen['expanded_manifest_source'], frozen.get('candidate_source')
        if (manifest_name not in frozen['source_hashes'] or candidate_name not in frozen['source_hashes'] or
                not fact_reviews or frozen.get('composite_manifest_source') is not None):
            raise ValueError('Expanded source, manifest and both fact declarations must be frozen.')
        def source_path(name):
            return resolve_frozen_source(name, ROOT)
        manifest_path = source_path(manifest_name)
        manifest = json.loads(manifest_path.read_bytes())
        entries = manifest.get('inputs', [])
        allowed_lengths = {'ac3-expanded-composite-review-v1':11, 'ac3-expanded-revised-composite-review-v1':16,
                           'ac3-expanded-rebased-composite-review-v1':18,
                           'ac3-expanded-user-confirmed-rebased-composite-review-v1':21,
                           'ac3-expanded-both-rounds-confirmed-composite-review-v1':24,
                           'ac3-expanded-restored-composite-review-v1':11,
                           'ac3-expanded-restored-user-confirmed-composite-review-v1':14,
                           'ac3-expanded-h19-unresolved-composite-review-v1':12,
                           'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1':15}
        if (manifest.get('format') not in allowed_lengths or len(entries) != allowed_lengths[manifest['format']] or
                any(not evidence_bound(item) for item in entries)):
            raise ValueError('Expanded inputs are not all bound to frozen sources.')
        prior_path = source_path(entries[2]['path'])
        prior = json.loads(prior_path.read_bytes())
        if any(not evidence_bound(item) for item in prior.get('inputs', [])):
            raise ValueError('Prior composite inputs are not all bound to frozen sources.')
        restoration_entries=entries
        if manifest.get('format') in ('ac3-expanded-h19-unresolved-composite-review-v1',
                                      'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'):
            v7_entries=prior.get('inputs',[])
            if len(v7_entries)!=14:
                raise ValueError('V8 source lacks the full user-confirmed v7 review evidence.')
            unresolved=json.loads(source_path(entries[9]['path']).read_bytes())
            unresolved_evidence=unresolved.get('evidence',{})
            if not isinstance(unresolved_evidence,dict) or any(not evidence_bound(item) for item in unresolved_evidence.values()):
                raise ValueError('Unresolved-edge source evidence is not bound to frozen sources.')
            restoration_entries=v7_entries
            prior=json.loads(source_path(v7_entries[2]['path']).read_bytes())
            if any(not evidence_bound(item) for item in prior.get('inputs',[])):
                raise ValueError('V6 composite inputs are not all bound to frozen sources.')
        if manifest.get('format') in ('ac3-expanded-restored-composite-review-v1',
                                     'ac3-expanded-restored-user-confirmed-composite-review-v1',
                                     'ac3-expanded-h19-unresolved-composite-review-v1',
                                     'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'):
            v6_entries=prior.get('inputs',[])
            if len(v6_entries)!=24:
                raise ValueError('Restored source lacks the full v6 review evidence.')
            v3=json.loads(source_path(v6_entries[2]['path']).read_bytes())
            if any(not evidence_bound(item) for item in v3.get('inputs',[])):
                raise ValueError('Original review inputs are not all bound to frozen sources.')
            restoration=json.loads(source_path(restoration_entries[8]['path']).read_bytes())
            evidence=restoration.get('evidence',{})
            if not isinstance(evidence,dict) or any(not evidence_bound(item) for item in evidence.values()):
                raise ValueError('Restored question source evidence is not bound to frozen sources.')
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
        result = verify_expanded_manifest(manifest_path, source_path(candidate_name).read_bytes(),
            [source_path(name).read_bytes() for name in frozen['review_sources']],
            [source_path(name).read_bytes() for name in frozen['fact_review_sources']])
        if result['source_sha256'] != frozen['input_sha256']:
            raise ValueError('Expanded source differs from frozen source.')
    cfg = protocol['model_configuration']; budget = protocol['budget']
    if frozen.get('expanded_manifest_source') and cfg.get('target_provider') == 'openrouter':
        sys.path.insert(0, str(ROOT))
        from scripts.ac3_stability import validate_plan, canonical_sha
        stability = protocol.get('stability_plan')
        validate_plan(stability, suite)
        if (frozen.get('study_role') != 'primary_validation' or
                frozen.get('stability_plan_sha256') != canonical_sha(stability)):
            raise ValueError('The repeat plan is not bound to this primary study.')
    maximum, already, cap = (Decimal(str(budget[key])) for key in ('max_new_estimated_usd', 'existing_estimated_usd', 'cumulative_cap_usd'))
    reserve = Decimal(str(reservation))
    if not all(value.is_finite() for value in (maximum, already, cap, reserve)) or reserve < 0 or maximum < 0 or already < 0 or cap < Decimal('0.4') or already + maximum > cap:
        raise ValueError('Invalid budget or requested reservation.')
    remote = any(cfg.get(f'{role}_provider') == 'openrouter' for role in ('target', 'evaluator', 'pipeline'))
    if remote and reserve <= 0:
        raise ValueError('Remote request simulation requires a positive per-request reservation.')
    if not remote and (maximum != 0 or reserve != 0):
        raise ValueError('The local-only mock must not allocate hosted API budget.')
    if frozen.get('expanded_manifest_source') and remote and budget.get('per_request_reservation_usd') is not None and reserve != Decimal(str(budget['per_request_reservation_usd'])):
        raise ValueError('Reservation differs from the frozen per-request planning allocation.')
    # The optional snapshot is an explicitly declared test fixture/observation,
    # not proof that any memory exists in the application. A future live
    # adapter must fetch and revalidate current records under a run lock.
    source_to_memory = {}
    if memory_snapshot is not None:
        histories = memory_snapshot.get('histories')
        if not isinstance(histories, list) or len(histories) != len(suite['cases']):
            raise ValueError('Memory snapshot must cover the eight separate histories.')
        case_map = {case['history_id']: case for case in suite['cases']}
        conversations, memory_ids, covered_histories = set(), set(), set()
        for history in histories:
            history_id, conversation_id = history.get('history_id'), history.get('conversation_id')
            if history_id not in case_map or history_id in covered_histories or not isinstance(conversation_id, str) or not conversation_id or conversation_id in conversations:
                raise ValueError('Each history needs a distinct, nonempty conversation ID.')
            covered_histories.add(history_id); conversations.add(conversation_id)
            source = {message['message_id']: message['text'] for message in case_map[history_id]['source_messages']}
            records = history.get('memories')
            if not isinstance(records, list): raise ValueError('Missing declared confirmed memory records.')
            for memory in records:
                memory_id, sources = memory.get('memory_id'), memory.get('source_message_ids')
                if not isinstance(memory_id, str) or not memory_id or memory_id in memory_ids or memory.get('conversation_id') != conversation_id or memory.get('status') not in {'confirmed', 'edited'} or not isinstance(sources, list) or len(sources) != 1 or sources[0] not in source:
                    raise ValueError('Memory IDs, conversation, status and source must match the declared history.')
                source_id = sources[0]
                if (history_id, source_id) in source_to_memory or memory.get('canonical_value') != source[source_id]:
                    raise ValueError('Each source message must map once to a verbatim confirmed memory.')
                source_to_memory[history_id, source_id] = memory_id; memory_ids.add(memory_id)
            if set(source) != {source_id for h, source_id in source_to_memory if h == history_id}:
                raise ValueError('Every frozen source message needs an exact memory mapping.')
        if covered_histories != set(case_map): raise ValueError('Memory snapshot omits a frozen history.')
    items = []
    seen = set()
    for history in suite['cases']:
        known = {message['message_id'] for message in history['source_messages']}
        for test in history['tests']:
            if test['test_id'] in seen or not test.get('question') or not test.get('expected_behavior') or not set(test.get('supporting_source_message_ids', [])) <= known or not test.get('supporting_source_message_ids'):
                raise ValueError('Question identity, expected behaviour or source mapping is invalid.')
            seen.add(test['test_id'])
            items.append({'history_id': history['history_id'], 'test_id': test['test_id'], 'dimension': test['dimension'], 'question': test['question'], 'expected_behavior': test['expected_behavior'], 'supporting_source_message_ids': test['supporting_source_message_ids'], 'supporting_memory_ids': [source_to_memory[history['history_id'], source_id] for source_id in test['supporting_source_message_ids']] if memory_snapshot is not None else None, 'grounding_review': reviews[0].get(test['test_id'])})
    required_histories, required_questions = (30, 120) if frozen.get('expanded_manifest_source') else (8, 32)
    if (len(suite['cases']) != required_histories or len(items) != required_questions or
            set(reviews[0]) != seen or frozen['grounding'].get('questions') != required_questions):
        raise ValueError('Frozen suite size or reviewed question identities do not match its study design.')
    eligible = [item for item in items if item['grounding_review'] == 'valid']
    # This is a mocked reservation trace, not a bound on actual future token use.
    remote_count = sum(cfg.get(f'{role}_provider') == 'openrouter' for role in ('target', 'evaluator'))
    if not remote_count and cfg.get('pipeline_provider') == 'openrouter':
        remote_count = 1
    simulated = reserve * len(eligible) * remote_count
    if simulated > maximum:
        raise ValueError('Mock reservation would exceed the frozen new-spend cap before requests start.')
    return {'format': 'ac3-fixed-suite-mock-stage-v1', 'frozen_sha256': expected_sha, 'mode': 'mock', 'model_called': False, 'database_written': False, 'responses_generated': 0, 'history_count': len(suite['cases']), 'question_count': len(items), 'eligible_question_count': len(eligible), 'memory_snapshot_checked_offline': memory_snapshot is not None, 'memory_records_verified_in_app': False, 'per_request_mock_reservation_usd': str(reserve), 'simulated_target_and_grader_reservation_usd': str(simulated), 'max_new_estimated_usd': str(maximum), 'model_configuration': cfg, 'items': items, 'reviewed_fact_plan': fact_plan, 'fact_plan_reviews': fact_reviews, 'limitation': 'Dry-run staging only; a declared memory snapshot is not proof of app state. Source message IDs require revalidation against live confirmed memory IDs under a run lock. No live adapter or real budget enforcement is implemented.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--frozen-sha256', required=True, help='SHA-256 recorded separately by the freeze command.')
    parser.add_argument('--mock-reserve-usd', default='0', help='Per-request simulated upper reservation; no real billing.')
    parser.add_argument('--memory-snapshot', type=Path, help='Optional declared per-history memory mapping to validate offline; never reads the app database.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['mock'], default='mock')
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.memory_snapshot.read_text()) if args.memory_snapshot else None
        result = compile_mock(args.frozen, args.frozen_sha256, args.mock_reserve_usd, snapshot)
    except (ValueError, InvalidOperation, KeyError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'output': str(args.output), 'question_count': result['question_count'], 'model_called': False, 'database_written': False}))


if __name__ == '__main__':
    main()
