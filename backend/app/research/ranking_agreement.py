"""Read-only, evidence-bound policy ranking agreement for proposal Experiment C."""
from sqlalchemy import func, select
from fractions import Fraction
from collections import Counter
import json
from statistics import stdev

from app.benchmarks.semantic_review import SemanticReviewService
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from app.schemas.ranking_agreement import (
    RankingAgreementReport, RankingSuiteResult, RankingDimensionResult,
    RepeatedRankingReport, RepeatedRankingSuite, RankingTrialResult,
)
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.schemas.domain import Dimension
from app.schemas.target_profile import TargetMemoryProfile
from app.services.audit_comparison import compare_audit_evidence
import re


def suite_result(label, total, reference, candidate):
    return RankingSuiteResult(label=label, total=total,
        reference_correct=reference, candidate_correct=candidate,
        reference_percentage=round(100 * reference / total, 3),
        candidate_percentage=round(100 * candidate / total, 3),
        ordering="candidate_higher" if candidate > reference else "reference_higher" if reference > candidate else "tie")


def audit_suite_result(pairs):
    groups = {dimension: [] for dimension in Dimension}
    for pair in pairs:
        try:
            groups[Dimension(pair["dimension"])].append(pair)
        except (KeyError, ValueError):
            raise ValueError("Every paired audit question needs its recorded memory dimension.") from None
    dimensions = []
    fractions = {key: [] for key in ("before", "after")}
    for dimension, rows in groups.items():
        counts = {key: sum(row[key]["passed"] for row in rows) for key in fractions}
        for key in fractions:
            if rows:
                fractions[key].append(Fraction(counts[key], len(rows)))
        dimensions.append(RankingDimensionResult(
            dimension=dimension, total=len(rows), reference_correct=counts["before"], candidate_correct=counts["after"],
            reference_percentage=round(100 * counts["before"] / len(rows), 3) if rows else None,
            candidate_percentage=round(100 * counts["after"] / len(rows), 3) if rows else None,
        ))
    complete = all(rows for rows in groups.values())
    left = sum(fractions["before"], Fraction()) / len(Dimension) if complete else None
    right = sum(fractions["after"], Fraction()) / len(Dimension) if complete else None
    return RankingSuiteResult(
        label="Audit questions", total=len(pairs),
        reference_correct=sum(row.reference_correct for row in dimensions),
        candidate_correct=sum(row.candidate_correct for row in dimensions),
        reference_percentage=round(float(left * 100), 3) if left is not None else None,
        candidate_percentage=round(float(right * 100), 3) if right is not None else None,
        score_basis="dimension_macro_average", dimensions=dimensions,
        ordering="unmeasured" if not complete else "candidate_higher" if right > left else "reference_higher" if left > right else "tie",
    )


class RankingAgreementService:
    VERSION = "bound-policy-ranking-v2"

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
        suites = [audit_suite_result(pairs),
                  suite_result("Benchmark questions", left.total, left.correct, right.correct)]
        first, second = (s.ordering for s in suites)
        agreement = ("inconclusive_missing_dimensions" if "unmeasured" in {first, second}
                     else "both_tied" if first == second == "tie" else "inconclusive_tie" if "tie" in {first, second}
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
            experiment_id=before.experiment_id,
            audit_suite_fingerprint_sha256=LongMemEvalDeterministicRunner._fingerprint(sorted([
                {key: pair.get(key) for key in ('suite_test_id', 'prompt', 'dimension', 'expected_behavior')}
                for pair in pairs], key=lambda row: json.dumps(row, sort_keys=True))),
            audit_configuration_fingerprint_sha256=LongMemEvalDeterministicRunner._fingerprint({
                'settings': {key: getattr(before, key, None) for key in (
                    'conversation_id', 'provider', 'model', 'temperature', 'random_seed', 'target_configuration',
                    'target_memory_capacity', 'target_memory_writer_version', 'target_system_adapter_version',
                    'evaluator_provider', 'evaluator_model')},
                'profile': TargetMemoryProfile(**(before.reproducibility_metadata or {})['target_memory_profile']).model_dump(exclude={'label', 'version'}),
                'runtime': (before.reproducibility_metadata or {}).get('audit_runtime_signature'),
                'assessors': sorted({str(pair['before'].get('evaluator')) for pair in pairs}),
            }),
            benchmark_configuration_fingerprint_sha256=left.configuration_fingerprint_sha256,
            evaluator_model=left.evaluator_model, evaluator_revision=left.evaluator_revision,
            notice="Descriptive relative ordering across two different question sets, not a comparison of absolute scores or proof of general reliability. Auditor ordering uses the equal-weight macro-average of all four dimensions; missing dimensions make ranking unmeasured. Benchmark percentages remain response accuracy. Dataset version, licence, citation, source file and imported semantic labels are caller-declared; adapter compatibility limits are listed above. Independent human review, representative subsets and repeated trials are still required. No model calls, training or human labels were created by this check.")

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


class RepeatedRankingService:
    """Read-only repeated analysis; preserve invalid and missing planned trials."""

    VERSION = "repeated-bound-policy-ranking-v1"

    @staticmethod
    def _compatibility(report):
        fields = ('provider', 'model', 'reference_strategy', 'candidate_strategy', 'output_token_limit',
                  'experiment_id', 'source_fingerprint_sha256', 'adapter_version', 'adapter_fingerprint_sha256',
                  'audit_suite_fingerprint_sha256', 'audit_configuration_fingerprint_sha256',
                  'benchmark_configuration_fingerprint_sha256', 'evaluator_model', 'evaluator_revision')
        return {**{key: getattr(report, key) for key in fields},
                'dataset_provenance': report.dataset_provenance.model_dump(mode='json'),
                'compatibility_limitations': report.compatibility_limitations}

    @staticmethod
    def _score(suite, candidate=False):
        key = 'candidate_correct' if candidate else 'reference_correct'
        if suite.score_basis == 'dimension_macro_average':
            if len(suite.dimensions) != len(Dimension) or any(row.total == 0 for row in suite.dimensions):
                raise ValueError('Repeated Auditor ranking requires all four measured dimensions.')
            return sum((Fraction(getattr(row, key), row.total) for row in suite.dimensions), Fraction()) / len(Dimension)
        return Fraction(getattr(suite, key), suite.total)

    def analyse(self, db, request):
        comparisons = [trial.comparison for trial in request.trials if trial.comparison is not None]
        if any(not item.reference_benchmark.source_authorised or not item.candidate_benchmark.source_authorised
               for item in comparisons):
            raise ValueError('Confirm source authorisation for every repeated benchmark assessment before processing it.')
        if len(json.dumps(request.model_dump(mode='json')).encode()) > 10_000_000:
            raise ValueError('Choose a repeated analysis package smaller than 10 MB.')
        benchmark_runs = [item.reference_benchmark.evidence.run_id for item in comparisons]
        if len(benchmark_runs) != len(set(benchmark_runs)):
            raise ValueError('A saved benchmark execution cannot be counted as more than one repeated trial.')
        by_id = {trial.trial_id: trial for trial in request.trials}
        results, anchor = [], None
        for trial_id in request.planned_trial_ids:
            trial = by_id.get(trial_id)
            if trial is None or trial.comparison is None:
                results.append(RankingTrialResult(trial_id=trial_id, status='missing',
                    reason=trial.unavailable_reason if trial and trial.unavailable_reason else 'No comparison evidence was supplied for this planned trial.'))
                continue
            try:
                report = RankingAgreementService().analyse(db, trial.comparison)
                compatible = self._compatibility(report)
                if anchor is not None and compatible != anchor:
                    raise ValueError('Repeated trials must use the same frozen audit suite, source subset, model, settings, adapter and evaluation standard.')
                if anchor is None:
                    anchor = compatible
                status = 'unmeasured' if report.agreement == 'inconclusive_missing_dimensions' else 'measured'
                results.append(RankingTrialResult(trial_id=trial_id, status=status, report=report,
                    reference_run_id=trial.comparison.reference_run_id, candidate_run_id=trial.comparison.candidate_run_id,
                    reason='The Auditor did not measure all four dimensions.' if status == 'unmeasured' else None))
            except ValueError as error:
                results.append(RankingTrialResult(trial_id=trial_id, status='invalid', reason=str(error),
                    reference_run_id=trial.comparison.reference_run_id, candidate_run_id=trial.comparison.candidate_run_id))
        measured = [row.report for row in results if row.status == 'measured']
        complete = len(measured) == len(request.planned_trial_ids)
        statuses = Counter(row.status for row in results)
        agreements = Counter(report.agreement for report in measured)
        directional = agreements['consistent'] + agreements['reversed']
        suites = []
        if measured:
            for index, first in enumerate(measured[0].suites):
                left = [self._score(report.suites[index]) for report in measured]
                right = [self._score(report.suites[index], True) for report in measured]
                left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
                suites.append(RepeatedRankingSuite(
                    label=first.label, score_basis=first.score_basis, measured_trials=len(measured),
                    reference_mean_percentage=round(float(left_mean * 100), 3) if complete else None,
                    candidate_mean_percentage=round(float(right_mean * 100), 3) if complete else None,
                    reference_standard_deviation=round(stdev([float(value * 100) for value in left]), 3) if complete and len(left) > 1 else None,
                    candidate_standard_deviation=round(stdev([float(value * 100) for value in right]), 3) if complete and len(right) > 1 else None,
                    ordering='unmeasured' if not complete else 'candidate_higher' if right_mean > left_mean else 'reference_higher' if left_mean > right_mean else 'tie',
                ))
        return RepeatedRankingReport(
            version=self.VERSION, status='complete' if complete else 'partial',
            planned_trial_ids=request.planned_trial_ids,
            plan_fingerprint_sha256=LongMemEvalDeterministicRunner._fingerprint([
                {'trial_id':trial_id,
                 'reference_run_id':by_id[trial_id].comparison.reference_run_id if trial_id in by_id and by_id[trial_id].comparison else None,
                 'candidate_run_id':by_id[trial_id].comparison.candidate_run_id if trial_id in by_id and by_id[trial_id].comparison else None,
                 'benchmark_run_id':by_id[trial_id].comparison.reference_benchmark.evidence.run_id if trial_id in by_id and by_id[trial_id].comparison else None,
                 'source_fingerprint_sha256':by_id[trial_id].comparison.reference_benchmark.evidence.source_fingerprint_sha256 if trial_id in by_id and by_id[trial_id].comparison else None}
                for trial_id in request.planned_trial_ids]),
            provider=anchor['provider'] if anchor else None, model=anchor['model'] if anchor else None,
            reference_strategy=anchor['reference_strategy'] if anchor else None,
            candidate_strategy=anchor['candidate_strategy'] if anchor else None,
            trials=results, planned_trials=len(results), measured_trials=len(measured),
            invalid_trials=statuses['invalid'], missing_trials=statuses['missing'], unmeasured_trials=statuses['unmeasured'],
            directional_trials=directional, consistent_trials=agreements['consistent'], reversed_trials=agreements['reversed'],
            both_tied_trials=agreements['both_tied'], inconclusive_tie_trials=agreements['inconclusive_tie'],
            ranking_agreement_percentage=round(100 * agreements['consistent'] / directional, 3) if complete and directional else None,
            suites=suites,
            notice='Descriptive repeated analysis of saved original executions. Each planned repeat has equal weight; Auditor scores are four-dimension macro-averages and benchmark scores are response accuracy. Ties are reported separately from directional agreement. Missing, invalid or unmeasured planned trials prevent aggregate scores and agreement rates. The plan is caller-declared at analysis time, not a verified pre-registration or server freeze. Independent labels, a genuinely predeclared study plan and an authorised representative LongMemEval subset remain required. This analysis creates no model calls, database records or human labels.',
        )
