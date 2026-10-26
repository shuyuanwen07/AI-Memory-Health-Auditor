"""Offline source-to-private-memory trace; benchmark annotations are analysis-only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from run_longmemeval_pilot import protocol_memory_profile


def trace(payload, result):
    rows = []
    for original in payload:
        source_ids, annotated = [], {}
        position = 0
        for session in original['haystack_sessions']:
            for message in session:
                position += 1
                mid = message.get('message_id') or message.get('id') or f'MSG-{position:03d}'
                if message.get('has_answer'):
                    source_ids.append(mid)
                    annotated[mid] = message['content']
        for condition in result['conditions']:
            case = next(c for c in condition['cases'] if c['case_id'] == original['question_id'])
            records = case['memory_evidence']
            associated = [r for r in records if set(source_ids).intersection(r['source_message_ids'])]
            rows.append({'case_id': case['case_id'], 'strategy': condition['strategy'],
                'question': case['question'], 'annotated_source_messages': annotated,
                'annotated_source_records': associated,
                'extracted_records': len(records),
                'lifecycle_counts': {state: sum(r['lifecycle_state'] == state for r in records)
                                     for state in sorted({r['lifecycle_state'] for r in records})},
                'supplied_records': [r for r in records if r['supplied']]})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--capacities', type=int, nargs='+', default=[50, 500])
    args = parser.parse_args()
    protocol = json.loads((args.directory / 'pilot-protocol.json').read_text())
    if protocol.get('source_authorised') is not True:
        raise ValueError('Source authorisation is required.')
    payload = json.loads((args.directory / 'pilot-subset.json').read_text())
    os.environ['DATABASE_URL'] = 'sqlite://'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.benchmarks.live import LiveBenchmarkRunner
    from app.schemas import TargetResponse, ExecutionMetadata
    from app.schemas.benchmark import LiveBenchmarkRequest
    from app.target_ai.providers import HttpTargetAIConnector
    from app.target_ai.rule_based import memory_input_evidence, private_context_instruction

    def capture_only(self, test, audit):
        assert test.expected_behavior == '' and test.supporting_memory_ids == []
        return TargetResponse(response_id='OFFLINE-' + test.test_id, test_id=test.test_id,
            run_id=test.run_id, response_text='Offline input trace; no model called.',
            model='offline-input-capture', temperature=0, created_at=datetime.now(timezone.utc),
            execution_metadata=ExecutionMetadata(request_attempts=0, reported_model='offline-input-capture',
                memory_input=memory_input_evidence(test, audit.target_configuration,
                    private_context_instruction(test, audit.target_configuration))))

    original = HttpTargetAIConnector.execute
    HttpTargetAIConnector.execute = capture_only
    report = {'scope': 'offline_input_trace_only', 'model_calls': 0,
              'annotations_used_only_after_target_preparation': True, 'traces': []}
    try:
        for capacity in args.capacities:
            request = LiveBenchmarkRequest(payload=payload, source_authorised=True,
                dataset_provenance={'dataset_version': protocol['source_provenance']['revision'],
                    'license': protocol['source_provenance']['license'],
                    'citation': protocol['source_provenance']['citation']},
                strategies=protocol['strategies'], target_memory_capacity=capacity,
                target_memory_profile=protocol_memory_profile(protocol))
            result = LiveBenchmarkRunner().run(request).model_dump(mode='json')
            report['traces'].append({'capacity': capacity, 'cases': trace(payload, result)})
    finally:
        HttpTargetAIConnector.execute = original
    (args.directory / 'offline-memory-diagnosis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'scope': report['scope'], 'capacities': args.capacities,
                      'rows': sum(len(t['cases']) for t in report['traces'])}))


if __name__ == '__main__':
    main()
