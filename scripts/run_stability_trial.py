"""One isolated predeclared target trial, using the existing pinned-rubric pilot.

Identity/model mismatch is retained and stops subsequent dispatch. Target-only
identity evidence has an explicit separate per-trial budget, never a fallback.
"""
from stability_grading_budget import trial_grader_cap, preflight_grader_budget, grader_budget_matches
from stability_auxiliary import agent_identity_matches, validate_final_identity_binding
from stability_configuration import preflight_all_roles, role_settings, answer_validation_enabled
from stability_answer_validation import ROLE as VALIDATION_ROLE, OBSERVATIONS as VALIDATION_OBSERVATIONS, DRAFT as PRIMARY_DRAFT, read_observation as read_validation_observation, validate_binding as validate_answer_binding
from stability_request_contracts import required as wire_required, WireObserver, validate_events
from contextlib import nullcontext

import argparse
from functools import wraps
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import runpy
import sys
import tempfile


def build_memory_preparation_observation(store, run_id, conversation, *, status, exception_type=None):
    """Read actual private store state without flushing, committing or invoking providers."""
    from sqlalchemy import select, literal_column
    from app.models import TargetAgentMemoryModel, TargetAgentMemoryEventModel
    errors = []
    records, events = [], []
    with store.db.no_autoflush:
        for model, component in ((TargetAgentMemoryModel, 'records'), (TargetAgentMemoryEventModel, 'events')):
            rows = []
            try:
                statement = select(model).where(model.run_id == run_id)
                if component == 'records':
                    statement = statement.order_by(model.write_order, model.id)
                elif store.db.get_bind().dialect.name == 'sqlite':
                    statement = statement.order_by(literal_column('rowid'))
                else:
                    statement = statement.order_by(model.created_at, model.id)
                rows = list(store.db.scalars(statement).all())
            except Exception as exc:
                errors.append({'component': component, 'error_type': type(exc).__name__})
            # On an interrupted ingestion there may also be unflushed objects.
            for item in list(store.db.identity_map.values()) + list(store.db.new):
                if isinstance(item, model) and item.run_id == run_id and all(item is not row for row in rows):
                    rows.append(item)
            if component == 'records':
                rows.sort(key=lambda row: (row.write_order, row.id or ''))
            for row in rows:
                try:
                    schema = store._record_schema(row) if component == 'records' else store._event_schema(row)
                    (records if component == 'records' else events).append(schema.model_dump(mode='json'))
                except Exception as exc:
                    errors.append({'component': component + '_schema', 'error_type': type(exc).__name__})
    policy = store.maintenance_policy
    return {
        'version': 'private-memory-preparation-observation-v1',
        'run_id': run_id, 'conversation_id': conversation.conversation_id,
        'status': status, 'exception_type': exception_type,
        'profile': store.profile.model_dump(mode='json'),
        'capacity': store.max_active_records,
        'maintenance_policy': getattr(policy, 'value', policy),
        'writer_version': store.writer_version,
        'records': records, 'events': events,
        'snapshot_complete': not errors, 'snapshot_errors': errors,
    }


def _validate_memory_preparation(path, protocol):
    from stability_memory_preparation import validate_private_memory_preparation_receipt
    receipt = json.loads(Path(path).read_text(encoding='utf-8'))
    return validate_private_memory_preparation_receipt(receipt, protocol=protocol, expected_observation_count=1)


def memory_preparation_wrapper(ingest, directory, *, required=False, protocol=None):
    """Capture the first actual ingestion before its caller can request any model."""
    path = Path(directory) / 'private-memory-preparation-receipts.json'
    captured_runs = set()

    @wraps(ingest)
    def observed(self, run_id, conversation, *args, **kwargs):
        if run_id in captured_runs:
            if required and not _validate_memory_preparation(path, protocol).get('passed', False):
                raise RuntimeError('First memory preparation evidence remains invalid.')
            return ingest(self, run_id, conversation, *args, **kwargs)
        captured_runs.add(run_id)
        status, error_type, original_error = 'failed', None, None
        capture_ok = False
        try:
            result = ingest(self, run_id, conversation, *args, **kwargs)
            status = 'completed'
            return result
        except BaseException as exc:
            original_error, error_type = exc, type(exc).__name__
            raise
        finally:
            temporary = None
            try:
                observation = build_memory_preparation_observation(self, run_id, conversation, status=status, exception_type=error_type)
                receipt = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
                    'version': 'private-memory-preparation-receipts-v1',
                    'provenance': 'actual_runtime_observation', 'reconstructed': False, 'observations': [],
                }
                receipt['observations'].append({'attempt': len(receipt['observations']) + 1,
                    'observed_at': datetime.now(timezone.utc).isoformat(), **observation})
                fd, temporary = tempfile.mkstemp(prefix='.memory-preparation-', dir=path.parent)
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path); temporary = None
                capture_ok = observation['snapshot_complete']
                if required and original_error is None:
                    validation = _validate_memory_preparation(path, protocol)
                    capture_ok = capture_ok and validation.get('passed', False)
            except Exception as exc:
                capture_ok = False
                try:
                    sys.stderr.write(json.dumps({'memory_preparation_write_failure': type(exc).__name__,
                        'ingest_status': status, 'ingest_exception_type': error_type}) + '\n')
                except Exception:
                    pass
            finally:
                if temporary is not None:
                    try: os.unlink(temporary)
                    except OSError: pass
            if required and original_error is None and not capture_ok:
                raise RuntimeError('Actual memory preparation evidence missing or incomplete.')
    return observed


def identity_observation_wrapper(analyze, directory, *, filename="identity-observation-receipts.json", version="private-identity-observation-receipts-v1"):
    """Persist actual analyzer observations, including local contract failures.

    This private sidecar is not an exported report or an offline reconstruction.
    Observing the existing call adds no model requests, retries or role attempts.
    """
    path = Path(directory) / filename

    @wraps(analyze)
    def observed(self, *args, **kwargs):
        status = 'failed'
        error_type = None
        self.last_observation = None  # Never attribute a prior call's observation.
        try:
            result = analyze(self, *args, **kwargs)
            status = 'completed'
            return result
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            temporary = None
            try:
                receipt = (json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
                    'version': version,
                    'provenance': 'actual_runtime_observation',
                    'reconstructed': False,
                    'observations': [],
                })
                receipt['observations'].append({
                    'attempt': len(receipt['observations']) + 1,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'analyzer_call_status': status,
                    'exception_type': error_type,
                    'last_observation': getattr(self, 'last_observation', None),
                    'last_execution': getattr(self, 'last_execution', None),
                })
                serialized = json.dumps(receipt, ensure_ascii=False, indent=2) + '\n'
                # Atomic replacement avoids a partial JSON file; mkstemp is 0600.
                fd, temporary = tempfile.mkstemp(prefix='.identity-observation-', dir=path.parent)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write(serialized)
                os.replace(temporary, path)
                temporary = None
            except Exception as exc:
                # Exception text may contain source/model content. Log only type.
                # Observation I/O must not replace the original pipeline failure.
                try:
                    sys.stderr.write(json.dumps({
                        'identity_observation_write_failure': type(exc).__name__,
                        'analyzer_call_status': status,
                        'analyzer_exception_type': error_type,
                    }) + '\n')
                except Exception:
                    pass
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass
    return observed


def _write_private_json(path,value):
    fd,temporary=tempfile.mkstemp(prefix='.private-stage-',dir=Path(path).parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        os.unlink(temporary)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--directory',type=Path,required=True);args=ap.parse_args();directory=args.directory.resolve()
    protocol=json.loads((directory/'pilot-protocol.json').read_text())
    assert len(protocol['strategies'])==1 and protocol['model']=='openai/gpt-6-luna' and protocol['provider']=='openrouter'
    if (directory/'pilot-report.json').exists():raise ValueError('Never overwrite an existing attempt.')
    os.environ['DATABASE_URL']='sqlite://';sys.path.insert(0,str(Path('/app') if Path('/app/app').exists() else Path(__file__).resolve().parents[1]/'backend'))
    from app.target_ai.providers import HttpTargetAIConnector
    from app.extraction.llm import PipelineLLMClient
    from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
    from app.memory_agent.store import SqlTargetMemoryStore
    memory_preparation_required = protocol.get('memory_preparation_receipt_required') is True
    grader_cap=trial_grader_cap(protocol)
    preflight=preflight_grader_budget(grader_cap)
    (directory/'grading-budget-preflight.json').write_text(json.dumps(preflight,indent=2)+'\n')
    assert preflight['passed'],'Pipeline environment would lower the frozen grader cap.'
    all_roles=preflight_all_roles(protocol)
    (directory/'all-role-budget-preflight.json').write_text(json.dumps(all_roles,indent=2)+'\n')
    assert all_roles['passed'],'Pipeline environment would lower a preregistered role cap.'
    wire=WireObserver(directory,protocol) if wire_required(protocol) else None
    expected=protocol['model'];extra=[];evidence_calls=0;validation_calls=0;assessment_role=protocol.get('assessment_role','benchmark_pilot_assessment')
    def save():
        (directory/'agent-execution-receipts.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2)+'\n')
    def mismatch(kind,value):
        (directory/'identity-mismatch-receipt.json').write_text(json.dumps({'kind':kind,'actual':value,'at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2)+'\n')
        raise RuntimeError('Actual provider/model differs from the frozen Luna protocol; no fallback permitted.')
    original_provider=HttpTargetAIConnector._execute_provider
    def observe_provider(self,audit,test,instructions,credential):
        if memory_preparation_required and not _validate_memory_preparation(directory/'private-memory-preparation-receipts.json',protocol).get('passed',False):
            raise RuntimeError('Actual memory preparation evidence missing or inconsistent.')
        from app.target_ai.rule_based import memory_input_evidence,target_question_input
        evidence=memory_input_evidence(test,audit.target_configuration,instructions).model_dump(mode='json')
        receipt={'memory_input':evidence,'instruction_sha256':hashlib.sha256(instructions.encode()).hexdigest(),'question_sha256':hashlib.sha256(target_question_input(test.prompt).encode()).hexdigest(),'combined_input_sha256':hashlib.sha256(json.dumps({'instructions':instructions,'question':target_question_input(test.prompt)},sort_keys=True).encode()).hexdigest(),'requested_output_token_limit':audit.target_memory_profile.output_token_limit,'identity_advisory_sha256':evidence.get('identity_advisory_sha256')}
        if 'identity_failure_receipt_sha256' in evidence:receipt['identity_failure_receipt_sha256']=evidence.get('identity_failure_receipt_sha256')
        (directory/'actual-input-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        if wire is not None:
            wire.set_target_plan(question=test.prompt,selected_record_count=evidence['record_count'])
            wire.prepare('target_answer',instructions=instructions,prompt=target_question_input(test.prompt))
        return original_provider(self,audit,test,instructions,credential)
    HttpTargetAIConnector._execute_provider=observe_provider
    original_target=HttpTargetAIConnector.execute
    def target(self,test,audit):
        response=original_target(self,test,audit);meta=response.execution_metadata.model_dump(mode='json')
        if answer_validation_enabled(protocol.get('target_memory_profile',{})):
            path=directory/PRIMARY_DRAFT
            if path.exists():raise ValueError('Never overwrite primary draft evidence.')
            _write_private_json(path,response.model_dump(mode='json'))
        if response.model!=expected or meta.get('reported_model')!=expected or meta.get('response_source')!='openrouter':
            mismatch('target',response.model_dump(mode='json'))
        if meta.get('requested_output_token_limit')!=protocol['output_token_limit']:mismatch('target_budget_mismatch',meta)
        memory_input=meta.get('memory_input') or {}
        observation_path=directory/'identity-observation-receipts.json'
        observations=json.loads(observation_path.read_text()).get('observations',[]) if observation_path.exists() else []
        observation=observations[-1].get('last_observation') if observations else None
        binding_error=validate_final_identity_binding(test=test,audit=audit,memory_input=memory_input,protocol=protocol,evidence_calls=evidence_calls,observation=observation)
        if binding_error:mismatch(binding_error,meta)
        return response
    original_agent=PipelineLLMClient.complete_json
    def agent(self,**kwargs):
        nonlocal evidence_calls,validation_calls
        role=kwargs.get('agent_role')
        if role=='target_identity_evidence':
            evidence_calls+=1
            if (protocol['strategies']!=['strong_rule_based'] or protocol['target_memory_profile'].get('identity_analysis','off')!='evidence_links' or evidence_calls>protocol['maximum_extra_identity_evidence_calls']):
                mismatch('unbudgeted_evidence_stage',{'agent_role':role,'logical_calls':evidence_calls})
        elif role==VALIDATION_ROLE:
            validation_calls+=1
            if (not answer_validation_enabled(protocol.get('target_memory_profile',{})) or validation_calls>protocol.get('maximum_extra_answer_validation_calls',0)
                    or kwargs.get('max_output_tokens')!=role_settings(protocol,role)['output_token_limit']):
                mismatch('unbudgeted_answer_validation_stage',{'agent_role':role,'logical_calls':validation_calls})
        elif role==assessment_role and kwargs.get('max_output_tokens')!=grader_cap:
            mismatch('grader_protocol_budget_mismatch',{'expected_grader_cap':grader_cap,'actual_call_cap':kwargs.get('max_output_tokens')})
        elif role!=assessment_role:
            mismatch('unbudgeted_agent_role',{'agent_role':role})
        if wire is not None:
            controls=role_settings(protocol,role)
            if kwargs.get('reasoning_effort')!=controls['reasoning_effort']:mismatch('agent_reasoning_mismatch',{'role':role})
            wire.prepare(role,instructions=kwargs['instructions'],prompt=kwargs['prompt'],schema_name=kwargs['schema_name'],schema=kwargs['schema'])
        result=None
        try:
            result=original_agent(self,**kwargs)
            execution=dict(self.last_execution or {})
            extra.append({'agent_role':role,'execution':execution,'evidence_payload':result if role=='target_identity_evidence' else None,'result':result,'actual_instruction_sha256':hashlib.sha256(kwargs['instructions'].encode()).hexdigest(),'actual_prompt_sha256':hashlib.sha256(kwargs['prompt'].encode()).hexdigest(),'requested_max_output_tokens':kwargs.get('max_output_tokens')});save()
            if not agent_identity_matches(execution,expected,role,kwargs.get('max_output_tokens')):mismatch('agent',extra[-1])
            if role==assessment_role and not grader_budget_matches(protocol,execution):mismatch('grader_execution_budget_mismatch',execution)
            if execution.get('requested_output_token_limit')!=kwargs.get('max_output_tokens'):mismatch('agent_budget_mismatch',extra[-1])
            return result
        except Exception as exc:
            if not extra or extra[-1].get('execution')!=dict(self.last_execution or {}):
                extra.append({'agent_role':role,'execution':dict(self.last_execution or {}),'status':'failed','exception_type':type(exc).__name__,'evidence_payload':None,'actual_instruction_sha256':hashlib.sha256(kwargs['instructions'].encode()).hexdigest(),'actual_prompt_sha256':hashlib.sha256(kwargs['prompt'].encode()).hexdigest(),'requested_max_output_tokens':kwargs.get('max_output_tokens')});save()
            if not (directory/'identity-mismatch-receipt.json').exists() and not agent_identity_matches(dict(self.last_execution or {}),expected,role,kwargs.get('max_output_tokens')):
                mismatch('failed_agent_identity_or_budget_mismatch',extra[-1])
            raise
    HttpTargetAIConnector.execute=target;PipelineLLMClient.complete_json=agent
    TargetIdentityEvidenceAnalyzer.analyze=identity_observation_wrapper(TargetIdentityEvidenceAnalyzer.analyze,directory)
    validation_class=None;original_validation=None
    if answer_validation_enabled(protocol.get('target_memory_profile',{})):
        from app.memory_agent.answer_validation import TargetAnswerValidator
        validation_class=TargetAnswerValidator;original_validation=validation_class.validate
        validation_class.validate=identity_observation_wrapper(original_validation,directory,filename=VALIDATION_OBSERVATIONS,version='private-answer-validation-observation-receipts-v1')
    script='run_stability_guard_trial.py' if protocol.get('assessment_kind')=='synthetic_source_safety' else 'run_longmemeval_pilot.py'
    sys.argv=[str(Path(__file__).with_name(script)),'--directory',str(directory)]
    if wire is not None:
        from app.target_ai.request_contracts import observe_request_contracts
        context=observe_request_contracts(wire)
    else:context=nullcontext()
    original_ingest=SqlTargetMemoryStore.ingest
    SqlTargetMemoryStore.ingest=memory_preparation_wrapper(original_ingest,directory,required=memory_preparation_required,protocol=protocol)
    try:
        with context:runpy.run_path(str(Path(__file__).with_name(script)),run_name='__main__')
    finally:
        SqlTargetMemoryStore.ingest=original_ingest
        if validation_class is not None:validation_class.validate=original_validation
        pending_error=sys.exc_info()[1]
        preserve_failure=pending_error is not None and not (isinstance(pending_error,SystemExit) and pending_error.code in (None,0))
        if wire is not None:
            proof={'version':'actual-wire-validation-v1','status':'failed','roles':{},'error_type':None}
            try:
                if memory_preparation_required:
                    proof['memory_preparation']=_validate_memory_preparation(directory/'private-memory-preparation-receipts.json',protocol)
                    if not proof['memory_preparation'].get('passed',False):raise ValueError('Memory preparation evidence incomplete.')
                report=json.loads((directory/'pilot-report.json').read_text()) if (directory/'pilot-report.json').exists() else {}
                if answer_validation_enabled(protocol.get('target_memory_profile',{})):
                    targets=report.get('target_call_receipts',[])
                    if len(targets)!=1 or targets[0].get('status')!='completed':raise ValueError('Missing final validated target response.')
                    proof['answer_validation']=validate_answer_binding(protocol,observation=read_validation_observation(directory),draft=json.loads((directory/PRIMARY_DRAFT).read_text()),final=targets[0]['response'],events=extra)
                proof['required_roles']=sorted(wire.required_roles)
                proof['actual_roles']=sorted({event.get('role') for event in wire.events})
                proof['target_plan']=wire.target_plan
                if set(wire.expected)!=wire.required_roles or wire.target_plan is None:raise ValueError('Required roles were not all planned and attempted.')
                if set(proof['actual_roles'])!=wire.required_roles:raise ValueError('Required HTTP roles missing or extra.')
                for role,contract in wire.expected.items():
                    if role=='target_answer':
                        targets=report.get('target_call_receipts',[])
                        if len(targets)!=1:raise ValueError('Missing actual target execution meter.')
                        execution=(targets[0].get('response') or {}).get('execution_metadata') or targets[0].get('execution')
                    else:
                        matching=[row for row in extra if row.get('agent_role')==role]
                        if len(matching)!=1:raise ValueError('Missing or extra role execution meter.')
                        execution=matching[0]['execution']
                    proof['roles'][role]=validate_events(protocol,wire.events,role,contract,execution)
                if not proof['roles']:raise ValueError('No actual HTTP attempts captured.')
                proof['status']='passed'
            except Exception as exc:proof['error_type']=type(exc).__name__
            proof['protocol_sha256']=hashlib.sha256((directory/'pilot-protocol.json').read_bytes()).hexdigest()
            proof['evidence_sha256']={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('actual-wire-attempt-receipts.json','pilot-report.json','agent-execution-receipts.json','private-memory-preparation-receipts.json',VALIDATION_OBSERVATIONS,PRIMARY_DRAFT) if (directory/name).exists()}
            (directory/'actual-wire-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
            if proof['status']!='passed' and not preserve_failure:raise RuntimeError('Actual wire request evidence incomplete or inconsistent.')
        elif memory_preparation_required:
            try:
                if not _validate_memory_preparation(directory/'private-memory-preparation-receipts.json',protocol).get('passed',False):raise ValueError('Incomplete memory preparation receipt.')
            except Exception:
                if not preserve_failure:raise RuntimeError('Actual memory preparation evidence incomplete or inconsistent.')

if __name__=='__main__':main()
