"""Read-only, evidence-bound policy ranking agreement for proposal Experiment C."""
from sqlalchemy import func, select

from app.benchmarks.semantic_review import SemanticReviewService
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from app.schemas.ranking_agreement import RankingAgreementReport, RankingSuiteResult
from app.schemas.target_profile import TargetMemoryProfile
from app.services.audit_comparison import compare_audit_evidence
import re


def suite_result(label, total, reference, candidate):
    return RankingSuiteResult(label=label, total=total,
        reference_correct=reference, candidate_correct=candidate,
        reference_percentage=round(100 * reference / total, 3),
        candidate_percentage=round(100 * candidate / total, 3),
        ordering="candidate_higher" if candidate > reference else "reference_higher" if reference > candidate else "tie")


class RankingAgreementService:
    VERSION = "bound-policy-ranking-v1"

    def analyse(self, db, request):
        if not request.reference_benchmark.source_authorised or not request.candidate_benchmark.source_authorised:
            raise ValueError("Confirm source authorisation for both benchmark assessment files before processing them.")
        before = db.get(AuditRunModel, request.reference_run_id)
        after = db.get(AuditRunModel, request.candidate_run_id)
        if not before or not after:
            raise ValueError("Choose two saved audits from this workspace.")
        if before.id == after.id or before.memory_strategy == after.memory_strategy:
            raise ValueError("Choose two different memory strategies, not a repeat of the same setting.")
        if {before.memory_strategy, after.memory_strategy} != {"weak_first_hit", "strong_rule_based"}:
            raise ValueError("Experiment C requires the frozen Weak first-hit and Strong rule-based policy pair.")
        if any(run.status != "COMPLETED" for run in (before, after)):
            raise ValueError("Both audits must be complete before comparing policy rankings.")
        if not before.experiment_id or before.experiment_id != after.experiment_id:
            raise ValueError("Choose audits from the same frozen experiment group.")
        if before.provider not in {"ollama", "openrouter"}:
            raise ValueError("Use saved real-model audits; the local rule baseline cannot establish model ranking agreement.")
        evidence = request.reference_benchmark.evidence
        candidate_evidence = request.candidate_benchmark.evidence
        for source in (evidence, candidate_evidence):
            provenance = source.dataset_provenance
            if (provenance is None or not provenance.dataset_version.strip()
                or not provenance.license.strip() or not provenance.citation.strip()):
                raise ValueError("Experiment C ranking qualification requires the dataset version, licence and citation for the local subset.")
            if (not source.adapter_version or not source.adapter_fingerprint_sha256
                or not re.fullmatch(r"[0-9a-f]{64}", source.adapter_fingerprint_sha256)):
                raise ValueError("Experiment C ranking qualification requires the adapter version and implementation fingerprint.")
            if not source.compatibility_limitations or any(not item.strip() for item in source.compatibility_limitations):
                raise ValueError("Experiment C ranking qualification requires the declared compatibility limitations.")
        if evidence.model_dump(mode="json") != candidate_evidence.model_dump(mode="json"):
            raise ValueError("Both benchmark assessments must use the same complete saved comparison evidence.")
        if request.reference_benchmark.strategy != before.memory_strategy or request.candidate_benchmark.strategy != after.memory_strategy:
            raise ValueError("Benchmark conditions must match the selected audit memory strategies in the same order.")
        for run in (before, after):
            if evidence.random_seed is None or run.random_seed != evidence.random_seed:
                raise ValueError("Both suites need the same recorded seed. Older benchmark files without seed provenance cannot establish compatibility.")
            if (run.provider, run.model, run.temperature, run.target_configuration,
                run.target_memory_capacity, run.target_memory_writer_version, run.target_system_adapter_version) != (
                evidence.provider.value, evidence.model, evidence.temperature, evidence.reader_configuration,
                evidence.target_memory_capacity, evidence.writer_version, evidence.target_adapter_version):
                raise ValueError("Target model, reader, memory capacity or implementation versions differ between suites.")
            metadata = run.reproducibility_metadata or {}
            if not evidence.audit_runtime_signature or metadata.get("audit_runtime_signature") != evidence.audit_runtime_signature:
                raise ValueError("The suites need the same saved software snapshot. Legacy files with unknown implementation provenance cannot establish compatibility.")
            if run.target_system_adapter != "controlled-memory" or run.target_memory_writer != "rule_based" or run.memory_maintenance_policy != "update_aware_consolidation":
                raise ValueError("Use the controlled target with the benchmark's recorded memory preparation policy.")
            if metadata.get("assessment_source_run_id") or metadata.get("shared_answer_source_run_id") or metadata.get("intervention"):
                raise ValueError("Use original target executions without additional diagnostic interventions or saved-answer reassessment.")
            profile = metadata.get("target_memory_profile")
            if not profile:
                raise ValueError("The audit has no frozen memory settings. Create a comparison with recorded settings.")
            # Labels describe presentation; all behavioural profile fields must match.
            if TargetMemoryProfile(**profile).model_dump(exclude={"label", "version"}) != evidence.target_memory_profile.model_dump(exclude={"label", "version"}):
                raise ValueError("Frozen context budgets, instructions or memory settings differ between suites.")
        comparison = compare_audit_evidence(db, before, after)
        if comparison["setting_differences"]:
            raise ValueError("The audit pair changes more than memory strategy. Choose a controlled strategy comparison.")
        pairs = comparison["paired_tests"]
        sizes = [db.scalar(select(func.count()).select_from(TestCaseModel).where(TestCaseModel.run_id == run.id)) for run in (before, after)]
        if not pairs or any(size != len(pairs) for size in sizes):
            raise ValueError("Every frozen audit question needs a matching reply and comparable decided assessment in both conditions.")
        # Profiles can omit the historical output limit; actual receipts must
        # still establish one common, explicit budget for every scored reply.
        limits = set()
        for condition in evidence.conditions:
            if condition.strategy not in {before.memory_strategy, after.memory_strategy}:
                continue
            for case in condition.cases:
                limits.add(self._receipt_limit(case.execution_metadata.model_dump(), before.provider))
        for run in (before, after):
            responses = self._evaluated_responses(db, run.id)
            if len(responses) != len(pairs):
                raise ValueError("Every compared answer needs its exact saved execution receipt.")
            for response in responses:
                if (response.model, response.temperature) != (run.model, run.temperature):
                    raise ValueError("A saved answer used different model settings from its audit.")
                limits.add(self._receipt_limit(response.execution_metadata or {}, run.provider))
        if len(limits) != 1:
            raise ValueError("Actual answer length limits differ between the compared replies. Rerun with the same explicit token budget.")
        declared_limit = evidence.target_memory_profile.output_token_limit
        if declared_limit is not None and limits != {declared_limit}:
            raise ValueError("Actual answer length limits do not match the frozen memory configuration.")
        service = SemanticReviewService()
        left = service.analyse(request.reference_benchmark)
        right = service.analyse(request.candidate_benchmark)
        if left.pending or right.pending:
            raise ValueError("Complete semantic assessment coverage for both benchmark conditions before checking ranking agreement.")
        if (left.evaluator_model, left.evaluator_revision) != (right.evaluator_model, right.evaluator_revision):
            raise ValueError("Both benchmark conditions must use the same semantic evaluator model and revision.")
        suites = [suite_result("Audit questions", len(pairs), sum(p["before"]["passed"] for p in pairs), sum(p["after"]["passed"] for p in pairs)),
                  suite_result("Benchmark questions", left.total, left.correct, right.correct)]
        first, second = (s.ordering for s in suites)
        agreement = ("both_tied" if first == second == "tie" else "inconclusive_tie" if "tie" in {first, second}
                     else "consistent" if first == second else "reversed")
        return RankingAgreementReport(version=self.VERSION, provider=before.provider, model=before.model,
            reference_strategy=before.memory_strategy, candidate_strategy=after.memory_strategy,
            output_token_limit=next(iter(limits)),
            suites=suites, agreement=agreement, reference_run_id=before.id, candidate_run_id=after.id,
            dataset_provenance=evidence.dataset_provenance,
            source_fingerprint_sha256=evidence.source_fingerprint_sha256,
            adapter_version=evidence.adapter_version,
            adapter_fingerprint_sha256=evidence.adapter_fingerprint_sha256,
            compatibility_limitations=evidence.compatibility_limitations,
            benchmark_evidence_fingerprint_sha256=left.evidence_fingerprint_sha256,
            reference_evaluation_fingerprint_sha256=left.evaluation_fingerprint_sha256,
            candidate_evaluation_fingerprint_sha256=right.evaluation_fingerprint_sha256,
            notice="Descriptive relative ordering across two different question sets, not a comparison of absolute scores or proof of general reliability. Dataset version, licence, citation, source file and imported semantic labels are caller-declared; adapter compatibility limits are listed above. Independent human review, representative subsets and repeated trials are still required. No model calls, training or human labels were created by this check.")

    @staticmethod
    def _evaluated_responses(db, run_id):
        return db.scalars(select(TargetResponseModel)
            .join(EvaluationResultModel, EvaluationResultModel.response_id == TargetResponseModel.id)
            .join(TestCaseModel, TestCaseModel.id == EvaluationResultModel.test_id)
            .where(TestCaseModel.run_id == run_id, TargetResponseModel.run_id == run_id,
                   TargetResponseModel.test_id == TestCaseModel.id)).all()

    @staticmethod
    def _receipt_limit(receipt, provider):
        limit = receipt.get("requested_output_token_limit")
        if (receipt.get("response_source") != provider
            or type(receipt.get("request_attempts")) is not int or receipt["request_attempts"] < 1
            or receipt.get("shared_source_run_id") or receipt.get("shared_source_response_id")):
            raise ValueError("Use original model-call receipts, not reused or unverified responses.")
        if type(limit) is not int or not 1 <= limit <= 8192:
            raise ValueError("Actual answer length limits are unknown. Rerun both suites with an explicit token budget.")
        return limit
