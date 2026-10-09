"""Bind imported upstream-format assessments to the exact saved replies.

The server performs no inference and makes no authenticity claim about a
user-supplied evaluation file or declared upstream revision.
"""
import json

from app.benchmarks.live import LiveBenchmarkRunner
from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.schemas.semantic_review import (
    SemanticReviewedCase, SemanticReviewReport, SemanticReviewRequest, SemanticSummary,
)


class SemanticReviewService:
    VERSION = "bound-upstream-review-v1"

    def analyse(self, request: SemanticReviewRequest) -> SemanticReviewReport:
        if len(json.dumps(request.model_dump(mode="json"), ensure_ascii=False).encode()) > 10_000_000:
            raise ValueError("Choose a saved pilot package smaller than 10 MB.")
        evidence = request.evidence
        source_hash = LongMemEvalDeterministicRunner._fingerprint(request.source)
        if source_hash != evidence.source_fingerprint_sha256:
            raise ValueError("The source file does not match this saved comparison.")
        references, _ = LongMemEvalAdapter().adapt(request.source)
        if len(references) > 20 or not 1 <= len(evidence.conditions) <= 4:
            raise ValueError("Choose a saved pilot with at most 20 questions and four conditions.")
        gold = {c.case_id: c for c in references}
        names = [c.strategy for c in evidence.conditions]
        if len(set(names)) != len(names):
            raise ValueError("Saved comparison contains duplicate conditions.")
        if request.strategy not in names:
            raise ValueError("Choose a condition from this saved comparison.")
        # Verify every condition, not only the selected one. This also prevents
        # a partial evidence subset from silently changing the denominator.
        for condition in evidence.conditions:
            ids = [c.case_id for c in condition.cases]
            if len(set(ids)) != len(ids) or set(ids) != set(gold):
                raise ValueError("Every saved condition must contain each source question exactly once.")
            for case in condition.cases:
                reference = gold[case.case_id]
                if (case.question, case.expected_answer, case.category) != (
                    reference.question, reference.expected_answer, reference.category,
                ):
                    raise ValueError("Saved questions, references or categories differ from the source.")
                if case.lexical_match != LiveBenchmarkRunner._lexical_match(case.expected_answer, case.response_text):
                    raise ValueError("Saved lexical assessments do not match the saved replies.")
        condition = next(c for c in evidence.conditions if c.strategy == request.strategy)
        saved = {c.case_id: c for c in condition.cases}
        assessed = {}
        models = set()
        for row in request.rows:
            if row.question_id in assessed:
                raise ValueError("Evaluation contains a duplicate question; no duplicate was silently discarded.")
            if row.question_id not in saved:
                raise ValueError("Evaluation contains a question absent from this saved condition.")
            if row.hypothesis != saved[row.question_id].response_text:
                raise ValueError("An evaluated hypothesis differs from the exact saved reply. Choose the matching condition and result file.")
            assessed[row.question_id] = row.autoeval_label.label
            models.add(row.autoeval_label.model)
        if len(models) != 1:
            raise ValueError("Use one evaluator model per imported assessment file.")
        cases = [SemanticReviewedCase(case_id=c.case_id, category=c.category, question=c.question,
            expected_answer=c.expected_answer, response_text=c.response_text, lexical_match=c.lexical_match,
            semantic_correct=assessed.get(c.case_id)) for c in condition.cases]
        reviewed = len(assessed)
        correct = sum(assessed.values())
        categories = []
        for category in sorted({c.category for c in cases}):
            group = [c for c in cases if c.category == category]
            count = sum(c.semantic_correct is not None for c in group)
            passed = sum(c.semantic_correct is True for c in group)
            categories.append(SemanticSummary(category=category, total=len(group), reviewed=count, correct=passed,
                percentage=round(100*passed/len(group), 2) if count == len(group) else None))
        return SemanticReviewReport(version=self.VERSION, run_id=evidence.run_id, strategy=request.strategy,
            source_fingerprint_sha256=source_hash, configuration_fingerprint_sha256=evidence.configuration_fingerprint_sha256,
            evidence_fingerprint_sha256=LongMemEvalDeterministicRunner._fingerprint(evidence.model_dump(mode="json")),
            evaluation_fingerprint_sha256=LongMemEvalDeterministicRunner._fingerprint([r.model_dump(mode="json") for r in request.rows]),
            evaluator_revision=request.evaluator_revision, evaluator_model=next(iter(models)),
            total=len(cases), reviewed=reviewed, correct=correct, pending=len(cases)-reviewed,
            percentage=round(100*correct/len(cases), 2) if reviewed == len(cases) else None,
            lexical_disagreements=sum(c.semantic_correct is not None and c.semantic_correct != c.lexical_match for c in cases),
            cases=cases, categories=categories,
            notice="Imported automated assessments in LongMemEval upstream output format, bound to this source and exact saved replies. File origin, evaluator revision, model execution and label accuracy are user-declared, not independently verified. No model was called by this import and no human labels were created. Incomplete coverage has no overall score; complete pilot coverage is not an official full-benchmark score.")
