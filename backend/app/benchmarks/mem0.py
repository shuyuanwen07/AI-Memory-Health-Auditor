"""Native memory-only target paired with the ordinary, shared answer connector."""
import os
import re
import time
import json
from hashlib import sha256
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

import httpx

from app.schemas import AuditRun, Dimension, TestCase
from app.schemas.benchmark import LiveBenchmarkCaseResult
from app.target_ai.providers import HttpTargetAIConnector


def endpoint():
    return os.getenv('MEM0_TARGET_URL','').strip().rstrip('/')


def call(operation, payload):
    try:
        with httpx.Client(timeout=httpx.Timeout(180,connect=5),follow_redirects=False) as client:
            response=client.post(endpoint()+'/'+operation,json=payload)
            response.raise_for_status()
            value=response.json()
        if not isinstance(value,dict):raise TypeError('Invalid target reply')
        return value
    except (httpx.HTTPError,ValueError,TypeError):
        raise ValueError('The native Mem0 target did not complete its memory operation. Check its local service and model availability.') from None


def prepare_case(request,case,cancelled:Event|None):
    if cancelled is not None and cancelled.is_set():raise ValueError('The live benchmark was cancelled.')
    rid='MB'+uuid4().hex[:20]
    prompt=case.question+(f'\nQuestion date: {case.question_timestamp.isoformat()}' if case.question_timestamp else '')
    started=time.perf_counter()
    ready=call('ingest',{'namespace':rid,'messages':[m.model_dump(mode='json',exclude={'source_session_id','timestamp_basis'}) for m in case.messages],
        'target':{'provider':request.provider.value,'model':request.model,'temperature':request.temperature},
        'memory_profile':request.target_memory_profile.model_dump(),'memory_strategy':'strong_score_based'})
    if ready.get('namespace')!=rid or ready.get('ready') is not True or ready.get('inference') is not True:
        raise ValueError('Native Mem0 did not confirm an isolated, inferred memory store.')
    tid='MT'+uuid4().hex[:20]
    if cancelled is not None and cancelled.is_set():raise ValueError('The live benchmark was cancelled before retrieval.')
    found=call('retrieve',{'namespace':rid,'request_id':tid,'prompt':prompt})
    if found.get('namespace')!=rid or found.get('request_id')!=tid:
        raise ValueError('Native Mem0 returned another question or memory namespace.')
    records,selected,stored=found.get('retrieved'),found.get('supplied'),found.get('stored')
    if any(not isinstance(values,list) for values in (records,selected,stored)):
        raise ValueError('Native Mem0 memory evidence is malformed.')
    for values in (records,selected,stored):
        if any(not isinstance(r,dict) or not isinstance(r.get('id'),str) or not isinstance(r.get('memory'),str) for r in values):
            raise ValueError('Native Mem0 memory evidence is malformed.')
        if len({r['id'] for r in values})!=len(values):raise ValueError('Native Mem0 returned duplicate memory records.')
    retrieved={r['id']:r['memory'] for r in records}
    if any(retrieved.get(r['id'])!=r['memory'] for r in selected):
        raise ValueError('The native supplied records do not match its retrieved records.')
    if len(selected)>min(request.target_memory_profile.max_retrieved_records,20) or sum(len(r['memory']) for r in selected)>request.target_memory_profile.context_character_budget:
        raise ValueError('Native Mem0 exceeded the shared supply budget.')
    preparation_ms=round((time.perf_counter()-started)*1000,2)
    snapshot = {'namespace':rid, 'prompt':prompt, 'retrieved':records, 'supplied':selected, 'stored':stored,
        'found':found, 'ingest_usage':ready.get('inference_usage'), 'latency_ms':preparation_ms}
    snapshot['sha256'] = sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    return snapshot


GENERIC_INSTRUCTION = 'Double-check the supplied memories before answering. Use relevant evidence carefully, distinguish facts from assumptions, and avoid unsupported guesses.'
REPAIR_VERSION = 'native-task-supply-v1'


def task_supply(prompt, selected):
    """Filter only separable task facts for explicit task questions; no gold values."""
    preference_query = re.search(r'\b(?:do\s+i|does\s+(?:the\s+)?user)\s+(?:generally\s+|usually\s+)?prefer\b|\bwhat\b[^?!.]*\b(?:preference|favou?rite)\b', prompt, re.I)
    task_query = re.search(r'\b(?:assignment|task|project|require\w*|must)\b', prompt, re.I)
    if preference_query or not task_query:
        return list(selected)
    scoped = [r for r in selected if re.search(r'\b(?:assignment|task|project|require\w*|must)\b', r['memory'], re.I)
        and not re.search(r'\b(?:prefer\w*|favou?rite)\b', r['memory'], re.I)]
    # Ambiguous bundled facts are kept; the wrapper never rewrites native facts.
    bundled = [r for r in selected if re.search(r'\b(?:assignment|task|project|require\w*|must)\b', r['memory'], re.I)
        and re.search(r'\b(?:prefer\w*|favou?rite)\b', r['memory'], re.I)]
    return [r for r in selected if r in scoped or r in bundled] if scoped else list(selected)


def answer_snapshot(request,case,snapshot,cancelled,runner_version,intervention='baseline'):
    if intervention not in {'baseline','generic','directed'}:
        raise ValueError('Unknown native memory intervention.')
    rid = snapshot['namespace']
    tid = 'MT'+uuid4().hex[:20]
    prompt = snapshot['prompt']
    found = snapshot['found']
    records, stored = snapshot['retrieved'], snapshot['stored']
    selected = task_supply(case.question, snapshot['supplied']) if intervention=='directed' else list(snapshot['supplied'])
    retrieved = {r['id']:r['memory'] for r in records}
    profile = request.target_memory_profile.model_copy(deep=True)
    if intervention=='generic':
        profile.additional_instructions = (profile.additional_instructions+'\n'+GENERIC_INSTRUCTION).strip()
    audit=AuditRun(run_id=rid,conversation_id=rid,status='CREATED',target_configuration='strong',provider=request.provider,
        model=request.model,temperature=request.temperature,random_seed=request.random_seed,test_budget=1,
        prompt_template_version=runner_version,created_at=datetime.now(timezone.utc),target_memory_profile=profile)
    private=TestCase(test_id=tid,run_id=rid,prompt=prompt,expected_behavior='',supporting_memory_ids=[],generator_version=runner_version,
        dimension=Dimension.CONFLICT_RESOLUTION if re.search(r'\b(?:conflict|contradict|disagree)\w*\b',case.question,re.I) else Dimension.ACCURACY,
        target_memory_context=[r['memory'] for r in selected])
    if cancelled is not None and cancelled.is_set():raise ValueError('The live benchmark was cancelled before the reader call.')
    response=HttpTargetAIConnector().execute(private,audit)
    if response.execution_metadata.memory_input is None or response.execution_metadata.memory_input.record_count!=len(selected):
        raise ValueError('The shared reader did not confirm the supplied native records.')
    response.execution_metadata.memory_input.sent_memory_ids=[r['id'] for r in selected]
    from app.benchmarks.live import LiveBenchmarkRunner
    from app.benchmarks.runner import LongMemEvalDeterministicRunner
    usages = [snapshot.get('ingest_usage'), found.get('inference_usage')]
    def counted(field):
        values = [u.get(field) if isinstance(u, dict) else None for u in usages]
        return sum(values) if all(type(v) is int and v >= 0 for v in values) else None
    return LiveBenchmarkCaseResult(case_id=case.case_id,category=case.category,question=case.question,expected_answer=case.expected_answer,
        response_text=response.response_text,lexical_match=LiveBenchmarkRunner._lexical_match(case.expected_answer,response.response_text),
        token_f1=LongMemEvalDeterministicRunner._token_f1(case.expected_answer,response.response_text),execution_metadata=response.execution_metadata,
        retrieved_memory_ids=list(retrieved),supplied_memory_ids=[r['id'] for r in selected],stored_memory_count=len(stored),retained_memory_count=len(stored),
        message_count=len(case.messages),assistant_message_count=sum(m.role=='assistant' for m in case.messages),
        memory_evidence=[{'memory_id':r['id'],'canonical_value':r['memory'],'lifecycle_state':'NATIVE','scope':'native_mem0',
            'source_message_ids':[],'retrieved':r['id'] in retrieved,'supplied':r['id'] in {x['id'] for x in selected}} for r in stored],
        ranking_evidence=[{'memory_id':r['id'],'native_score':r.get('score')} for r in records],
        memory_preparation={'system':'mem0_oss','sdk_version':found.get('sdk_version'),'target_service':found.get('target_service'),
            'latency_ms':snapshot['latency_ms'],'native_inference':True,
            'native_llm_calls':counted('llm_attempts'), 'embedding_calls':counted('embedding_attempts'),
            'native_llm_failures':counted('llm_failures'), 'embedding_failures':counted('embedding_failures'),
            'inference_usage':{'ingest':usages[0], 'retrieve':usages[1]},
            'cost_notice':'Observed SDK inference attempts for completed preparation; model setup, lower-level retries, hardware and monetary cost are not measured.',
            'source_attribution':'unavailable','stored_listing_limit':found.get('stored_listing_limit'),'shared_snapshot_sha256':snapshot['sha256'],
            'preparation_charged_here':intervention=='baseline'},
        intervention={'name':intervention,'policy_version':REPAIR_VERSION,'removed_memory_ids':[r['id'] for r in snapshot['supplied'] if r not in selected],
            'additional_instructions':GENERIC_INSTRUCTION if intervention=='generic' else '',
            'native_extraction_changed':False,'snapshot_shared':True})


def run_case(request,case,cancelled:Event|None,runner_version):
    return answer_snapshot(request,case,prepare_case(request,case,cancelled),cancelled,runner_version)


def run_case_comparison(request,case,cancelled:Event|None,runner_version):
    snapshot = prepare_case(request,case,cancelled)
    return {name:answer_snapshot(request,case,deepcopy(snapshot),cancelled,runner_version,name)
        for name in ('baseline','generic','directed')}
