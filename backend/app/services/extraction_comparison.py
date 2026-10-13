"""Extraction outputs are isolated from confirmed source memories and answers."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditRunModel, ConversationModel, ExtractionComparisonModel, MemoryModel, MemoryRelationshipModel
from app.schemas import Memory
from app.services.reassessment import saved_answer_signature
from app.services.runtime_freeze import audit_runtime_signature
from app.services.generator_usage import generator_usage


def source_for_plan(db, plan):
    source = db.get(AuditRunModel, plan.source_run_id)
    if not source or saved_answer_signature(db, source) != plan.input_fingerprint:
        raise HTTPException(409, 'Reference data changed. Saved extraction outputs remain available; start a new comparison.')
    conversation = db.get(ConversationModel, source.conversation_id)
    if not conversation or not conversation.authorised:
        raise HTTPException(409, 'The source conversation is unavailable or no longer authorised.')
    if plan.runtime_signature != audit_runtime_signature():
        raise HTTPException(409, 'Software changed. Saved extraction outputs remain available; start a new comparison.')
    return source


def create_extraction_plan(db, request):
    fingerprint = hashlib.sha256(json.dumps(request.model_dump(exclude={'creation_request_key'}),sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(ExtractionComparisonModel).where(ExtractionComparisonModel.creation_request_key==request.creation_request_key))
    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(409, 'This saved comparison has different settings. Start a new comparison.')
        return existing
    source = db.get(AuditRunModel, request.source_run_id)
    if source and (source.reproducibility_metadata or {}).get('assessment_source_run_id'):
        source = db.get(AuditRunModel, source.reproducibility_metadata['assessment_source_run_id'])
    if not source or source.status != 'COMPLETED':
        raise HTTPException(409, 'Choose a completed reference audit.')
    conversation = db.get(ConversationModel, source.conversation_id)
    if not conversation or not conversation.authorised:
        raise HTTPException(409, 'Choose an authorised reference conversation.')
    references = []
    for memory in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==source.conversation_id,
                                                      MemoryModel.status.in_(['confirmed','edited']))):
        relationships = [{'type':row.relationship_type,'target_memory_id':row.target_memory_id}
                         for row in db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id==memory.id))]
        references.append(Memory(memory_id=memory.id,conversation_id=source.conversation_id,
            canonical_value=memory.canonical_value,status=memory.status,source_message_ids=memory.source_message_ids,
            timestamp=memory.timestamp,relationships=relationships).model_dump(mode='json'))
    if not references:
        raise HTTPException(422,'Choose an audit with confirmed reference memories.')
    plan = ExtractionComparisonModel(id='EC'+uuid4().hex.upper(),creation_request_key=request.creation_request_key,
        fingerprint=fingerprint,source_run_id=source.id,input_fingerprint=saved_answer_signature(db,source),
        runtime_signature=audit_runtime_signature(),reference_snapshot=references,entries=[{'selection':item.model_dump(),'status':'pending',
            'candidates':None,'operations':[]} for item in request.extractors])
    db.add(plan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ExtractionComparisonModel).where(ExtractionComparisonModel.creation_request_key==request.creation_request_key))
        if not existing or existing.fingerprint != fingerprint:
            raise HTTPException(409, 'The comparison could not be saved with these settings.') from None
        return existing
    db.refresh(plan)
    return plan


def extract_entry(db, plan, index, conversation, factory):
    source_for_plan(db, plan)
    if index < 0 or index >= len(plan.entries):
        raise HTTPException(404, 'Extraction condition not found.')
    entry = deepcopy(plan.entries[index])
    if entry['status'] == 'completed':
        return plan
    operation = {'operation_id':uuid4().hex,'status':'started','saved_output':False,
        'started_at':datetime.now(timezone.utc).isoformat(),'attempts':[{'status':'requesting'}]}
    entry['operations'].append(operation)
    entry['status'] = 'started'
    entries = deepcopy(plan.entries); entries[index] = entry; plan.entries = entries
    db.commit()  # Durable intent exists before any potentially paid call.
    extractor = None
    try:
        selection = entry['selection']
        extractor = factory(selection['provider'],selection['model'])
        operation['extractor_version'] = getattr(extractor,'VERSION',type(extractor).__name__)
        candidates = extractor.extract(conversation)
        identities = {memory.memory_id for memory in candidates}
        known_messages = {message.message_id for message in conversation.messages if message.role.strip().lower()=='user'}
        if len(identities) != len(candidates) or any(not memory.source_message_ids
                or not set(memory.source_message_ids).issubset(known_messages)
                or any(relation.target_memory_id not in identities or relation.target_memory_id==memory.memory_id
                       for relation in memory.relationships) for memory in candidates):
            raise HTTPException(502, 'The extractor returned invalid source links. No candidate output was saved.')
        source_for_plan(db, plan)  # Changed input during a call cannot become a valid result.
        entry['candidates'] = [memory.model_dump(mode='json') for memory in candidates]
        entry['status'] = 'completed'
        operation.update(status='completed',saved_output=True)
        operation['attempts'][0]['status'] = 'returned'
    except Exception as cause:
        db.rollback()
        entry['status'] = 'failed'
        operation['status'] = 'failed'
        operation['attempts'][0]['status'] = 'failed'
        operation['failure_status'] = cause.status_code if isinstance(cause,HTTPException) else 502
        # Exceptions may contain provider bodies or credentials. Persist only
        # a bounded category; public extraction clients supply safe API errors.
        operation['failure_category'] = 'input_or_software_changed' if operation['failure_status']==409 else 'extraction_failed'
        raise
    finally:
        receipt = getattr(getattr(extractor,'client',None),'last_execution',None)
        if receipt is not None:
            operation['attempts'][0]['http_execution'] = deepcopy(receipt)
        operation['finished_at'] = datetime.now(timezone.utc).isoformat()
        db.refresh(plan)
        entries = deepcopy(plan.entries); entries[index] = entry; plan.entries = entries
        db.commit()
    return plan


def extraction_usage(entry):
    observed = generator_usage(SimpleNamespace(pipeline_provider=entry['selection']['provider'],
        pipeline_model=entry['selection']['model'],
        reproducibility_metadata={'generation_observations':entry['operations']}))
    observed['scope'] = 'Saved extraction invocations only, including failed calls and retries. Missing usage remains unknown; reported credits are not a full invoice.'
    return observed


def exact_reference_checks(candidates, references):
    if candidates is None:
        return None
    def text(value):
        return ' '.join(value.strip().casefold().rstrip('.').split())
    reference_text = {memory.memory_id:text(memory.canonical_value) for memory in references}
    candidate_text = {memory['memory_id']:text(memory['canonical_value']) for memory in candidates}
    facts = set(reference_text.values())
    outputs = set(candidate_text.values())
    reference_links = {(reference_text[memory.memory_id],relation.type.value,reference_text[relation.target_memory_id])
                       for memory in references for relation in memory.relationships if relation.target_memory_id in reference_text}
    output_links = {(candidate_text[memory['memory_id']],relation['type'],candidate_text[relation['target_memory_id']])
                    for memory in candidates for relation in memory['relationships'] if relation['target_memory_id'] in candidate_text}
    return {'candidate_count':len(candidates),'reference_fact_count':len(facts),'exact_fact_matches':len(facts & outputs),
        'reference_relationship_count':len(reference_links),'exact_relationship_matches':len(reference_links & output_links),
        'fact_coverage_percent':100*len(facts & outputs)/len(facts) if facts else None,
        'relationship_coverage_percent':100*len(reference_links & output_links)/len(reference_links) if reference_links else None,
        'scope':'Exact normalised reference text and endpoint/type matching only. Paraphrases may not match; unmatched output is not automatically wrong. Not semantic accuracy or independent human validation.'}
