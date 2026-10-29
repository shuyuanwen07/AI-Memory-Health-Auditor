"""Source import uses only synthetic fixtures and never calls a model."""
from datetime import datetime
import hashlib, json
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.entities import Base
from app.models import ConversationModel, MessageModel, MemoryModel, MemoryRelationshipModel
from app.services.ac3_reviewed_source_import import import_reviewed_ac3_sources
from scripts.ac3_fixed_suite_adapter import sha


@pytest.fixture
def fixture_plan(tmp_path):
    suite = {'cases': []}; plan = {'histories': {}}
    for n in range(8):
        history=f'H{n}'; sources=[{'message_id':f'{history}-M{i}', 'order':i, 'role':'user', 'text':f'Source {history} message {i}'} for i in range(1,6)]
        facts=[]
        for i, source in enumerate(sources,1):
            for k in range(2 if i in (4,5) else 1):
                facts.append({'memory_id':f'{history}-F{i}-{k}', 'source_message_id':source['message_id'], 'source_span':source['text'], 'canonical_value':source['text'] + f' fact {k}'})
        relations=[{'memory_id':f'{history}-F3-0','target_memory_id':f'{history}-F2-0','relationship_type':'UPDATE','evidence_message_ids':[f'{history}-M3']},
                   {'memory_id':f'{history}-F4-0','target_memory_id':f'{history}-F4-1','relationship_type':'CONFLICT','evidence_message_ids':[f'{history}-M4']},
                   {'memory_id':f'{history}-F5-1','target_memory_id':f'{history}-F5-0','relationship_type':'CONTEXTUAL_OVERRIDE','evidence_message_ids':[f'{history}-M5']}]
        plan['histories'][history]={'facts':facts,'relationships':relations}
        tests=[{'test_id':f'{history}-Q1','question':'Synthetic?', 'expected_behavior':'Synthetic', 'dimension':'accuracy', 'supporting_source_message_ids':[f'{history}-M1']}]
        suite['cases'].append({'history_id':history,'source_messages':sources,'tests':tests})
    digest=hashlib.sha256(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    reviews=[{'reviewer_label':f'synthetic-reviewer-{i}', 'completed_by_human':True,'completed_independently':True,'reviewed_fact_and_relation_semantics':True,'fact_plan_sha256':digest} for i in (1,2)]
    frozen=tmp_path/'synthetic.json'; frozen.write_text(json.dumps({'suite':suite})); frozen_sha=sha(frozen.read_bytes())
    items=[{'history_id':case['history_id'],**test,'grounding_review':'valid'} for case in suite['cases'] for test in case['tests']]
    def compile_fake(path, expected, reservation, snapshot=None):
        if sha(path.read_bytes()) != expected: raise ValueError('changed')
        return {'frozen_sha256':expected,'reviewed_fact_plan':plan,'fact_plan_reviews':reviews,
                'model_configuration':{'synthetic_source_timestamp_utc':'2000-01-01T00:00:00Z'},
                'eligible_question_count':len(items),'items':[dict(x) for x in items]}
    return frozen, frozen_sha, compile_fake


def test_import_all_histories_idempotently_and_preserve_synthetic_order(fixture_plan):
    frozen,digest,compile_fake=fixture_plan; engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
    with patch('app.services.ac3_reviewed_source_import.compile_mock',side_effect=compile_fake), patch('scripts.ac3_database_mapping.compile_mock',side_effect=compile_fake):
        first=import_reviewed_ac3_sources(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')
        assert first['status']=='imported' and first['history_count']==8 and first['memory_count']==56
        assert import_reviewed_ac3_sources(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')['status']=='already_imported'
        with Session(engine) as db:
            assert len(db.scalars(select(ConversationModel)).all())==8
            assert len(db.scalars(select(MemoryRelationshipModel)).all())==24
            messages=list(db.scalars(select(MessageModel).where(MessageModel.conversation_id==first['history_conversations']['H0']).order_by(MessageModel.sequence)))
            assert [m.timestamp for m in messages]==[datetime(2000,1,1,0,0,i) for i in range(5)]
            assert db.get(ConversationModel,first['history_conversations']['H0']).extraction_provenance['timestamp_policy']=='synthetic_placeholder_not_observed_time'
            db.get(MemoryModel,'H0-F1-0').canonical_value='tampered'; db.commit()
        with pytest.raises(ValueError,match='differs'):
            import_reviewed_ac3_sources(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')
    engine.dispose()


def test_unreviewed_plan_fails_before_writing(fixture_plan):
    frozen,digest,compile_fake=fixture_plan; engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
    def unreviewed(*args,**kwargs):
        result=compile_fake(*args,**kwargs); result['fact_plan_reviews'][0]['completed_by_human']=False; return result
    with patch('app.services.ac3_reviewed_source_import.compile_mock',side_effect=unreviewed):
        with pytest.raises(ValueError,match='Human review'):
            import_reviewed_ac3_sources(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')
    with Session(engine) as db: assert not db.scalars(select(ConversationModel)).all()
    engine.dispose()


def test_independent_subset_repeat_reuses_exact_reviewed_sources(fixture_plan, tmp_path):
    frozen,digest,compile_fake=fixture_plan; engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
    with patch('app.services.ac3_reviewed_source_import.compile_mock',side_effect=compile_fake), patch('scripts.ac3_database_mapping.compile_mock',side_effect=compile_fake):
        first=import_reviewed_ac3_sources(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')
    base=compile_fake(frozen,digest,'0'); suite=json.loads(frozen.read_text())['suite']
    subset={'cases':suite['cases'][:3]}; ids={item['history_id'] for item in subset['cases']}
    fact_plan={'histories':{key:value for key,value in base['reviewed_fact_plan']['histories'].items() if key in ids}}
    plan_sha=hashlib.sha256(json.dumps(fact_plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    declarations=[{**item,'fact_plan_sha256':plan_sha} for item in base['fact_plan_reviews']]
    repeat=tmp_path/'synthetic-repeat.json'; repeat.write_text(json.dumps({'suite':subset,'repeat':True})); repeat_sha=sha(repeat.read_bytes())
    items=[item for item in base['items'] if item['history_id'] in ids]
    def repeat_compile(path, expected, reservation, snapshot=None):
        if sha(path.read_bytes())!=expected: raise ValueError('changed')
        return {**base,'frozen_sha256':expected,'reviewed_fact_plan':fact_plan,'fact_plan_reviews':declarations,'items':[dict(item) for item in items],'eligible_question_count':len(items)}
    with patch('app.services.ac3_reviewed_source_import.compile_mock',side_effect=repeat_compile), patch('scripts.ac3_database_mapping.compile_mock',side_effect=repeat_compile):
        result=import_reviewed_ac3_sources(engine,frozen_path=repeat,frozen_sha256=repeat_sha,reservation='0')
        assert result['status']=='already_imported'
        assert result['history_conversations']=={key:first['history_conversations'][key] for key in ids}
    with Session(engine) as db: assert len(db.scalars(select(ConversationModel)).all())==8
    engine.dispose()
