"""Synthetic data verifies packet shape; no model or human labels are created."""
import hashlib
import json
from pathlib import Path
import pytest
from scripts.prepare_b_four_blind_review import prepare
from scripts.analyze_b_four_blind_review import analyze, verify_user_confirmation


def test_confirmation_is_bound_to_both_exact_human_returns(tmp_path):
    paths = [tmp_path / 'review-1.json', tmp_path / 'review-2.json']
    for path in paths:
        path.write_text(path.name)
    record = {'format': 'experiment-b-human-confirmation-v1', 'confirmed_by': 'user',
              'completed_by_humans': True,
              'review_sha256': [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]}
    verify_user_confirmation(record, paths)
    paths[1].write_text('changed after confirmation')
    with pytest.raises(ValueError):
        verify_user_confirmation(record, paths)
    with pytest.raises(ValueError):
        verify_user_confirmation({**record, 'completed_by_humans': False}, paths)


def fixture():
    path=Path('datasets/phase4-candidate-v1/source-histories.json')
    histories=json.loads(path.read_bytes())
    strategies=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance']
    protocol={'target':{'memory_strategies':strategies},'followup_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    scenarios=[]
    for history in histories:
        runs=[]
        for strategy in strategies:
            for repetition in (1,2,3):
                dims=['accuracy','freshness','conflict_resolution','appropriate_use']
                tests=[{'test_id':f'T{i}','dimension':dims[i],'prompt':f'Q{i}',
                        'expected_behavior':f'expected{i}','supporting_memory_ids':[f'M{i}']} for i in range(4)]
                responses=[{'response_id':f'R{i}','test_id':f'T{i}','response_text':f'answer{i}'} for i in range(4)]
                evaluations=[{'response_id':f'R{i}','passed':True} for i in range(4)]
                runs.append({'run_id':f'{history["scenario_id"]}-{strategy}-{repetition}',
                    'strategy':strategy,'repetition':repetition,'tests':tests,'responses':responses,'evaluations':evaluations})
        scenarios.append({'scenario_id':history['scenario_id'],'runs':runs})
    return {'status':'complete_automatic_collection','scenarios':scenarios},protocol,{'same_question_set_verified':True}


def test_complete_packet_hides_strategy_and_automatic_judgments():
    reviews,key=prepare(*fixture())
    assert len(reviews)==2 and len(key['mapping'])==144
    for review in reviews:
        assert review['format']=='b-four-strategy-human-review-v1'
        assert len(review['questions'])==12 and len(review['answers'])==144
        text=json.dumps(review)
        assert 'weak_first_hit' not in text and 'automatic_evaluation' not in text
        assert all(row['verdict'] is None for row in review['answer_reviews'])


def test_missing_run_is_rejected():
    state,protocol,addendum=fixture();state['scenarios'][0]['runs'].pop()
    with pytest.raises(ValueError,match='strategy repeat'):prepare(state,protocol,addendum)


def test_two_complete_synthetic_reviews_preserve_uncertainty():
    reviews,key=prepare(*fixture())
    material={'format':'b-four-strategy-blind-material-v1','histories':reviews[0]['histories'],
              'questions':reviews[0]['questions'],'answers':reviews[0]['answers']}
    for i,review in enumerate(reviews,1):
        review['reviewer_declaration']={'reviewer_label':f'synthetic {i}','completed_by_human':True,
            'completed_independently':True,'seen_current_automatic_results':False,'seen_other_review':False,
            'used_ai_assistance':False,'previously_seen_prior_b_results':None}
        for q in review['question_reviews']:q.update(valid=True,note='')
        for a in review['answer_reviews']:a.update(verdict='pass',failure_dimension=None,note='')
    reviews[1]['answer_reviews'][0].update(verdict='uncertain',note='Synthetic uncertainty')
    result=analyze(material,key,reviews)
    assert result['unresolved_answer_count']==1
    assert sum(s['counts']['pass'] for s in result['strategies'].values())==143
    assert result['current_results_blinded']
