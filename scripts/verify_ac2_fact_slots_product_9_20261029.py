"""Check source-bound nine-history run, preserving failures and avoiding validity claims."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1'
SOURCE = ROOT / 'output/proposal-delivery/ac2-independent-source-proposal-20261029/histories.json'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    protocol = json.loads((RUN/'protocol.json').read_text())
    ledger = json.loads((RUN/'ledger.json').read_text())
    summary = json.loads((RUN/'summary.json').read_text())
    assert digest(SOURCE) == protocol['source_sha256']
    assert digest(RUN/'protocol.json') == ledger['protocol_sha256'] == summary['protocol_sha256']
    assert digest(RUN/'ledger.json') == summary['ledger_sha256']
    ids = protocol['history_ids']
    assert len(ids) == len(set(ids)) == 9
    assert [h['history_id'] for h in ledger['histories']] == ids
    sources = {h['conversation_id']: h for h in json.loads(SOURCE.read_text())['conversations']}
    counts, dimensions, states, versions = Counter(), Counter(), Counter(), Counter()
    n = 0
    for h in ledger['histories']:
        states[h['state']] += 1
        assert h['state'] in ('completed', 'failed')
        calls = h['requests']
        assert all('/execute' not in c['path'] and '/evaluate' not in c['path'] for c in calls)
        assert len([c for c in calls if c['path'].endswith('/generate-tests')]) <= 1
        imports = [c for c in calls if c['path'] == '/conversations' and c['state'] == 'returned']
        if imports:
            original = sources[h['history_id']]['messages']
            assert [x['content'] for x in imports[0]['request']['messages']] == [x['text'] for x in original]
            assert [x['message_id'] for x in imports[0]['request']['messages']] == [x['source_id'] for x in original]
        if h['state'] != 'completed':
            continue
        reviews = [c['response'] for c in calls if c['path'].endswith('/test-review') and c['state'] == 'returned']
        extractions = [c['response'] for c in calls if c['path'].endswith('/extract') and c['state'] == 'returned']
        assert len(reviews) == len(extractions) == 1
        assert reviews[0]['coverage_policy'] == protocol['coverage_policy']
        facts = {m['memory_id'] for m in extractions[0]}
        for t in reviews[0]['tests']:
            assert t['supporting_memory_ids'] and set(t['supporting_memory_ids']) <= facts
            assert t['quality_status'] == 'pending'
            n += 1
            counts[t['quality_status']] += 1
            dimensions[t['dimension']] += 1
            versions[t['generator_version']] += 1
    assert n == summary['saved_questions']
    assert dict(states) == summary['states'] and dict(counts) == summary['quality_states']
    assert dict(dimensions) == summary['dimensions']
    assert states['completed'] == summary['histories_with_saved_suite']
    assert not versions or set(versions) == {'agent-coverage-semantic-v23'}
    result = {'protocol_sha256': digest(RUN/'protocol.json'), 'ledger_sha256': digest(RUN/'ledger.json'),
              'source_sha256': digest(SOURCE), 'states': dict(states), 'saved_questions': n,
              'dimensions': dict(dimensions), 'quality_states': dict(counts), 'generator_versions': dict(versions),
              'scope': 'Recorded provenance and counts only; no target answers, human validity, causal or population claims.'}
    (RUN/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
