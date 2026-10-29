"""Post-outcome inventory diagnostic, not a generator or validity assessment."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-partial-twenty-five-history-development-20261029-v1'

def main():
    raw = (RUN / 'ledger.json').read_bytes()
    ledger = json.loads(raw)
    rows = []
    for h in ledger['histories']:
        extract = next(r['response'] for r in h['requests'] if r['path'].endswith('/extract') and r['state'] == 'returned')
        confirm = next(r for r in h['requests'] if r['path'].endswith('/confirm-ground-truth') and r['state'] == 'returned')
        confirmed = set(confirm['request']['confirmed_memory_ids'])
        assert confirmed == {m['memory_id'] for m in extract}
        related = {m['memory_id'] for m in extract if m['relationships']}
        related.update(r['target_memory_id'] for m in extract for r in m['relationships'])
        eligible = [m['memory_id'] for m in extract if m['memory_id'] in confirmed and m['memory_id'] not in related
                    and m['canonical_value'].strip() and m['source_message_ids']]
        rows.append({'history_id': h['history_id'], 'generation_state': h['state'],
                     'provisionally_confirmed_fact_count': len(confirmed),
                     'unrelated_cited_fact_ids': eligible, 'candidate_count': len(eligible)})
    assert len(rows) == 25 and sum(row['generation_state'] == 'failed' for row in rows) == 12
    out = {'ledger_sha256': hashlib.sha256(raw).hexdigest(), 'histories': len(rows),
           'no_suite_histories_with_at_least_one_candidate': sum(row['generation_state'] == 'failed' and row['candidate_count'] > 0 for row in rows),
           'method': 'Count nonempty provisionally confirmed extracted facts with cited source IDs and no extracted relationship endpoint. No question or reference was generated or checked.',
           'limitations': ['Post-outcome diagnosis on previously observed related synthetic histories; not validation.',
                           'Simulated confirmation is not human ground truth; source IDs do not prove support, uniqueness, persistence or answerability.',
                           'Absence of an extracted relationship does not establish absence of conflict or update.',
                           'Candidate counts are not valid-question counts and do not establish coverage of any ability.'],
           'rows': rows}
    (RUN / 'candidate-inventory-diagnostic.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print('No-suite histories with at least one provisional cited fact:', out['no_suite_histories_with_at_least_one_candidate'], '/ 12')

if __name__ == '__main__':
    main()
