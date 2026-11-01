"""Replay the frozen rule-v65 archive with complete saved response metadata.

This companion fixes only schema construction in the original runner: its
offline TargetResponse constructor omitted the required created_at field.
It does not modify the archived evaluator, new target answers or paid judge.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ac3_frozen_collector',ROOT/'scripts/ac3_astra_max_retest_20261101.py')
collector=importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
collector.check()
folder=Path(tempfile.mkdtemp(prefix='ac3-rule-v65-replay-'))
with ZipFile(collector.BASELINE) as archive:archive.extractall(folder)
sys.path.insert(0,str(folder))
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import TestCase,TargetResponse,Memory

assert RuleBasedBehaviourEvaluator.VERSION=='rule-based-v65'
records=[]
for item in collector.read(collector.OUT/'private-scorer-inputs.json')['items']:
    question=TestCase.model_validate(item['test'])
    # The old schema predates MAX, while its evaluator never reads effort.
    # Validate all remaining actual completion fields, then retain the actual
    # effort value with a non-validating model copy. No model output is changed.
    payload=dict(item['response'])
    metadata=dict(payload['execution_metadata'])
    actual_effort=metadata.get('requested_reasoning_effort')
    metadata['requested_reasoning_effort']=None
    payload['execution_metadata']=metadata
    response=TargetResponse.model_validate(payload)
    response=response.model_copy(update={'execution_metadata':response.execution_metadata.model_copy(update={'requested_reasoning_effort':actual_effort})})
    memories=[Memory.model_validate(m) for m in item['memories']]
    records.append(RuleBasedBehaviourEvaluator().evaluate(question,response,memories).model_dump(mode='json'))
print(json.dumps({'evaluator':'rule-based-v65','snapshot_sha256':collector.sha(collector.BASELINE),
    'input_sha256':collector.sha(collector.OUT/'private-scorer-inputs.json'),
    'implementation_note':'Original runner omitted required response.created_at. The old schema also predates MAX; all supported metadata are validated and the actual MAX value is retained using model_copy. The archived evaluator reads completion_status and memory_input, never effort. Answer text, source facts and evaluator logic are unchanged; no model calls.',
    'items':records},ensure_ascii=False))
