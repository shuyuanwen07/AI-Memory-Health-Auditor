"""Compare raw counts with frozen percentages, never rounded display values."""
import hashlib
import json
from fractions import Fraction
from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import AuditRunModel, ExperimentModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from app.schemas.acceptance import AcceptanceCheckRequest, AcceptanceCheckReport, AcceptanceMeasure, SavedEvidenceBinding
from app.schemas.formal_experiment import FormalAcceptanceProtocol
from app.schemas.annotation import TestQualityLabel
from app.schemas.research import annotation_fingerprint
from app.research.validity import ResearchValidityService
from app.services.formal_freeze import assert_formal_inputs_frozen
from app.services.formal_matrix import _stable_id


def measure(key, label, direction, threshold, numerator, denominator, definition, complete=True):
    value = 100 * numerator / denominator if denominator and complete else None
    if value is None:
        status = 'insufficient_evidence'
        reason = 'Complete reference coverage and a non-zero denominator are required.'
    else:
        ratio = Fraction(100 * numerator, denominator)
        boundary = Fraction(str(threshold))
        met = ratio >= boundary if direction == 'minimum' else ratio <= boundary
        status = 'meets_threshold' if met else 'threshold_not_met'
        reason = 'Compared using raw counts; displayed rounding does not change the decision.'
    return AcceptanceMeasure(key=key, label=label, direction=direction, threshold_percent=threshold,
                             numerator=numerator, denominator=denominator, observed_percent=value,
                             status=status, definition=definition, reason=reason)


def observed_category(verdict):
    classification = verdict.failure_classification or {}
    return verdict.failure_type if classification.get('status') == 'classified' else None


class AcceptanceCheckService:
    def calculate(self, db: Session, request: AcceptanceCheckRequest) -> AcceptanceCheckReport:
        audit = db.get(AuditRunModel, request.frozen_run_id)
        if audit is None:
            raise HTTPException(404, 'The saved experiment could not be found.')
        metadata = audit.reproducibility_metadata or {}
        if not metadata.get('formal_matrix_version') or not metadata.get('formal_acceptance_protocol'):
            raise HTTPException(422, 'This experiment has no frozen success criteria.')
        assert_formal_inputs_frozen(db, audit)
        protocol = FormalAcceptanceProtocol.model_validate(metadata['formal_acceptance_protocol'])
        if annotation_fingerprint(request.dataset) != protocol.dataset_fingerprint_sha256:
            raise HTTPException(422, 'The supplied dataset differs from the release used to freeze these criteria.')
        source = next((source for source in request.dataset.conversations
                       if _stable_id('SYN', request.dataset.dataset_id, request.dataset.dataset_version, source.conversation_id) == audit.conversation_id), None)
        if source is None:
            raise HTTPException(422, 'The saved experiment is not part of this dataset release.')
        for values in (request.predictions.memory_predictions, request.predictions.relationship_predictions,
                       request.predictions.test_assessments, request.predictions.evaluator_predictions):
            if any(item.conversation_id != source.conversation_id for item in values):
                raise HTTPException(422, 'Upload predictions for the selected scenario only. Other scenarios cannot be combined into this condition’s score.')
        scoped = request.model_copy(update={'dataset': request.dataset.model_copy(update={'conversations': [source]})})
        result = self.compare(scoped, protocol)
        binding = self.bind_saved_evidence(db, audit, source, request.predictions)
        result.saved_evidence_binding = binding
        result.saved_result_thresholds_met = result.all_thresholds_met and binding.status == 'verified'
        result.notice = ('Threshold arithmetic covers the selected scenario only. The protocol retains the full reviewed-release fingerprint; '
                         'metrics identify the scoped label contents. Saved-result acceptance requires exact answer and automated-verdict binding. '
                         'This does not verify independent authorship or held-out sampling and does not certify the experiment as complete.')
        return result

    @staticmethod
    def bind_saved_evidence(db, audit, source, predictions):
        experiment = db.get(ExperimentModel, audit.experiment_id)
        canonical_run = experiment.test_suite_source_run_id if experiment else None
        tests = {test.suite_test_id or test.id: test for test in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == audit.id))}
        replies = defaultdict(list)
        for reply in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == audit.id).order_by(TargetResponseModel.id)):
            replies[reply.test_id].append(reply)
        verdicts = defaultdict(list)
        for verdict in db.scalars(select(EvaluationResultModel).join(TargetResponseModel, EvaluationResultModel.response_id == TargetResponseModel.id).where(TargetResponseModel.run_id == audit.id).order_by(EvaluationResultModel.id)):
            verdicts[verdict.response_id].append(verdict)
        supplied = {item.response_id: item for item in predictions.evaluator_predictions}
        outcomes = dict(matched=0, missing=0, mismatched=0, ambiguous=0)
        receipt = []
        used = set()
        for reference in source.gold_evaluations:
            test = tests.get(_stable_id('T', canonical_run or '', reference.test_id))
            candidates = replies.get(test.id, []) if test else []
            prediction = supplied.get(reference.response_id)
            status = 'missing'
            reply = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1 or (reply and reply.id in used):
                status = 'ambiguous'
            elif reply:
                reviews = verdicts[reply.id]
                if len(reviews) > 1:
                    status = 'ambiguous'
                elif prediction is not None and reviews:
                    verdict = reviews[0]
                    status = 'matched' if (reply.response_text == reference.response_text and
                        verdict.test_id == test.id and prediction.passed == verdict.passed and
                        (prediction.failure_type.value if prediction.failure_type else None) == observed_category(verdict)) else 'mismatched'
                if status == 'matched':
                    used.add(reply.id)
            outcomes[status] += 1
            receipt.append({'run': audit.id, 'reference': reference.response_id, 'test': test.id if test else None,
                            'candidate_answers': [{'id': item.id, 'answer_sha256': hashlib.sha256(item.response_text.encode()).hexdigest(),
                            'verdicts': [{'id': review.id, 'passed': review.passed, 'failure_type': review.failure_type, 'classification': review.failure_classification} for review in verdicts[item.id]]} for item in candidates],
                            'response': reply.id if reply else None,
                            'answer_sha256': hashlib.sha256(reply.response_text.encode()).hexdigest() if reply else None,
                            'verdicts': [{'id': item.id, 'passed': item.passed, 'failure_type': item.failure_type, 'classification': item.failure_classification} for item in verdicts[reply.id]] if reply else [],
                            'prediction': prediction.model_dump(mode='json') if prediction else None, 'status': status})
        return SavedEvidenceBinding(status='verified' if source.gold_evaluations and outcomes['matched'] == len(source.gold_evaluations) else 'incomplete',
                                    condition_label=(audit.reproducibility_metadata or {}).get('condition_label', 'Saved condition'),
                                    reference_cases=len(source.gold_evaluations), **outcomes,
                                    receipt_sha256=hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    @staticmethod
    def compare(request, protocol):
        metrics = ResearchValidityService().calculate(request.dataset, request.predictions)
        criteria = protocol.criteria
        detection = metrics.failure_detection
        classification = metrics.failure_classification
        supplied = {(p.conversation_id, p.response_id): p.passed for p in request.predictions.evaluator_predictions}
        reference_passes = [(c.conversation_id, r.response_id) for c in request.dataset.conversations
                            for r in c.gold_evaluations if r.passed]
        false_positives = sum(supplied.get(key) is False for key in reference_passes)
        pass_coverage = all(key in supplied and supplied[key] is not None for key in reference_passes)
        tests = [t for c in request.dataset.conversations for t in c.gold_tests]
        valid_tests = sum(t.grounded and t.quality_label == TestQualityLabel.ACCEPT for t in tests)
        rows = [
            measure('failure_recall', 'Failure recall', 'minimum', criteria.failure_detection_recall_min_percent,
                    detection.detected, detection.reference_failures,
                    'Detected failures / all reference failures; uncertain failures remain in the denominator.', not detection.missing),
            measure('failure_classification', 'Failure classification', 'minimum', criteria.failure_classification_accuracy_min_percent,
                    classification.correct, classification.reference_failures,
                    'Correct failure categories / all reference failures, including missed and uncertain outcomes.', not classification.missing),
            measure('test_validity', 'Grounded test validity', 'minimum', criteria.test_validity_min_percent,
                    valid_tests, len(tests), 'Reference-grounded, accepted tests / all reference tests. This measures the supplied suite, not newly generated tests.',
                    not metrics.test_assessment_coverage.missing),
            measure('false_positive_rate', 'False-positive rate', 'maximum', criteria.false_positive_rate_max_percent,
                    false_positives, len(reference_passes), 'False failure findings / all reference passes.', pass_coverage),
        ]
        return AcceptanceCheckReport(protocol=protocol, metrics=metrics, measures=rows,
                                     all_thresholds_met=all(row.status == 'meets_threshold' for row in rows))
