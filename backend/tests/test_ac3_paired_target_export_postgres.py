"""Private full-suite export from an explicitly disposable database."""
import hashlib
import json
import os
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
from app.models import AuditRunModel,TargetResponseModel
from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_export import collect_paired_targets
from app.services.ac3_paired_replay_export import collect_paired_scores
from app.services.ac3_retest_prepare import prepare_paired_retest
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage
from scripts.ac3_paired_blind_review import make_packets,validate_reviews
from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
from test_ac3_staging_postgres_isolated import isolated_db as isolated_db,URL

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


def test_export_requires_all_120_bound_settled_answers(isolated_db):
    engine=create_engine(URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=0,pool_timeout=3)
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    try:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_receipts'))
            conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_scopes'))
            for sql in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
                if sql.strip():conn.execute(text(sql))
        sample=AuditRun(run_id='sample',conversation_id='sample',status='CREATED',target_configuration='strong',
            provider='rule_based',model='fixture',temperature=0,random_seed=1,test_budget=4,
            prompt_template_version='fixture',memory_strategy='strong_rule_based',target_memory_profile={'output_token_limit':20},
            target_memory_writer_version='fixture-writer',target_system_adapter_version='fixture-adapter',created_at=datetime.now(timezone.utc))
        setup=sample.model_dump(mode='json',include=_SETTINGS_FIELDS)
        helper.cfg['target'].update(provider='rule_based',model='fixture',strategy='strong_rule_based',prompt_template_version='fixture',
            memory_configuration_sha256=hashlib.sha256(canonical(setup)).hexdigest())
        frozen=helper.freeze();sha=hashlib.sha256(canonical(frozen)).hexdigest()
        prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        with Session(engine) as db:
            audits=[r for r in db.scalars(select(AuditRunModel)) if r.status=='RESEARCH_STAGED']
            runs={r.reproducibility_metadata['ac3_paired_retest']['history_id']:r.id for r in audits}
            conversations={r.reproducibility_metadata['ac3_paired_retest']['history_id']:r.conversation_id for r in audits}
        ledger=PairedBudgetLedger(engine,frozen_path='/tmp/synthetic',frozen_sha256=sha,source=helper.source,plan=helper.plan,
            reviews=helper.reviews,components=helper.components,budget_path='/tmp/budget',budget_sha256='b'*64,billing_path='/tmp/billing')
        questions=[q for c in frozen['suite']['cases'] for q in c['tests']]
        budget={'eligible_test_ids':[q['test_id'] for q in questions],'max_usd':'0.40','reservation_per_target_usd':'0.001'}
        with patch.object(ledger,'_validated',return_value=(budget,Decimal('0.20'),Decimal('0.001'))):
            ledger.register('synthetic')
            with Session(engine) as db,db.begin():
                for case in frozen['suite']['cases']:
                    run_id=runs[case['history_id']]
                    for q in case['tests']:
                        ident=q['test_id'];request='request-'+ident;answer='synthetic '+ident
                        evidence=json.dumps({'format':'ac3-private-request-evidence-v1','frozen_test_id':ident,'run_id':run_id},sort_keys=True,separators=(',',':'))
                        esha=hashlib.sha256(evidence.encode()).hexdigest()
                        local='AC3'+hashlib.sha256(f'{sha}|{run_id}|{ident}'.encode()).hexdigest()[:32].upper()
                        rid='ACR'+hashlib.sha256(f'synthetic|{request}'.encode()).hexdigest()[:32].upper()
                        db.execute(text("INSERT INTO ac3_paired_budget_receipts (request_key,scope_id,test_id,role,contract_sha256,request_evidence_json,request_evidence_sha256,reserved_usd,status,response_text,reported_cost_usd) VALUES (:key,'synthetic',:test,'target',:contract,:evidence,:esha,'0.001','settled',:answer,'0.0001')"),
                            {'key':request,'test':ident,'contract':'c'*64,'evidence':evidence,'esha':esha,'answer':answer})
                        db.add(TargetResponseModel(id=rid,test_id=local,run_id=run_id,response_text=answer,model='fixture',temperature=0,
                            execution_metadata={'ac3_paired_request_evidence_sha256':esha}))
            kwargs=dict(ledger=ledger,frozen=frozen,source=helper.source,plan=helper.plan,reviews=helper.reviews,
                components=helper.components,history_conversations=conversations,history_runs=runs,scope='synthetic')
            result=collect_paired_targets(engine,**kwargs)
            assert len(result['answers'])==120 and not result['model_called']
            stage=compile_reference_stage(frozen,helper.source,helper.plan,helper.reviews,helper.components)
            packet,reviewers,key=make_packets(frozen,stage['questions'],result)
            for slot,review in enumerate(reviewers,1):
                review['reviewer_declaration']={'reviewer_label':f'synthetic-{slot}','completed_by_human':True,
                    'completed_independently':True,'has_seen_automatic_results':False,'has_seen_other_review':False,'used_ai_assistance':False}
                for row in review['decisions']:row.update(verdict='pass',failure_dimension=None,rationale='Synthetic only.')
            checked=validate_reviews(packet,reviewers,key)
            assert len(checked['reviews'][0])==120 and not checked['adjudicated']
            with pytest.raises(ValueError, match='both receipts'):
                collect_paired_scores(engine,judge=object(),**kwargs)
            with engine.begin() as conn:
                for item in result['answers']:
                    conn.execute(text("INSERT INTO ac3_paired_budget_receipts (request_key,scope_id,test_id,role,contract_sha256,target_answer_sha256,reserved_usd,status,response_text,reported_cost_usd) VALUES (:key,'synthetic',:test,'scorer',:contract,:answer_sha,'0.001','settled','synthetic output','0.0001')"),
                        {'key':'score-'+item['test_id'],'test':item['test_id'],'contract':'d'*64,'answer_sha':item['response_sha256']})
            def synthetic_replay(frozen,components,judge,test,answer,memories,question,receipt,*,scope,frozen_test_id):
                digest=hashlib.sha256(answer.response_text.encode()).hexdigest()
                assert receipt['target_answer_sha256']==digest
                def record(role):
                    return {'test_id':frozen_test_id,'target_answer_sha256':digest,
                            'evaluator_version_sha256':frozen['protocol']['component_sha256'][role],
                            'verdict':'uncertain','failure_type':None}
                return {'format':'ac3-paired-single-replay-v1','frozen_sha256':sha,
                        'target_answer_sha256':digest,'old':record('old_evaluator'),'new':record('new_evaluator'),
                        'new_scorer_variant':'hybrid','model_called':False,'human_truth_evaluated':False}
            with patch('app.services.ac3_paired_replay_export.replay_pair',side_effect=synthetic_replay):
                pairs=collect_paired_scores(engine,judge=object(),**kwargs)
            assert pairs['integrity']['answer_pairing_verified'] and len(pairs['old_records'])==120
            with engine.begin() as conn:
                conn.execute(text("UPDATE ac3_paired_budget_scopes SET status='unknown' WHERE scope_id='synthetic'"))
            with pytest.raises(ValueError,match='unresolved'):collect_paired_targets(engine,**kwargs)
    finally:helper.doCleanups();engine.dispose()
