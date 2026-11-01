import copy
import json
import pytest
from scripts import ingest_ac2_astra_four_review as ingest
from scripts.ingest_ac2_astra_four_review import reconcile

def fixture():
    return {'items':[{'test_id':f'T{i}','history_id':f'H{i//4}','source_messages':[{'text':f'fact {i}'}],
                      'dimension':'accuracy','question':f'question {i}','expected_behavior':f'answer {i}',
                      'source_grounding':'','question_executability':'','reference_answer_validity':''} for i in range(16)]}

def complete(doc):
    result=copy.deepcopy(doc)
    for row in result['items']:
        row.update(source_grounding='valid',question_executability='valid',reference_answer_validity='valid')
    return result

def test_disagreement_and_uncertainty_are_not_counted_as_valid():
    original=fixture();a=complete(original);b=complete(original)
    a['items'][0]['question_executability']='invalid'
    a['items'][1]['source_grounding']=b['items'][1]['source_grounding']='uncertain'
    a['items'][2]['reference_answer_validity']=b['items'][2]['reference_answer_validity']='invalid'
    counts,_=reconcile(original,a,b)
    assert counts=={'agreed_valid':13,'agreed_invalid':1,'uncertain_or_disagreement':2}

def test_rejects_changed_source_or_missing_question():
    original=fixture();a=complete(original);b=complete(original)
    a['items'][0]['source_messages'][0]['text']='changed'
    with pytest.raises(ValueError,match='source changed'):reconcile(original,a,b)
    a=complete(original);a['items'].pop()
    with pytest.raises(ValueError,match='cover'):reconcile(original,a,b)

def test_intake_requires_confirmation_and_publishes_exact_counts(tmp_path, monkeypatch):
    study=tmp_path/'study';study.mkdir(); original=fixture();a=complete(original);b=complete(original)
    a['items'][0]['question_executability']='invalid'
    for name,doc in [('reviewer-1-blank.json',original),('a.json',a),('b.json',b)]:
        (study/name).write_text(json.dumps(doc))
    report=tmp_path/'report.json';report.write_text(json.dumps({'product_followup':{'histories':4,'generated':16,'review_status':'pending'}}))
    confirmation=tmp_path/'confirmation.json';confirmation.write_text(json.dumps({'two_distinct_humans':False,'independent':True,'user_statement':'Test confirmation'}))
    out=tmp_path/'return';monkeypatch.setattr(ingest,'STUDY',study);monkeypatch.setattr(ingest,'REPORT',report)
    monkeypatch.setattr('sys.argv',['ingest','--reviewer-1',str(study/'a.json'),'--reviewer-2',str(study/'b.json'),'--confirmation',str(confirmation),'--output',str(out)])
    with pytest.raises(ValueError,match='explicit user confirmation'):ingest.main()
    assert not out.exists()
    confirmation.write_text(json.dumps({'two_distinct_humans':True,'independent':True,'user_statement':'Test confirmation'}))
    ingest.main()
    follow=json.loads(report.read_text())['product_followup']
    assert (follow['review_status'],follow['reviewed_valid'],follow['reviewed_unresolved'])==('human_confirmed',15,1)
    assert json.loads((out/'confirmation.json').read_text())['user_statement']=='Test confirmation'
