"""Reconstruct saved pilot inputs offline, without reusing scores as new model calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from run_longmemeval_pilot import protocol_memory_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directories', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ['DATABASE_URL'] = 'sqlite://'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.benchmarks.live import LiveBenchmarkRunner
    from app.schemas import ExecutionMetadata, TargetResponse
    from app.schemas.benchmark import LiveBenchmarkRequest
    from app.target_ai.providers import HttpTargetAIConnector
    from app.target_ai.rule_based import memory_input_evidence, private_context_instruction

    proof = {'scope': 'offline_target_input_equivalence_only', 'model_calls': 0, 'cases': []}
    original = HttpTargetAIConnector.execute
    try:
        for directory in args.directories:
            protocol = json.loads((directory / 'pilot-protocol.json').read_text())
            if protocol.get('source_authorised') is not True:
                raise ValueError('Source processing must be authorised.')
            saved = json.loads((directory / 'pilot-report.json').read_text())
            payload = json.loads((directory / 'pilot-subset.json').read_text())
            receipts = iter(saved['target_call_receipts'])

            def capture(self, test, audit):
                old = next(receipts)['response']['execution_metadata']['memory_input']
                current = memory_input_evidence(test, audit.target_configuration,
                    private_context_instruction(test, audit.target_configuration))
                fields = ('record_count', 'context_sha256', 'instruction_sha256', 'prompt_sha256')
                differences = [key for key in fields if old[key] != getattr(current, key)]
                proof['cases'].append({'directory': directory.name, 'strategy': audit.memory_strategy.value,
                    'capacity': protocol['target_memory_capacity'], 'prompt_sha256': current.prompt_sha256,
                    'inputs_equal': not differences, 'different_fields': differences})
                return TargetResponse(response_id='OFFLINE-' + test.test_id, test_id=test.test_id,
                    run_id=test.run_id, response_text='Offline equivalence trace; no model call.',
                    model='offline-input-capture', temperature=0, created_at=datetime.now(timezone.utc),
                    execution_metadata=ExecutionMetadata(request_attempts=0, memory_input=current))

            HttpTargetAIConnector.execute = capture
            provenance = protocol['source_provenance']
            LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=payload, source_authorised=True,
                dataset_provenance={'dataset_version': provenance['revision'],
                                    'license': provenance['license'], 'citation': provenance['citation']},
                provider=protocol['provider'], model=protocol['model'],
                strategies=protocol['strategies'], max_cases=len(payload),
                target_memory_capacity=protocol['target_memory_capacity'],
                target_memory_profile=protocol_memory_profile(protocol)))
            if next(receipts, None) is not None:
                raise ValueError('Saved receipt count differs from reconstructed calls.')
    finally:
        HttpTargetAIConnector.execute = original
    proof['all_inputs_equal'] = all(r['inputs_equal'] for r in proof['cases'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'calls_reconstructed': len(proof['cases']), 'all_inputs_equal': proof['all_inputs_equal']}))


if __name__ == '__main__':
    main()
