"""Post-discovery offline quality-guard replay; no new generated questions."""
import collections
import hashlib
import json
from pathlib import Path
from app.schemas import Memory, MemoryStatus, TestCase
from app.test_generator.quality import RuleBasedTestQualityValidator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/ac2-astra-diverse-product-20261101-v1'
review=json.loads((OUT/'question-ai-reviewer-1-completed.json').read_text())
labels={x['test_id']:x for x in review['items']}
results=[]
for path in sorted(OUT.glob('prospective-*.json')):
    entry=json.loads(path.read_text())
    if entry['status']!='completed':continue
    memories=[Memory.model_validate(x).model_copy(update={'status':MemoryStatus.CONFIRMED}) for x in next(x['response'] for x in entry['requests'] if x['path'].endswith('/extract'))]
    tests=next(x['response'] for x in entry['requests'] if x['path'].endswith('/generate-tests'))
    for raw in tests:
        test=TestCase.model_validate(raw);assessment=RuleBasedTestQualityValidator().validate(test,memories)
        item=labels[test.test_id];verdict='invalid' if any(item[k]=='invalid' for k in ('source_grounding','question_executability','reference_answer_validity')) else 'uncertain' if any(item[k]=='uncertain' for k in ('source_grounding','question_executability','reference_answer_validity')) else 'valid'
        results.append({'history_id':entry['history_id'],'test_id':test.test_id,'dimension':test.dimension.value,
                        'prior_quality':raw['quality_status'],'candidate_quality':assessment.quality_status.value,
                        'reason':assessment.reason,'reference':verdict})
if len(results)!=len(labels):raise SystemExit('Saved question/review mismatch')
matrix=collections.Counter((x['reference'],x['candidate_quality']) for x in results)
payload={'format':'ac2-conflict-guard-development-replay-v1','validator_version':RuleBasedTestQualityValidator.VERSION,
 'review_sha256':hashlib.sha256((OUT/'question-ai-reviewer-1-completed.json').read_bytes()).hexdigest(),
 'human_confirmation_sha256':hashlib.sha256((OUT/'human-confirmation.json').read_bytes()).hexdigest(),
 'matrix':[{'reference':a,'candidate_quality':b,'count':n} for (a,b),n in sorted(matrix.items())],
 'results':results,'scope':'Offline replay on the same questions that motivated this rule; no model rerun and not independent validation.',
 'limitations':['The rule detects only recorded conflict relationships; missing or wrongly typed edges remain a risk.',
 'Seven related template histories and user-reported human checks of AI-assisted reviews do not establish population performance.',
 'Rejecting an unsafe question is not proof that the application can generate a replacement.']}
(OUT/'conflict-guard-development-replay.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(payload['matrix']))
