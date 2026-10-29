"""Inspect recorded v7 target request sampling without modifying the run."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm'
OUT = ROOT / 'output/proposal-delivery/c-v7-sampling-record-audit-20261030.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol_path, run_path, subset_path = [RUN / name for name in ('protocol.json', 'C-live.json', 'longmemeval-subset.json')]
    protocol, run = (json.loads(path.read_text()) for path in (protocol_path, run_path))
    assert run['protocol_sha256'] == digest(protocol_path) and run['subset_sha256'] == digest(subset_path)
    intents, receipts = run['target_call_intents'], run['target_receipts']
    assert len(intents) == len(receipts) == 360
    key = lambda row: (row['repetition'], row['strategy'], row['question_id'])
    assert len({key(row) for row in intents}) == 360 and {key(row) for row in intents} == {key(row) for row in receipts}
    keys = Counter(tuple(attempt['request_contract']['payload_keys']) for row in intents for attempt in row['attempts'])
    controls = Counter(str(row['response']['execution_metadata'].get('sampling_control')) for row in receipts)
    sent = Counter(str(row['response']['execution_metadata'].get('sent_temperature')) for row in receipts)
    output = {'protocol_sha256': digest(protocol_path), 'subset_sha256': digest(subset_path), 'run_sha256': digest(run_path), 'planned_temperature': protocol['target'].get('temperature'), 'planned_random_seed': protocol['target'].get('random_seed'), 'target_intents': len(intents), 'target_receipts': len(receipts), 'sampling_control': dict(controls), 'sent_temperature': dict(sent), 'payload_key_sets': [{'keys': list(k), 'attempts': v} for k, v in keys.items()], 'recorded_frozen_at_utc': protocol['frozen_at_utc'], 'first_recorded_dispatch_utc': run['provider_dispatch_starts_utc'][0], 'limitations': 'Recorded timestamps are not independent evidence of actual freeze timing. Request contracts record payload keys and hashes, not provider-side sampling or deterministic repeatability. This audit covers target intents and receipts only, not grader requests or all AC5 runs.'}
    OUT.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
