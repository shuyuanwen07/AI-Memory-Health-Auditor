"""Compare saved audits only by their frozen canonical test identities."""

from collections import Counter
from sqlalchemy import select
from app.models import TestCaseModel, EvaluationResultModel, TargetResponseModel


def profile_description(profile):
    if not profile:
        return "Original defaults"
    return (f"{profile.get('label', 'Memory configuration')} · version {profile.get('version', 1)} · "
        f"up to {profile.get('max_retrieved_records', 50)} records / {profile.get('context_character_budget', 16000)} characters · "
        f"project separation {'on' if profile.get('isolate_project_scope') else 'off'} · "
        f"current-fact preference {'on' if profile.get('prefer_current_state') else 'off'} · "
        f"answer limit {profile.get('output_token_limit') or 'not recorded'} tokens · "
        f"instructions: {profile.get('additional_instructions') or 'default'}")

def assessment_signature(run, evaluation):
    """Use saved evidence, never the currently installed evaluator version."""
    implementation = evaluation.evaluator
    if not implementation:
        return None
    meter = getattr(evaluation, "judge_execution", None) or {}
    cross_check = meter.get("cross_check_version")
    # Every hybrid implementation needs the saved cross-check identity.
    # Equal missing values do not establish equal evidence-rule standards,
    # including later judge versions and cloud providers.
    if implementation.startswith("llm-judge-") and not cross_check:
        return None
    return (implementation, getattr(run, "evaluator_provider", None),
            getattr(run, "evaluator_model", None), meter.get("provider"),
            meter.get("model"), cross_check)


def compare_audit_evidence(db, before, after):
    warnings = []
    reused = any((run.reproducibility_metadata or {}).get("study_role") == "saved_answer_reassessment"
                 or (run.reproducibility_metadata or {}).get("assessment_source_run_id")
                 or (run.reproducibility_metadata or {}).get("shared_answer_source_run_id")
                 for run in (before, after))
    answer_lineage = []
    controls = [
        ("conversation_id", "Source conversation"),
        ("provider", "Target provider"),
        ("model", "Target model"),
        ("target_configuration", "Reader behaviour policy"),
        ("temperature", "Temperature"),
        ("evaluator_provider", "Evaluator provider"),
        ("evaluator_model", "Evaluator model"),
        ("retrieval_mode", "Memory retrieval method"),
        ("retrieval_provider", "Memory retrieval service"),
        ("retrieval_model", "Memory retrieval model"),
        ("target_memory_writer", "Memory writer"),
        ("target_memory_writer_version", "Memory writer version"),
        ("memory_maintenance_policy", "Memory maintenance"),
        ("target_memory_capacity", "Memory capacity"),
    ]
    differences = []
    for field, label in controls:
        left, right = getattr(before, field, None), getattr(after, field, None)
        if left != right:
            differences.append(
                {"field": field, "label": label, "before": left, "after": right}
            )
    writer_equivalence_unknown = False
    def model_writer(run):
        kind = getattr(run, "target_memory_writer", None)
        return getattr(kind, "value", kind) == "llm_structured"
    if any(model_writer(run) for run in (before, after)):
        for source_field, field, label in (("pipeline_provider", "memory_writer_provider", "Memory writer service"),
                                           ("pipeline_model", "memory_writer_model", "Memory writer model")):
            left = getattr(before, source_field, None) if model_writer(before) else "Not used by rule writer"
            right = getattr(after, source_field, None) if model_writer(after) else "Not used by rule writer"
            if left != right:
                differences.append({"field": field, "label": label, "before": left, "after": right})
        warnings.append("Model-written memory can differ between original executions even with matching writer settings. Check the original stored-memory evidence before attributing answer changes to retrieval alone.")
        writer_equivalence_unknown = any(model_writer(run) and (not getattr(run, "pipeline_provider", None) or not getattr(run, "pipeline_model", None)) for run in (before, after))
        if writer_equivalence_unknown:
            warnings.append("The model memory writer's service or model is not recorded on every relevant run. Writer equivalence cannot be established from these records.")
    for key, label in (("target_memory_profile", "Memory configuration"), ("intervention", "Diagnostic intervention"), ("target_system_adapter", "Target system")):
        left = (before.reproducibility_metadata or {}).get(key)
        right = (after.reproducibility_metadata or {}).get(key)
        if left != right:
            differences.append({"field": key, "label": label, "before": profile_description(left) if key == "target_memory_profile" else str(left or "None"), "after": profile_description(right) if key == "target_memory_profile" else str(right or "None")})
    if any((run.reproducibility_metadata or {}).get("study_role") in {"diagnostic_intervention", "adaptive_follow_up", "repair_comparison"} for run in (before, after)):
        warnings.append("Exploratory diagnostic conditions: this comparison is not evidence of held-out performance improvement.")
    if before.target_configuration != after.target_configuration:
        warnings.append("The reader behaviour policy also changes. This comparison measures the combined configuration change; it does not isolate retrieval strategy alone.")
    if differences:
        warnings.append(
            "Other settings differ. Review the recorded changes before attributing score differences to a particular mechanism."
        )
    if not before.experiment_id or before.experiment_id != after.experiment_id:
        warnings.append("These runs do not share a frozen experiment group.")
    if (
        before.memory_strategy == after.memory_strategy
        and getattr(before, "retrieval_mode", "fixed") == getattr(after, "retrieval_mode", "fixed")
        and getattr(before, "retrieval_provider", None) == getattr(after, "retrieval_provider", None)
        and getattr(before, "retrieval_model", None) == getattr(after, "retrieval_model", None)
        and before.target_configuration == after.target_configuration
        and (before.reproducibility_metadata or {}).get("target_memory_profile", {}) == (after.reproducibility_metadata or {}).get("target_memory_profile", {})
    ):
        if before.provider != after.provider or before.model != after.model:
            warnings.append("The saved memory configuration matches. This compares different target models or providers, rather than a memory policy change.")
        elif differences:
            warnings.append("The saved memory configuration matches, but other recorded settings differ. Check those changes when interpreting the results.")
        elif not writer_equivalence_unknown:
            warnings.append("Both runs use the same saved configuration. This is a repeat comparison, not a recorded policy change.")
    if any(
        (run.reproducibility_metadata or {}).get("human_validation") == "pending"
        for run in (before, after)
    ):
        warnings.append(
            "This synthetic pilot was pre-reviewed by AI. Independent human validation is still pending."
        )

    def rows(run_id):
        tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id).order_by(TestCaseModel.id)).all()
        evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
        responses = {row.id: row for row in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)).all()}
        counts = Counter(row.test_id for row in evaluations)
        key_counts = Counter(test.comparison_test_id or test.suite_test_id or test.id for test in tests)
        by_test = {row.test_id: row for row in evaluations}
        result = {}
        excluded = 0
        for test in tests:
            key = test.comparison_test_id or test.suite_test_id or test.id
            evaluation = by_test.get(test.id) if counts[test.id] == 1 and key_counts[key] == 1 else None
            response = responses.get(evaluation.response_id) if evaluation else None
            if response is None or response.test_id != test.id or response.run_id != run_id:
                evaluation = response = None
                excluded += 1
            result[key] = (test, evaluation, response)
        if excluded:
            warnings.append(f"{excluded} saved questions in a compared run have missing or inconsistent assessment evidence and are excluded from pairing.")
        return result

    left, right = rows(before.id), rows(after.id)
    shared_question_count = 0
    decided_shared_question_count = 0
    paired = []
    excluded_assessments = []
    counts = {"fixed": 0, "regressed": 0, "still_failed": 0, "still_passed": 0}
    for identity in sorted(left.keys() & right.keys()):
        lt, le, lr = left[identity]
        rt, re, rr = right[identity]
        if (
            lt.prompt,
            lt.expected_behavior,
            lt.dimension,
            sorted(lt.supporting_memory_ids),
        ) != (
            rt.prompt,
            rt.expected_behavior,
            rt.dimension,
            sorted(rt.supporting_memory_ids),
        ):
            warnings.append(
                "A shared question changed content and was excluded from pairing."
            )
            continue
        shared_question_count += 1
        if reused:
            def origin(run, response):
                if response is None:
                    return None
                receipt = getattr(response, "execution_metadata", None) or {}
                source_run = receipt.get("shared_source_run_id")
                source_response = receipt.get("shared_source_response_id")
                if source_run and source_response:
                    return source_run, source_response
                if (receipt.get("response_source") == "shared_target_answer"
                    or (run.reproducibility_metadata or {}).get("assessment_source_run_id")
                    or (run.reproducibility_metadata or {}).get("shared_answer_source_run_id")):
                    return None  # A replay without its receipt has unknown lineage.
                response_id = getattr(response, "id", None)
                return (run.id, response_id) if response_id else None
            left_origin, right_origin = origin(before, lr), origin(after, rr)
            if left_origin is None or right_origin is None:
                answer_lineage.append("unknown")
            elif left_origin == right_origin:
                answer_lineage.append("same" if lr.response_text == rr.response_text else "unknown")
            else:
                answer_lineage.append("different")
        if not le or not re or not lr or not rr or le.passed is None or re.passed is None:
            continue
        decided_shared_question_count += 1
        outcome = (
            ("still_passed" if re.passed else "regressed")
            if le.passed
            else ("fixed" if re.passed else "still_failed")
        )
        left_signature = assessment_signature(before, le)
        right_signature = assessment_signature(after, re)
        if left_signature is None or left_signature != right_signature:
            excluded_assessments.append({
                "prompt": lt.prompt, "dimension": lt.dimension,
                "before_passed": le.passed, "after_passed": re.passed,
                "before_response": lr.response_text, "after_response": rr.response_text,
                "reason": "Assessment settings or saved rule versions differ, or version evidence is incomplete.",
            })
            continue
        counts[outcome] += 1
        paired.append(
            {
                "suite_test_id": identity,
                "prompt": lt.prompt,
                "dimension": lt.dimension,
                "expected_behavior": lt.expected_behavior,
                "outcome": outcome,
                "before": {
                    "passed": le.passed,
                    "response_text": lr.response_text,
                    "reason": le.reason,
                    "evaluator": le.evaluator,
                },
                "after": {
                    "passed": re.passed,
                    "response_text": rr.response_text,
                    "reason": re.reason,
                    "evaluator": re.evaluator,
                },
            }
        )
    if excluded_assessments:
        warnings.append(
            f"{len(excluded_assessments)} shared questions use different or incompletely recorded assessment standards. "
            "They are excluded from improvement, regression and paired charts. Historical scores are descriptive only."
        )
    if not paired:
        warnings.append(
            "No shared questions have comparable decided assessments. Overall scores are descriptive only."
            if shared_question_count else
            "No unchanged frozen questions are shared. Overall scores are descriptive only."
        )
    if len(paired) < max(len(left), len(right)):
        warnings.append(
            "Only the shared, unchanged questions contribute to the paired comparison."
        )
    answer_provenance = "target_executions"
    if reused:
        answer_provenance = "unknown_saved_answers"
        if answer_lineage and all(item == "same" for item in answer_lineage):
            answer_provenance = "same_saved_answers"
            warnings.insert(0, "Saved-answer assessment comparison: both sides reuse the exact same original answers. Score changes describe assessment decisions, not an improvement in the target model or its memory policy.")
        elif answer_lineage and all(item == "different" for item in answer_lineage):
            answer_provenance = "different_saved_executions"
            warnings.insert(0, "These saved answers come from different original target executions. Reassessment made no new target calls. Compare matching assessment standards and original configuration changes before interpreting the difference.")
        else:
            warnings.insert(0, "Saved-answer provenance is incomplete or mixed. The comparison cannot establish whether score changes come only from reassessment or from different original answers.")
    return {
        "answer_provenance": answer_provenance,
        "warnings": list(dict.fromkeys(warnings)),
        "setting_differences": differences,
        "shared_question_count": shared_question_count,
        "decided_shared_question_count": decided_shared_question_count,
        "comparable_decided_question_count": len(paired),
        "paired_tests": paired,
        "excluded_assessments": excluded_assessments,
        "counts": counts,
        "paired_delta_percentage_points": round(
            (counts["fixed"] - counts["regressed"]) * 100 / len(paired), 3
        )
        if paired
        else None,
        "unpaired_before": sum(bool(e and r and e.passed is not None) for _, e, r in left.values()) - len(paired),
        "unpaired_after": sum(bool(e and r and e.passed is not None) for _, e, r in right.values()) - len(paired),
    }
