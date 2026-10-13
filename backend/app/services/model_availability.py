"""Only allowed, recently callable models are offered for new cloud requests."""
from copy import deepcopy
from collections.abc import Mapping
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
import re
import time

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.models import ModelAvailabilityModel
from app.extraction.llm import PipelineLLMClient
from app.target_ai.openrouter import CHAT_COMPLETIONS_URL,request_options
from app.services.stage_lock import database_stage_busy

_CATALOG=None
_CATALOG_AT=0.0
VERSION='allowed-json-availability-v1'
FAILURE_RECHECK_COOLDOWN=timedelta(minutes=10)
MAX_RETAINED_OPERATIONS=50


def allowed(model):
    return bool(re.match(r'^(?:anthropic/claude-opus-|openai/gpt-(?:5\.6|6(?:\.\d+)?)(?:-|$)|google/gemini-)',model)
                and ':' not in model
                and not re.search(r'(?:^|[-_/])batch(?:$|[-_/])',model,re.I)
                and not re.search(r'(?:latest|auto|image|audio|tts|embedding|decisions)',model,re.I))


def credential_scope():
    key=os.getenv('OPENROUTER_API_KEY','').strip()
    if not key:raise HTTPException(503,'OpenRouter is not configured.')
    return hashlib.sha256(json.dumps([VERSION,key,CHAT_COMPLETIONS_URL,request_options()],sort_keys=True).encode()).hexdigest()


def catalog():
    global _CATALOG,_CATALOG_AT
    scope=credential_scope()
    if _CATALOG and _CATALOG[0]==scope and time.monotonic()-_CATALOG_AT<300:return _CATALOG[1]
    try:
        response=httpx.get('https://openrouter.ai/api/v1/models',headers={'Authorization':'Bearer '+os.getenv('OPENROUTER_API_KEY','').strip()},timeout=15)
        response.raise_for_status()
        items=response.json()['data']
        if not isinstance(items,list):raise ValueError('Invalid model catalog.')
        result=[]
        for item in items:
            if not isinstance(item,Mapping) or not isinstance(item.get('id'),str) or not allowed(item['id']):continue
            architecture=item.get('architecture')
            if architecture is None:architecture={}
            if not isinstance(architecture,Mapping):continue
            inputs=architecture.get('input_modalities',['text']);outputs=architecture.get('output_modalities',['text'])
            if not isinstance(inputs,list) or not isinstance(outputs,list) or 'text' not in inputs or 'text' not in outputs:continue
            identifier=item['id'];name=item.get('name')
            label=name.strip() if isinstance(name,str) and name.strip() and identifier.casefold() not in name.casefold() else _friendly_name(identifier)
            result.append({'value':identifier,'label':label})
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise HTTPException(502,'The allowed model catalog could not be loaded. Retry the check.') from None
    result.sort(key=lambda item:item['label'].casefold());_CATALOG=(scope,result);_CATALOG_AT=time.monotonic()
    return result


def _friendly_name(model):
    name=model.split('/',1)[-1]
    if name.startswith('gpt-'):return 'GPT ' + name[4:].replace('-', ' ')
    if name.startswith('claude-opus-'):return 'Claude Opus ' + name.removeprefix('claude-opus-').replace('-', ' ')
    if name.startswith('gemini-'):return 'Gemini ' + name.removeprefix('gemini-').replace('-', ' ')
    return 'Cloud model'


def recent(row):
    if row is None or row.checked_at is None:return False
    stamp=row.checked_at.replace(tzinfo=row.checked_at.tzinfo or timezone.utc)
    return stamp>datetime.now(timezone.utc)-timedelta(hours=6)


def options_and_checks(db):
    scope=credential_scope()
    rows={row.model:row for row in db.scalars(select(ModelAvailabilityModel).where(ModelAvailabilityModel.credential_scope==scope))}
    result=[]
    for item in catalog():
        row=rows.get(item['value'])
        scope_key=f"model-check:{scope}:{item['value']}"
        if row is not None and row.status=='checking' and database_stage_busy(db,scope_key):status='checking'
        else:status=row.status if recent(row) else 'not_checked'
        last=row.operations[-1] if row is not None and row.operations else {}
        result.append({**item,'status':status,'checked_at':row.checked_at if row else None,
                       'reason':last.get('reason') if status=='unavailable' else None})
    return result


def verified_options(db):
    return [{'value':item['value'],'label':item['label']} for item in options_and_checks(db) if item['status']=='available']


def check_model(db,model):
    if not allowed(model) or model not in {item['value'] for item in catalog()}:
        raise HTTPException(422,'Choose an allowed model from the current catalog.')
    scope=credential_scope();identity=hashlib.sha256((scope+model).encode()).hexdigest()
    row=db.get(ModelAvailabilityModel,identity)
    if row is not None and recent(row) and row.status=='available':return {'model':model,'status':'available','checked_at':row.checked_at}
    if row is not None and recent(row) and row.status=='unavailable' and datetime.now(timezone.utc)-row.checked_at.replace(tzinfo=row.checked_at.tzinfo or timezone.utc)<FAILURE_RECHECK_COOLDOWN:
        last=row.operations[-1] if row.operations else {}
        return {'model':model,'status':'unavailable','reason':last.get('reason','The last check was unsuccessful; wait before retrying.'),'checked_at':row.checked_at}
    if row is None:
        row=ModelAvailabilityModel(id=identity,model=model,credential_scope=scope,status='checking',operations=[],checked_at=None)
        db.add(row)
    history=deepcopy(row.operations);operation={'started_at':datetime.now(timezone.utc).isoformat(),'status':'checking','version':VERSION}
    history.append(operation);row.operations=history;row.status='checking';row.checked_at=None;db.commit()
    client=None
    try:
        client=PipelineLLMClient('openrouter',model)
        result=client.complete_json(instructions='Return exactly the requested JSON object. This is a model availability check.',
            prompt='Return {"available":true}.',schema_name='availability_check',
            schema={'type':'object','additionalProperties':False,'required':['available'],'properties':{'available':{'type':'boolean'}}},
            max_output_tokens=64)
        receipt=client.last_execution or {}
        reported=receipt.get('reported_model')
        exact_model=isinstance(reported,str) and reported.casefold()==model.casefold()
        valid_output=isinstance(result,dict) and set(result)=={'available'} and result['available'] is True
        success=exact_model and valid_output
        operation['status']='available' if success else 'unavailable'
        operation['reason']=('Verified structured output from the selected model' if success else
            'The returned model identity did not match the selected model' if not exact_model else
            'The model did not return the required structured response')
        operation['reported_model']=reported
    except Exception:
        operation['status']='unavailable'
        receipt=client.last_execution if client is not None else None
        operation['reason']=_safe_failure_reason(receipt)
    operation['receipt']=deepcopy(client.last_execution) if client is not None else None
    operation['finished_at']=datetime.now(timezone.utc).isoformat()
    history=history[-MAX_RETAINED_OPERATIONS:]
    history[-1]=operation;row.operations=history;row.status=operation['status'];row.checked_at=datetime.now(timezone.utc);db.commit()
    return {'model':model,'status':row.status,'reason':operation['reason'],'checked_at':row.checked_at}


def _safe_failure_reason(receipt):
    """Map safe client evidence to a useful category, never expose upstream bodies."""
    receipt=receipt if isinstance(receipt,dict) else {}
    status=receipt.get('last_http_status')
    if status in {401,403}:return 'The OpenRouter key or its model access was rejected'
    if status==402:return 'The OpenRouter account could not cover this request'
    if status==404:return 'This model is not available through the selected service'
    if status==429:return 'The service rate limit was reached; retry later'
    if status==400:return 'The model rejected the required structured-output format'
    if isinstance(status,int) and status>=500:return 'The model service had a temporary error'
    if receipt.get('status')=='failed':return 'The model did not complete the structured-output check'
    return 'The model request could not be verified; retry after checking service access'
