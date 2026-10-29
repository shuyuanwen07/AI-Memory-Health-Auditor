"""Source-bind and compare three AI-only development review passes."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/ac3-generated/ac2-full-source-critic-development-20261030-v1'
PACKET = ROOT / 'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/blind-review'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    protocol_path, ledger_path = RUN/'protocol.json', RUN/'ledger.json'
    packet_path = PACKET/'reviewer-1.json'
    protocol, ledger, packet = (json.loads(p.read_text()) for p in (protocol_path, ledger_path, packet_path))
    assert ledger['protocol_sha256'] == sha(protocol_path) and protocol['packet_sha256'] == sha(packet_path)
    assert protocol['script_sha256'] == sha(ROOT/'scripts/run_ac2_full_source_critic_development_20261030.py')
    reviews = [json.loads((PACKET/f'ai-review-{i}.json').read_text()) for i in (1, 2)]
    ids = [x['review_item_id'] for x in packet['items']]
    assert len(ids) == len(set(ids)) == 24 == len(ledger['rows'])
    assert ids == protocol['item_ids'] == [row['review_item_id'] for row in ledger['rows']]
    rows = []
    for item, result, first, second in zip(packet['items'], ledger['rows'], reviews[0]['items'], reviews[1]['items']):
        assert result['state'] == 'returned' and item['review_item_id'] == first['review_item_id'] == second['review_item_id']
        assert all({k:v for k,v in item.items() if k != 'review'} == {k:v for k,v in other.items() if k != 'review'} for other in (first,second))
        material = {k:item[k] for k in ('source_messages','question','reference_answer')}
        prompt = json.dumps(material, ensure_ascii=False, sort_keys=True)
        assert result['input_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
        x, y = first['review']['overall'], second['review']['overall']
        prior = x if x == y and x in ('valid','invalid') else 'unresolved'
        rows.append({'review_item_id':item['review_item_id'], 'prior_ai_1':x, 'prior_ai_2':y,
                     'prior_ai_consensus':prior, 'source_complete_ai':result['review']['overall']})
    counts = Counter((r['prior_ai_consensus'],r['source_complete_ai']) for r in rows)
    costs = [(r.get('execution') or {}).get('reported_cost_credits') for r in ledger['rows']]
    out = {'protocol_sha256':sha(protocol_path),'ledger_sha256':sha(ledger_path),
           'previous_reviews_sha256':[sha(PACKET/f'ai-review-{i}.json') for i in (1,2)],
           'counts':[{'previous_ai_consensus':k[0], 'source_complete_ai':k[1], 'n':v} for k,v in sorted(counts.items())],
           'items':rows,'provider_reported_cost_sum':sum(x for x in costs if isinstance(x,(int,float))),
           'requests_with_reported_cost':sum(isinstance(x,(int,float)) for x in costs),
           'limitations':'Post-outcome, same 24 related synthetic questions. All labels are AI suggestions; human review is pending. Prior AI passes also saw the complete source. Agreement with AI is not accuracy or proof of independent validation. Provider-reported cost is not a verified invoice; missing or failed-attempt costs may be unknown.'}
    (RUN/'analysis.json').write_text(json.dumps(out, indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ('counts','provider_reported_cost_sum','requests_with_reported_cost')},indent=2))


if __name__ == '__main__': main()
