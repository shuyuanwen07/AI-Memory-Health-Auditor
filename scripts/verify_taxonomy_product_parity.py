"""Replay saved AC3 provider outputs through research and product evaluators.

No model calls. This validates implementation equivalence on observed cases;
it is not independent performance validation of the product implementation.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database.session import engine
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.evaluator.taxonomy_evaluator import TaxonomyEvidenceEvaluator
from app.models import AuditRunModel, MemoryModel, TargetResponseModel, TestCaseModel
from app.schemas import TargetResponse
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def main():
    root=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen=json.loads((root/'frozen-canonical.json').read_bytes())
    paths=json.loads((root/'sources.json').read_text()); staged=json.loads((root/'staged.json').read_text())
    source=Path(paths['source']).read_bytes();plan=Path(paths['plan']).read_bytes()
    reviews=[Path(p).read_bytes() for p in paths['reviews']]
    components={k:Path(p).read_bytes() for k,p in paths['components'].items()}
    questions=compile_reference_stage(frozen,source,plan,reviews,components)['questions']
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if frozen_sha!=staged['frozen_sha256']:raise ValueError('Frozen study changed')
    sys.path.insert(0,'/output/proposal-delivery/ac3-taxonomy-development-tools-2026-10-28')
    from taxonomy_candidate import TaxonomyCandidate
    from app.api.routes import memory_schema,test_schema
    research=TaxonomyCandidate('openrouter',model='openai/gpt-6-luna')
    product=TaxonomyEvidenceEvaluator()
    mismatches=[];counts={'prompt_match':0,'verdict_match':0,'classification_match':0,'evidence_match':0}
    with Session(engine) as db:
        receipts=db.execute(text("SELECT test_id,status,response_text,target_answer_sha256 FROM ac3_paired_budget_receipts "
            "WHERE scope_id=:scope AND role='scorer'"),{'scope':staged['scope']}).mappings().all()
        by_id={row['test_id']:row for row in receipts}
        if len(receipts)!=120 or len(by_id)!=120:raise ValueError('Expected 120 unique scorer receipts')
        for q in questions:
            ident=q['test_id'];run_id=staged['history_runs'][q['history_id']];receipt=by_id[ident]
            local_id='AC3'+hashlib.sha256(f'{frozen_sha}|{run_id}|{ident}'.encode()).hexdigest()[:32].upper()
            audit=db.get(AuditRunModel,run_id);test=db.get(TestCaseModel,local_id)
            rows=list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id==local_id)))
            if not audit or not test or len(rows)!=1 or receipt['status']!='settled':raise ValueError('Missing source-bound record')
            row=rows[0]
            if hashlib.sha256(row.response_text.encode()).hexdigest()!=receipt['target_answer_sha256']:
                raise ValueError('Scorer receipt does not match saved answer')
            answer=TargetResponse(response_id=row.id,test_id=local_id,run_id=run_id,response_text=row.response_text,
                model=row.model,temperature=row.temperature,created_at=row.created_at or datetime.now(timezone.utc))
            memories=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(
                MemoryModel.conversation_id==audit.conversation_id).order_by(MemoryModel.id))]
            test=test_schema(test);relevant=[m for m in memories if m.memory_id in test.supporting_memory_ids]
            prompt_match=research._judge_prompt(test,answer,relevant)==product._judge_prompt(test,answer,relevant)
            payload=json.loads(receipt['response_text']); LLMBehaviourEvaluator._check_openrouter_completion(payload)
            if payload['choices'][0].get('finish_reason')!='stop':raise ValueError('Provider response was not complete')
            raw=LLMBehaviourEvaluator._parse_json(LLMBehaviourEvaluator._deepseek_text(payload))
            with patch.object(research,'_credential',return_value=''),patch.object(research,'_judge',return_value=raw), \
                 patch.object(research,'_openrouter_output_budget',return_value={'requested_output_token_limit':2048}), \
                 patch.object(product,'_credential',return_value=''),patch.object(product,'_judge',return_value=raw):
                _,provider=research.evaluate_with_provider(test,answer,memories)
                actual=product.evaluate(test,answer,memories)
            if provider is None:raise ValueError('Research candidate did not validate stored provider output')
            verdict_match=actual.passed==provider['passed']
            classification_match=(actual.failure_type.value if actual.failure_type is not None else None)==provider['failure_type']
            evidence_match=set(actual.evidence_memory_ids)==set(provider['evidence_memory_ids'])
            for k,ok in (('prompt_match',prompt_match),('verdict_match',verdict_match),
                         ('classification_match',classification_match),('evidence_match',evidence_match)):
                counts[k]+=int(ok)
            if not all((prompt_match,verdict_match,classification_match,evidence_match)):mismatches.append(ident)
    result={'format':'taxonomy-product-parity-v1','frozen_sha256':frozen_sha,'cases':len(questions),
            'counts':counts,'mismatch_ids':mismatches,'model_called':False,
            'scope':'Replay of observed provider outputs; parity does not establish population performance.'}
    output=root/'product-parity.json'
    with output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main()
