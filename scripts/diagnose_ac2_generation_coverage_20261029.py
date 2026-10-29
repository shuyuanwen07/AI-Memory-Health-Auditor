"""Post-hoc diagnosis of a frozen feasibility study; never an acceptance test."""
import collections, hashlib, json
from pathlib import Path
from app.schemas import AuditRun, Memory
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'output/proposal-delivery/ac2-v4-prospective-product-20261029-v1/ledger.json'
out=(Path('/ac3-results') if Path('/ac3-results').is_dir() else ROOT/'output/ac3-generated')/'ac2-generation-coverage-diagnosis-20261029.json'
ledger=json.loads(source.read_bytes()); validator=RuleBasedTestQualityValidator(); records=[]
for h in ledger['histories']:
    memories=[Memory.model_validate(m) for m in h['provisional_memories']]
    audit=next(x['response'] for x in h['requests'] if x['path']=='/audits' and x['status']=='returned')
    # Reveal all proposed candidates only for this retrospective diagnostic;
    # no modified suite is saved or used for target execution.
    run=AuditRun.model_validate(audit).model_copy(update={'test_budget':100})
    tests=RuleBasedTestGenerator().generate(memories,run)
    checks=[validator.validate(t,memories) for t in tests]
    statuses=collections.Counter(c.quality_status.value for c in checks)
    reasons=collections.Counter(c.reason for c in checks if c.quality_status.value=='rejected')
    records.append({'history_id':h['history_id'],'original_status':h['status'],
      'candidate_count':len(tests),'candidate_quality':dict(statuses),'rejected_reasons':dict(reasons),
      'hypothetical_up_to_four_not_rejected':min(4,len(tests)-statuses['rejected'])})
result={'format':'ac2-generation-coverage-diagnosis-v1','input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'scope':'Retrospective local rule-generator diagnostic after observing failures; no product changes, new labels, target execution or independent validation.',
 'histories':len(records),'histories_with_four_nonrejected_candidates':sum(x['hypothetical_up_to_four_not_rejected']==4 for x in records),
 'hypothetical_nonrejected_candidates_up_to_four':sum(x['hypothetical_up_to_four_not_rejected'] for x in records),
 'limitations':['Per-question checks alone do not certify semantic validity or whole-suite compatibility.',
  'Using larger local diagnostic budget changes candidate inspection, not the frozen original result.',
  'These observed histories are development examples and cannot serve as an independent retest after tuning.'],
 'histories_detail':records}
with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('histories','histories_with_four_nonrejected_candidates','hypothetical_nonrejected_candidates_up_to_four')}))
