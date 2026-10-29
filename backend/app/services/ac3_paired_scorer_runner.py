"""Internal scorer step that loads the frozen question and saved target answer.

Caller must execute this in the verified candidate snapshot environment. This
is not exposed as a route and does not publish or adjudicate results.
"""
import hashlib
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditRunModel,MemoryModel,TargetResponseModel,TestCaseModel
from app.schemas import TargetResponse
from app.services.ac3_locked_preflight import ac3_sequence_locks
from app.services.ac3_paired_locked_preflight import locked_paired_preflight
from app.services.ac3_paired_scorer_step import score_once
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def run_paired_scorer_step(engine, *, ledger, frozen, source, plan, reviews, components,
                           history_conversations, history_runs, scope, test_id, request_key, judge, headers):
    if engine.url.get_backend_name()!='postgresql' or ledger.engine is not engine:
        raise ValueError('Scorer execution requires the matching PostgreSQL ledger')
    if any(getattr(ledger,key)!=value for key,value in (('source',source),('plan',plan),('reviews',reviews),('components',components))):
        raise ValueError('Ledger evidence differs from the reviewed study')
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if frozen_sha!=ledger.frozen_sha256:raise ValueError('Frozen study differs from the ledger')
    stage=compile_reference_stage(frozen,source,plan,reviews,components)
    questions=[item for item in stage['questions'] if item['test_id']==test_id]
    if len(questions)!=1 or questions[0]['history_id'] not in history_runs:
        raise ValueError('Question does not belong to this frozen study')
    question=questions[0];run_id=history_runs[question['history_id']]
    local_id='AC3'+hashlib.sha256(f'{frozen_sha}|{run_id}|{test_id}'.encode()).hexdigest()[:32].upper()
    from app.api.routes import memory_schema,test_schema
    with Session(engine) as db, ac3_sequence_locks(db,history_runs):
        with locked_paired_preflight(db,frozen,source,plan,reviews,components,history_conversations,history_runs):
            audit=db.get(AuditRunModel,run_id);test=db.get(TestCaseModel,local_id)
            answers=list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id==local_id)))
            if not audit or not test or test.run_id!=run_id or len(answers)!=1 or answers[0].run_id!=run_id:
                raise ValueError('The frozen question needs one saved target answer')
            saved=answers[0]
            answer=TargetResponse(response_id=saved.id,test_id=local_id,run_id=run_id,response_text=saved.response_text,
                model=saved.model,temperature=saved.temperature,created_at=saved.created_at or datetime.now(timezone.utc))
            memories=[memory_schema(db,row) for row in db.scalars(select(MemoryModel)
                .where(MemoryModel.conversation_id==audit.conversation_id).order_by(MemoryModel.id))]
            settings=frozen['protocol'].get('scorer') or {}
            return score_once(ledger,frozen=frozen,components=components,scope=scope,request_key=request_key,
                frozen_test_id=test_id,judge=judge,test=test_schema(test),answer=answer,memories=memories,
                question=question,answer_sha256=hashlib.sha256(answer.response_text.encode()).hexdigest(),
                model=settings.get('model'),output_token_limit=settings.get('output_token_limit'),headers=headers)
