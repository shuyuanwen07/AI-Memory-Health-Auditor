"""Durable operation history; failed attempts must not vanish on retry."""
from copy import deepcopy
from uuid import uuid4
from app.test_generator.observations import observe_candidates


def begin_generation_observation(db, run):
    db.refresh(run)
    metadata=deepcopy(run.reproducibility_metadata or {})
    history=list(metadata.get('generation_observations') or [])
    operation_id=uuid4().hex
    history.append({'operation_id':operation_id,'version':'generator-observation-v1','status':'started',
        'attempts':[],'saved_suite':False,'scope':'Operation started; request dispatch and candidate data remain unknown until returned.'})
    metadata['generation_observations']=history
    run.reproducibility_metadata=metadata
    db.commit()
    return operation_id


def save_generation_observation(db, run, generator, memories, generated=None, failed=False, operation_id=None):
    observed=getattr(generator,'last_observation',None)
    if observed is None:
        observed={'version':'generator-observation-v1','status':'failed' if failed else 'completed','attempts':[],
            'scope':'Local generator output checks; no upstream invocation or billing count inferred.'}
        if generated is not None:
            observed['attempts']=[{**observe_candidates(generated,memories),'status':'returned',
                'suite_contract_valid':None,'repair_requested':False}]
    db.refresh(run)
    metadata=deepcopy(run.reproducibility_metadata or {})
    history=list(metadata.get('generation_observations') or [])
    completed={**deepcopy(observed),'saved_suite':False,'operation_id':operation_id}
    index=next((index for index,item in enumerate(history) if operation_id and item.get('operation_id')==operation_id),None)
    if index is None:history.append(completed)
    else:history[index]=completed
    metadata['generation_observations']=history
    run.reproducibility_metadata=metadata
    if generated is not None or failed:
        _persist_generation_agent_executions(db, run, observed, memories, generated, failed, operation_id)
    db.commit()


def _persist_generation_agent_executions(db, run, observed, memories, generated, failed, operation_id):
    from app.services.agent_trace import record_agent_execution

    if not isinstance(observed, dict):
        return
    stages = []
    planner = observed.get('coverage_planner')
    if isinstance(planner, dict):
        stages.append({**planner, 'role': 'coverage_planning',
                       'execution': planner.get('execution'),
                       'output_data': planner.get('output_data') or {
                           'uncovered_memory_ids': planner.get('uncovered_memory_ids', []),
                           'uncovered_relationships': planner.get('uncovered_relationships', []),
                           'uncovered_dimensions': planner.get('uncovered_dimensions', []),
                           'coverage_notes': planner.get('coverage_notes', []),
                       }})
    for attempt in observed.get('attempts', []):
        if not isinstance(attempt, dict) or not attempt.get('http_execution'):
            continue
        role = attempt.get('agent_role') or 'test_generation'
        request_status = attempt.get('status', '')
        stages.append({
            'role': role,
            'provider': attempt.get('provider') or run.pipeline_provider,
            'model': attempt.get('model') or run.pipeline_model,
            'prompt_template_version': attempt.get('prompt_template_version') or observed.get('agent_version') or 'unversioned',
            'input_refs': attempt.get('input_refs') or {'memory_ids': [memory.memory_id for memory in memories]},
            'input_payload': attempt.get('input_payload') or {'memory_ids': [memory.memory_id for memory in memories]},
            'output_data': attempt.get('output_data'),
            'execution': attempt.get('http_execution'),
            'status': 'completed' if request_status not in {'request_failed', 'failed'}
                      and attempt.get('http_execution', {}).get('status') == 'parsed' else 'failed',
            'error_summary': None if attempt.get('http_execution', {}).get('status') == 'parsed'
                             else 'The question-generation request did not produce a usable structured result.',
        })
    for review in observed.get('semantic_reviews', []):
        if not isinstance(review, dict) or not review.get('http_execution'):
            continue
        status = review.get('status', '')
        stages.append({
            'role': 'test_review', 'provider': review.get('provider') or run.semantic_review_provider or run.pipeline_provider,
            'model': review.get('model') or run.semantic_review_model or run.pipeline_model,
            'prompt_template_version': review.get('prompt_template_version') or review.get('reviewer_version') or 'unversioned',
            'instructions': review.get('instructions') or '', 'prompt': review.get('prompt') or '',
            'schema': review.get('schema'), 'input_payload': review.get('input_payload') or {},
            'input_refs': review.get('input_refs') or {},
            'output_data': review.get('output_data') or {'duplicate_pairs': review.get('duplicate_pairs', []),
                                                          'quality_findings': review.get('quality_findings', [])},
            'execution': review.get('http_execution'),
            'status': 'completed' if status in {'clear', 'issues_found', 'duplicates_found'} else 'failed',
            'error_code': None if status in {'clear', 'issues_found', 'duplicates_found'} else status,
            'error_summary': None if status in {'clear', 'issues_found', 'duplicates_found'}
                             else 'The question reviewer did not return a usable result.',
        })
    if not stages:
        return
    rows = []
    for stage in stages:
        receipt = stage.get('execution') or {}
        row = record_agent_execution(
            db,
            role=stage.get('role') or 'test_generation',
            provider=stage.get('provider') or receipt.get('provider') or run.pipeline_provider,
            model=stage.get('model') or receipt.get('model') or run.pipeline_model,
            prompt_template_version=stage.get('prompt_template_version') or 'unversioned',
            instructions=stage.get('instructions') or '',
            prompt=stage.get('prompt') or '',
            schema=stage.get('schema'),
            input_payload={**(stage.get('input_payload') or {}), 'operation_id': operation_id},
            input_refs=stage.get('input_refs') or {},
            output_data=stage.get('output_data'),
            status=stage.get('status') or ('failed' if failed else 'completed'),
            execution=receipt,
            error_code=stage.get('error_code'),
            error_summary=stage.get('error_summary'),
            run_id=run.id,
            handoff_from=rows[-1].id if rows else None,
        )
        if rows:
            rows[-1].handoff_to = row.id
        rows.append(row)


def mark_generated_suite_saved(run):
    metadata=deepcopy(run.reproducibility_metadata or {})
    history=list(metadata.get('generation_observations') or [])
    if history:
        history[-1]['saved_suite']=True
        if history[-1].get('attempts') and history[-1]['attempts'][-1].get('suite_contract_valid') is None:
            history[-1]['attempts'][-1]['suite_contract_valid']=True
        metadata['generation_observations']=history
        run.reproducibility_metadata=metadata
