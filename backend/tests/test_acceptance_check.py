import pytest
from app.research.acceptance import measure, AcceptanceCheckService
from app.schemas.acceptance import AcceptanceCheckRequest
from app.schemas.formal_experiment import FormalAcceptanceProtocol
from test_research_validity import dataset, predictions


@pytest.mark.parametrize('direction,threshold,numerator,denominator,status', [
    ('minimum',66.7,2,3,'threshold_not_met'),
    ('maximum',33.3,1,3,'threshold_not_met'),
    ('minimum',50,1,2,'meets_threshold'),
    ('maximum',50,1,2,'meets_threshold'),
    ('minimum',0,0,0,'insufficient_evidence'),
])
def test_thresholds_use_raw_counts(direction, threshold, numerator, denominator, status):
    assert measure('test','Test',direction,threshold,numerator,denominator,'Definition').status == status


def test_uncertain_failures_and_missing_passes_cannot_pass_frozen_thresholds():
    machine=predictions().model_dump()
    machine['evaluator_predictions'][2]['failure_type']='freshness'
    machine['evaluator_predictions'][3]['passed']=None
    machine['evaluator_predictions'].pop(0)
    request=AcceptanceCheckRequest(dataset=dataset(),predictions=machine,frozen_run_id='fixture')
    protocol=FormalAcceptanceProtocol(frozen_at='2026-10-12T00:00:00Z',dataset_fingerprint_sha256='fixture',runtime_source_sha256='fixture',criteria={'failure_detection_recall_min_percent':80,'failure_classification_accuracy_min_percent':80,'test_validity_min_percent':90,'false_positive_rate_max_percent':10})
    result=AcceptanceCheckService.compare(request,protocol)
    assert not result.all_thresholds_met
    assert [r.status for r in result.measures]==['threshold_not_met','threshold_not_met','threshold_not_met','insufficient_evidence']
    assert result.measures[0].observed_percent==50
    assert result.measures[2].observed_percent==80
    assert 'mapping' in result.notice


def test_complete_correct_evidence_meets_counts_without_claiming_certification():
    machine=predictions().model_dump()
    machine['evaluator_predictions'][2]['failure_type']='freshness'
    machine['evaluator_predictions'][3].update(passed=False,failure_type='conflict_resolution')
    request=AcceptanceCheckRequest(dataset=dataset(),predictions=machine,frozen_run_id='fixture')
    protocol=FormalAcceptanceProtocol(frozen_at='2026-10-12T00:00:00Z',dataset_fingerprint_sha256='fixture',runtime_source_sha256='fixture',criteria={'failure_detection_recall_min_percent':100,'failure_classification_accuracy_min_percent':100,'test_validity_min_percent':80,'false_positive_rate_max_percent':0})
    result=AcceptanceCheckService.compare(request,protocol)
    assert result.all_thresholds_met
    assert [(r.numerator,r.denominator) for r in result.measures]==[(2,2),(2,2),(4,5),(0,3)]
    assert 'does not certify' in result.notice
    machine['test_assessments'].pop()
    result=AcceptanceCheckService.compare(AcceptanceCheckRequest(dataset=dataset(),predictions=machine,frozen_run_id='fixture'),protocol)
    assert result.measures[2].status=='insufficient_evidence'
    assert not result.all_thresholds_met
