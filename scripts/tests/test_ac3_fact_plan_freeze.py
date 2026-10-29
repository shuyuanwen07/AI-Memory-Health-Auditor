"""Round trip with synthetic-only attestations; these are not human reviews."""
import hashlib
import json
import subprocess
import sys
from scripts import freeze_ac3_prospective_suite as freeze
from scripts.ac3_fixed_suite_adapter import compile_mock, sha
from scripts.tests.test_ac3_rehearsal_workflow import frozen


def test_reviewed_fact_plan_freeze_and_source_tamper(frozen, tmp_path):
    old_path, _old_sha, _ = frozen
    candidate = json.loads(old_path.read_text())['suite']
    histories = {}
    for case in candidate['cases']:
        history = case['history_id']
        facts, by_message = [], {}
        for message in case['source_messages']:
            source, body = message['message_id'], message['text']
            parts = body.split('. ', 1) if source.endswith(('-M4', '-M5')) else [body]
            by_message[source] = []
            for n, span in enumerate(parts):
                ident = f'{source}-F{n}'
                facts.append({'memory_id': ident, 'source_message_id': source, 'source_span': span,
                              'canonical_value': span + (' [synthetic normalization]' if n else '')})
                by_message[source].append(ident)
        def edge(a, kind, b, evidence):
            return {'memory_id': a, 'relationship_type': kind, 'target_memory_id': b, 'evidence_message_ids': [evidence]}
        relationships = [edge(by_message[f'{history}-M3'][0], 'UPDATE', by_message[f'{history}-M2'][0], f'{history}-M3'),
            edge(by_message[f'{history}-M4'][0], 'CONFLICT', by_message[f'{history}-M4'][1], f'{history}-M4'),
            edge(by_message[f'{history}-M5'][1], 'CONTEXTUAL_OVERRIDE', by_message[f'{history}-M5'][0], f'{history}-M5')]
        histories[history] = {'facts': facts, 'relationships': relationships}
    plan = {'histories': histories}
    plan_sha = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    plan_path = tmp_path / 'fact-plan.json'; plan_path.write_text(json.dumps(plan))
    fact_reviews = []
    for index in (1, 2):
        p = tmp_path / f'fact-review-{index}.json'
        p.write_text(json.dumps({'reviewer_label': f'synthetic-{index}', 'completed_by_human': True,
            'completed_independently': True, 'reviewed_fact_and_relation_semantics': True, 'fact_plan_sha256': plan_sha}))
        fact_reviews.append(p)
    output = tmp_path / 'fact-frozen.json'
    command = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'),
        '--review-1', str(tmp_path / 'reviewer-1.json'), '--review-2', str(tmp_path / 'reviewer-2.json'),
        '--config', str(tmp_path / 'config.json'), '--fact-plan', str(plan_path),
        '--fact-review-1', str(fact_reviews[0]), '--fact-review-2', str(fact_reviews[1]), '--output', str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    digest = sha(output.read_bytes())
    compiled = compile_mock(output, digest, '0')
    assert compiled['reviewed_fact_plan'] == plan and compiled['model_called'] is False
    fact_reviews[0].write_text('{}')
    import pytest
    with pytest.raises(ValueError, match='source file changed'):
        compile_mock(output, digest, '0')
