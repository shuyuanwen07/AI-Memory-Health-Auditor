"""Run B's frozen deterministic engineering pipeline, without cloud or database writes."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.schemas import AuditRun, Conversation, MemoryStrategy, TargetConfiguration, TargetProvider, AuditStatus
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.target_ai.rule_based import RuleBasedTargetAIConnector
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.metrics.service import MetricsService

BASELINE = 'a241e3d28ee58bdd5a66bfd724f8aa02ab315bb9'
FROZEN = ['backend/app/extraction/rule_based.py', 'backend/app/test_generator/rule_based.py',
          'backend/app/target_ai/rule_based.py', 'backend/app/evaluator/rule_based.py']

def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/local/owner-c-heldout-v1')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; preserve previous frozen runs and choose a new path.')
    for name in FROZEN:
        expected = subprocess.check_output(['git', 'show', f'{BASELINE}:{name}'], cwd=ROOT)
        if (ROOT/name).read_bytes() != expected:
            parser.error(f'Frozen component changed: {name}')
    source = ROOT/'handoff/owner-a-custodian/heldout/source_conversations.json'
    conversations = json.loads(source.read_text())['conversations']
    args.output.mkdir(parents=True)
    config = {'baseline_commit': BASELINE, 'provider': 'rule_based', 'model': 'rule-based-target-ai',
              'target_configuration': 'weak', 'memory_strategy': 'weak_first_hit', 'temperature': 0,
              'random_seed': 7, 'test_budget': 20, 'prompt_template_version': 'rule-based-v1',
              'generator_version': 'rule-based-v4', 'budget_origin': 'C pre-run engineering choice; B did not specify a final budget',
              'scope': 'Source-only extracted-memory engineering pipeline matching B investigation style; not the persisted web-app target adapter or a formal human-gated experiment',
              'reference_origin': 'Expected behaviour generated from extractor outputs, not human gold labels. Actual-output human review remains pending.',
              'source_sha256': digest(source), 'component_sha256': {name: digest(ROOT/name) for name in FROZEN}}
    dump(args.output/'configuration.json', config)
    suites=[]
    for raw in conversations:
        conversation = Conversation(conversation_id=raw['conversation_id'], authorised=True,
                                    created_at=raw['messages'][0]['timestamp'], messages=raw['messages'])
        memories = RuleBasedMemoryExtractor().extract(conversation)
        audit = AuditRun(run_id=f'C-V1-{conversation.conversation_id}', conversation_id=conversation.conversation_id,
                         status=AuditStatus.CREATED, target_configuration=TargetConfiguration.WEAK,
                         provider=TargetProvider.RULE_BASED, model=config['model'], temperature=0,
                         random_seed=7, test_budget=20, prompt_template_version=config['prompt_template_version'],
                         memory_strategy=MemoryStrategy.WEAK_FIRST_HIT, created_at=datetime.now(timezone.utc))
        tests = RuleBasedTestGenerator().generate(memories, audit)
        # The frozen generator's local IDs repeat between scenarios. Namespace them for paired review.
        tests = [t.model_copy(update={'test_id':f'{conversation.conversation_id}-{t.test_id}'}) for t in tests]
        assert len({t.test_id for t in tests}) == len(tests)
        suites.append({'audit':audit.model_dump(mode='json'), 'memories':[m.model_dump(mode='json') for m in memories],
                       'tests':[t.model_dump(mode='json') for t in tests]})
    dump(args.output/'frozen_suite.json', suites)
    freeze = {'frozen_before_execution': True, 'frozen_at': datetime.now(timezone.utc).isoformat(),
              'suite_sha256':digest(args.output/'frozen_suite.json'), 'configuration_sha256':digest(args.output/'configuration.json'),
              'scenarios':len(suites), 'tests':sum(len(s['tests']) for s in suites)}
    dump(args.output/'freeze_manifest.json', freeze)
    assert digest(args.output/'frozen_suite.json') == freeze['suite_sha256']
    results=[]; review=[]; all_evaluations=[]; dimensions={}
    for suite in suites:
        audit=AuditRun.model_validate(suite['audit'])
        from app.schemas import Memory, TestCase
        memories=[Memory.model_validate(m) for m in suite['memories']]
        tests=[TestCase.model_validate(t) for t in suite['tests']]
        for test in tests:
            # Remove evaluator fields before connector invocation. Private context is derived only from sources.
            private=test.model_copy(update={'expected_behavior':'', 'target_memory_context':test.target_memory_context[:1]})
            response=RuleBasedTargetAIConnector().execute(private,audit)
            evaluation=RuleBasedBehaviourEvaluator().evaluate(test,response,memories)
            all_evaluations.append(evaluation);dimensions[test.test_id]=test.dimension
            results.append({'conversation_id':audit.conversation_id, 'test':test.model_dump(mode='json'),
                            'response':response.model_dump(mode='json'), 'evaluation':evaluation.model_dump(mode='json')})
            review.append({'conversation_id':audit.conversation_id,'test_id':test.test_id,'response_id':response.response_id,
                           'prompt':test.prompt,'response_text':response.response_text,'human_passed':'','human_failure_dimension':'',
                           'source_message_ids':'','note':''})
    dump(args.output/'results.json',results)
    score, dimension_scores=MetricsService().calculate(all_evaluations,dimensions)
    summary={'scenarios':len(suites),'tests':len(results),'passed':sum(e.passed for e in all_evaluations),
             'failed':sum(not e.passed for e in all_evaluations),'overall_score':score,
             'dimension_scores':[d.model_dump(mode='json') for d in dimension_scores],
             'interpretation':'Automated engineering scores only; not validated against human labels of actual responses.',
             'empty_suite_scenarios':[s['audit']['conversation_id'] for s in suites if not s['tests']]}
    dump(args.output/'summary.json',summary)
    for name in ['actual_response_review_1.csv','actual_response_review_2.csv']:
        with (args.output/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(review[0]) if review else ['test_id','human_passed'])
            w.writeheader();w.writerows(review)
    assert len(results)==freeze['tests'] and len({r['test']['test_id'] for r in results})==len(results)
    assert digest(args.output/'frozen_suite.json')==freeze['suite_sha256']
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
