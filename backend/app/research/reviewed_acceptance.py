"""Use post-execution review records without changing pre-execution thresholds."""
import hashlib
import json
from collections import Counter
from sqlalchemy import select
from fastapi import HTTPException
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel, EvaluationHumanReviewModel
from app.schemas.acceptance import ReviewedSavedAcceptanceReport, SavedReviewCoverage
from app.schemas.formal_experiment import FormalAcceptanceProtocol
from app.research.acceptance import measure
from app.services.formal_freeze import assert_formal_inputs_frozen


class ReviewedSavedAcceptanceService:
    def calculate(self, db, run_id):
        # Import the canonical resolution rules lazily to avoid route import cycles.
        from app.api.routes import evaluation_review_items_for
        audit = db.get(AuditRunModel, run_id)
        if not audit:
            raise HTTPException(404, 'The saved experiment could not be found.')
        metadata = audit.reproducibility_metadata or {}
        if not metadata.get('formal_matrix_version') or not metadata.get('formal_acceptance_protocol'):
            raise HTTPException(422, 'This experiment has no frozen success criteria.')
        assert_formal_inputs_frozen(db, audit)
        protocol = FormalAcceptanceProtocol.model_validate(metadata['formal_acceptance_protocol'])
        items = evaluation_review_items_for(run_id, db)
        tests = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id).order_by(TestCaseModel.id)))
        responses = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id).order_by(TargetResponseModel.id)))
        evaluations = list(db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run_id).order_by(EvaluationResultModel.id)))
        raw_reviews = list(db.scalars(select(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.evaluation_id.in_([row.id for row in evaluations])).order_by(EvaluationHumanReviewModel.id)))
        reply_counts = Counter(row.test_id for row in responses)
        verdict_counts = Counter(row.test_id for row in evaluations)
        ambiguous = {test.id for test in tests if reply_counts[test.id] > 1 or verdict_counts[test.id] > 1}
        safe = [item for item in items if item.test.test_id not in ambiguous]
        resolved = [item for item in safe if item.human_review is not None]
        complete = bool(tests) and len(resolved) == len(tests)
        failures = [item for item in resolved if not item.human_review.human_passed]
        passes = [item for item in resolved if item.human_review.human_passed]
        detected = sum(item.automated.passed is False for item in failures)
        correct_categories = sum(item.automated.passed is False and item.human_review.human_failure_type is not None
                                 and item.automated.failure_type == item.human_review.human_failure_type for item in failures)
        missing_categories = sum(item.human_review.human_failure_type is None for item in failures)
        independent = sum(item.human_review.review_role.value == 'adjudication' and item.independent_reviewer_count >= 2 for item in resolved)
        valid_tests = sum(test.quality_status == 'accepted' and test.grounding_status == 'grounded' for test in tests)
        c = protocol.criteria
        rows = [
            measure('failure_recall', 'Failure recall', 'minimum', c.failure_detection_recall_min_percent,
                    detected, len(failures), 'Detected failures / resolved reference failures; uncertain decisions remain unsuccessful.', complete),
            measure('failure_classification', 'Failure classification', 'minimum', c.failure_classification_accuracy_min_percent,
                    correct_categories, len(failures), 'Correct failure categories / resolved reference failures, including missed failures.', complete and not missing_categories),
            measure('test_validity', 'Grounded test validity', 'minimum', c.test_validity_min_percent,
                    valid_tests, len(tests), 'Grounded, accepted tests in the frozen reviewed suite / all saved tests. This is not new-generator validation.'),
            measure('false_positive_rate', 'False-positive rate', 'maximum', c.false_positive_rate_max_percent,
                    sum(item.automated.passed is False for item in passes), len(passes),
                    'False failure findings / resolved reference passes.', complete and all(item.automated.passed is not None for item in passes)),
        ]
        from app.api.routes import human_review_schema
        receipt = {'run': audit.id,
                   'recorded_review_versions': [human_review_schema(row).model_dump(mode='json') | {'run_id': row.run_id} for row in raw_reviews], 'protocol': protocol.model_dump(mode='json'),
                   'answers': [{'id': row.id, 'test': row.test_id, 'sha256': hashlib.sha256(row.response_text.encode()).hexdigest()} for row in responses],
                   'verdicts': [{'id': row.id, 'response': row.response_id, 'test': row.test_id, 'passed': row.passed, 'category': row.failure_type, 'classification': row.failure_classification} for row in evaluations],
                   'reviews': [item.model_dump(mode='json', include={'human_review', 'human_reviews'}) for item in sorted(items, key=lambda row: row.test.test_id)]}
        met = all(row.status == 'meets_threshold' for row in rows)
        return ReviewedSavedAcceptanceReport(protocol=protocol, measures=rows, all_thresholds_met=met,
            saved_result_thresholds_met=met and complete,
            review_coverage=SavedReviewCoverage(expected_tests=len(tests), saved_answers=sum(reply_counts[t.id] == 1 for t in tests),
                resolved_labels=len(resolved), missing_labels=len(tests)-len(resolved), ambiguous_tests=len(ambiguous),
                independently_adjudicated=independent, failure_categories_missing=missing_categories),
            receipt_sha256=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest())
