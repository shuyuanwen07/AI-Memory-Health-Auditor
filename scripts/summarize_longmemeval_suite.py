"""Check frozen source/response identities and export descriptive pilot results."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from run_longmemeval_pilot import protocol_memory_profile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    manifest = json.loads((root / 'suite-manifest.json').read_text())
    rows, configurations, runtimes = [], set(), set()
    assessment_versions, assessment_scopes = set(), set()
    memory_profiles, writer_versions = set(), set()
    target_tokens = {'input': 0, 'output': 0}
    assessor_tokens = {'input': 0, 'output': 0}
    for entry in manifest['cases']:
        directory = root / entry['directory']
        data = (directory / 'pilot-subset.json').read_bytes()
        assert digest(data) == entry['subset_sha256']
        source = json.loads(data)
        assert len(source) == 1 and source[0]['question_id'] == entry['case_id']
        protocol_bytes = (directory / 'pilot-protocol.json').read_bytes()
        protocol = json.loads(protocol_bytes)
        assert protocol['source_authorised'] is True and protocol['target_memory_capacity'] == manifest['capacity']
        report = json.loads((directory / 'pilot-report.json').read_text())
        assert report['status'] == 'completed'
        assert report['protocol_sha256'] == digest(protocol_bytes)
        assessment_scopes.add(report.get('assessment_rule_scope', 'legacy_custom_v1'))
        result = report['benchmark_result']
        assert result['provider'] == 'openrouter' and result['model'] == manifest['reader']
        assert result['target_memory_capacity'] == manifest['capacity']
        for key, value in protocol_memory_profile(protocol).items():
            assert result['target_memory_profile'][key] == value
        memory_profiles.add(json.dumps(result['target_memory_profile'], sort_keys=True))
        writer_versions.add(result['writer_version'])
        assert result['reader_configuration'] == 'strong'
        assert result['source_fingerprint_sha256'] == digest(
            json.dumps(source, sort_keys=True, separators=(',', ':'), default=str).encode())
        assert {c['strategy'] for c in result['conditions']} == set(manifest['strategies'])
        assert len(result['conditions']) == len(report['target_call_receipts']) == len(report['semantic_assessments']) == 2
        configurations.add(result['configuration_fingerprint_sha256'])
        runtimes.add(json.dumps(result['audit_runtime_signature'], sort_keys=True))
        assessments = {(a['strategy'], a['case_id']): a for a in report['semantic_assessments']}
        for index, condition in enumerate(result['conditions']):
            assert len(condition['cases']) == 1
            case = condition['cases'][0]
            assert case['case_id'] == entry['case_id']
            assert case['question'] == source[0]['question'].strip()
            assert case['expected_answer'] == str(source[0]['answer']).strip()
            receipt = report['target_call_receipts'][index]
            assert receipt['status'] == 'completed'
            assert receipt['response']['response_text'] == case['response_text']
            metadata = receipt['response']['execution_metadata']
            assert metadata['reported_model'] == manifest['reader']
            assessment = assessments[(condition['strategy'], case['case_id'])]
            assert assessment['status'] == 'completed'
            assert assessment['execution']['reported_model'] == manifest['reader']
            assessment_versions.add(assessment['execution']['prompt_template_version'])
            assert type(assessment['verdict']['correct']) is bool
            for key in ('input', 'output'):
                target_tokens[key] += metadata.get(key + '_tokens') or 0
                assessor_tokens[key] += assessment['execution'].get('reported_' + key + '_tokens') or 0
            rows.append({'case_id': case['case_id'], 'category': entry['category'],
                'strategy': condition['strategy'], 'semantic_correct': assessment['verdict']['correct'],
                'question': case['question'], 'reference': case['expected_answer'],
                'response': case['response_text'], 'assessment_reason': assessment['verdict']['reason'],
                'lexical_match': case['lexical_match'], 'stored_memories': case['stored_memory_count'],
                'retained_memories': case['retained_memory_count'], 'supplied_memories': len(case['supplied_memory_ids']),
                'finish_reason': metadata.get('finish_reason')})
    assert len(rows) == manifest['planned_target_calls'] == manifest['planned_assessments']
    assert len(configurations) == len(runtimes) == 1
    assert len(assessment_versions) == len(assessment_scopes) == 1
    assert len(memory_profiles) == len(writer_versions) == 1
    summaries = {}
    for strategy in manifest['strategies']:
        members = [row for row in rows if row['strategy'] == strategy]
        correct = sum(row['semantic_correct'] for row in members)
        categories = defaultdict(lambda: {'correct': 0, 'total': 0})
        for row in members:
            categories[row['category']]['correct'] += row['semantic_correct']
            categories[row['category']]['total'] += 1
        summaries[strategy] = {'correct': correct, 'total': len(members),
                               'percentage': round(100 * correct / len(members), 1),
                               'categories': dict(categories)}
    summary = {'scope': manifest['scope'], 'case_count': len(manifest['cases']),
               'capacity': manifest['capacity'], 'strategies': summaries,
               'target_calls': len(rows), 'automatic_assessments': len(rows),
               'reader_model': manifest['reader'], 'assessor_model': manifest['reader'],
               'assessment_prompt_version': next(iter(assessment_versions)),
               'assessment_rule_scope': next(iter(assessment_scopes)),
               'target_memory_profile': json.loads(next(iter(memory_profiles))),
               'writer_version': next(iter(writer_versions)),
               'verified_source_response_and_model_correspondence': True,
               'one_shared_configuration_and_runtime': True,
               'reported_target_tokens': target_tokens, 'reported_assessor_tokens': assessor_tokens,
               'token_usage_scope': 'Sum of available provider usage fields; absent fields are not independently measured.',
               'limits': ['Exploratory development samples and one repetition; no formal C ranking agreement established.',
                          'Same-model automated assessment using the recorded rubric version; not independent human labels or official scorer execution.',
                          'Capacity500 and context16000characters are explicit conditions; capacity50 controls remain separate.',
                          'Writer and retrieval capabilities depend on the frozen target memory profile; per-record source dates are not guaranteed in reader context.']}
    (root / 'suite-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (root / 'suite-results.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'cases': summary['case_count'], 'strategies': summaries,
                      'correspondence_verified': True}))


if __name__ == '__main__':
    main()
