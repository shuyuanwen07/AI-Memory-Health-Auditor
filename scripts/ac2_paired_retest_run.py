"""Local, no-model paired generation on a reviewed and frozen AC2 source.

Callers must persist the predeclared protocol before invoking this function.
No app database is written and no human labels are created.
"""
import io
import inspect
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AuditRun, Memory, MemoryRelationship
from app.services.formal_freeze import formal_runtime_signature
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator
from scripts.ac2_paired_retest_freeze import BASELINE_SOURCE_SHA, frozen_digest, prepare, sha


def run(frozen, source, plan, reviews, archive, candidate, validator):
    current = formal_runtime_signature()['source_sha256']
    expected = prepare(source, plan, reviews, archive, candidate, validator, current)
    # Freeze timestamp is fixed by the original authoring step; every other
    # field is reconstructed from the current input and verified.
    expected['frozen_at_utc'] = frozen.get('frozen_at_utc')
    if expected != frozen or not frozen.get('frozen_at_utc'):
        raise ValueError('Frozen source, review or runtime changed.')
    if sha(Path(inspect.getfile(RuleBasedTestGenerator)).read_bytes()) != sha(candidate):
        raise ValueError('Candidate is not the running product generator.')
    if sha(Path(inspect.getfile(RuleBasedTestQualityValidator)).read_bytes()) != sha(validator):
        raise ValueError('Quality validator is not the running product version.')
    import json
    suite, facts = json.loads(source), json.loads(plan)['histories']
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        baseline_source = bundle.read('app/test_generator/rule_based.py')
    if sha(baseline_source) != BASELINE_SOURCE_SHA:
        raise ValueError('Baseline source changed.')
    namespace = {'__name__':'ac2_archived_baseline'}
    exec(compile(baseline_source, '<verified-v35>', 'exec'), namespace)
    baseline = namespace['RuleBasedTestGenerator']
    if baseline.VERSION != 'rule-based-v35' or RuleBasedTestGenerator.VERSION != 'rule-based-v36':
        raise ValueError('Unexpected generator versions.')
    output = {}
    for condition, generator in [('baseline',baseline),('candidate',RuleBasedTestGenerator)]:
        histories = []
        for case in suite['cases']:
            hid=case['history_id']; reference=facts[hid]; memories=[]
            for fact in reference['facts']:
                relations=[MemoryRelationship(type=e['relationship_type'],target_memory_id=e['target_memory_id'],
                    evidence_message_ids=e['evidence_message_ids']) for e in reference['relationships'] if e['memory_id']==fact['memory_id']]
                memories.append(Memory(memory_id=fact['memory_id'],conversation_id=hid,canonical_value=fact['canonical_value'],
                    status='confirmed',source_message_ids=[fact['source_message_id']],relationships=relations))
            audit=AuditRun(run_id='AC2-'+hid,conversation_id=hid,status='CREATED',target_configuration='strong',
                provider='rule_based',model='rule-based-v2',temperature=0,random_seed=42,test_budget=4,
                prompt_template_version='rule-based-v4',created_at=datetime(2000,1,1,tzinfo=timezone.utc))
            try:
                tests=generator().generate(memories,audit)
            except Exception as exc:
                histories.append({'history_id':hid,'status':'error','error_type':type(exc).__name__,
                                  'generated_count':0,'missing_slots':4,'tests':[]})
                continue
            # Generation and validation are separate outcomes. A validator
            # exception must never erase a question that was actually produced.
            quality=RuleBasedTestQualityValidator()
            rows=[]
            for test in tests:
                serialized=test.model_dump(mode='json')
                try:
                    assessment=quality.validate(test,memories).model_dump(mode='json')
                except Exception as exc:
                    assessment={'quality_status':'pending','validation_error_type':type(exc).__name__}
                rows.append({'test':serialized,'quality_assessment':assessment})
            try:
                suite_problem=quality.validate_suite(tests)
                suite_error=None
            except Exception as exc:
                suite_problem=None
                suite_error=type(exc).__name__
            histories.append({'history_id':hid,'status':'completed','suite_problem':suite_problem,
                              'suite_validation_error_type':suite_error,
                              'generated_count':len(rows),'missing_slots':max(0,4-len(rows)),'tests':rows})
        output[condition]=histories
    return {'format':'ac2-paired-generation-output-v1','source_sha256':sha(source),
            'frozen_protocol_sha256':frozen_digest(frozen),
            'frozen_at_utc':frozen['frozen_at_utc'],'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'baseline_sha256':sha(baseline_source),'candidate_sha256':sha(candidate),
            'conditions':output,'model_called':False,'database_written':False,
            'limitations':'Same current environment for both source versions. Human review of generated questions remains required.'}
