"""Compare saved audits only by their frozen canonical test identities."""

from sqlalchemy import select
from app.models import TestCaseModel, EvaluationResultModel, TargetResponseModel


def profile_description(profile):
    if not profile:
        return "Original defaults"
    return (f"{profile.get('label', 'Memory configuration')} · version {profile.get('version', 1)} · "
        f"up to {profile.get('max_retrieved_records', 50)} records / {profile.get('context_character_budget', 16000)} characters · "
        f"project separation {'on' if profile.get('isolate_project_scope') else 'off'} · "
        f"current-fact preference {'on' if profile.get('prefer_current_state') else 'off'} · "
        f"instructions: {profile.get('additional_instructions') or 'default'}")

def assessment_signature(run, evaluation):
    """Use saved evidence, never the currently installed evaluator version."""
    implementation = evaluation.evaluator
    if not implementation:
        return None
    meter = getattr(evaluation, "judge_execution", None) or {}
    cross_check = meter.get("cross_check_version")
    if (implementation in {"llm-judge-ollama-v2", "llm-judge-ollama-v3"}
        or (implementation.startswith("llm-judge-") and implementation.endswith("-v4"))) and not cross_check:
        return None
    return (implementation, getattr(run, "evaluator_provider", None),
            getattr(run, "evaluator_model", None), meter.get("provider"),
            meter.get("model"), cross_check)


def compare_audit_evidence(db, before, after):
    warnings = []
    controls = [
        ("conversation_id", "Source conversation"),
        ("provider", "Target provider"),
        ("model", "Target model"),
        ("target_configuration", "Reader behaviour policy"),
        ("temperature", "Temperature"),
        ("evaluator_provider", "Evaluator provider"),
        ("evaluator_model", "Evaluator model"),
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
        and before.target_configuration == after.target_configuration
        and (before.reproducibility_metadata or {}).get("target_memory_profile", {}) == (after.reproducibility_metadata or {}).get("target_memory_profile", {})
    ):
        if before.provider != after.provider or before.model != after.model:
            warnings.append("The saved memory configuration matches. This compares different target models or providers, rather than a memory policy change.")
        elif differences:
            warnings.append("The saved memory configuration matches, but other recorded settings differ. Check those changes when interpreting the results.")
        else:
            warnings.append("Both runs use the same saved configuration. This is a repeat comparison, not a recorded policy change.")
    if any(
        (run.reproducibility_metadata or {}).get("human_validation") == "pending"
        for run in (before, after)
    ):
        warnings.append(
            "This synthetic pilot was pre-reviewed by AI. Independent human validation is still pending."
        )

    def rows(run_id):
        tests = db.scalars(
            select(TestCaseModel).where(TestCaseModel.run_id == run_id)
        ).all()
        result = {}
        for test in tests:
            evaluation = db.scalar(
                select(EvaluationResultModel).where(
                    EvaluationResultModel.test_id == test.id
                )
            )
            response = db.scalar(
                select(TargetResponseModel).where(
                    TargetResponseModel.test_id == test.id,
                    TargetResponseModel.run_id == run_id,
                )
            )
            if evaluation and response and evaluation.passed is not None:
                result[test.comparison_test_id or test.suite_test_id or test.id] = (test, evaluation, response)
        return result

    left, right = rows(before.id), rows(after.id)
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
                f"Shared question {identity} changed content and was excluded from pairing."
            )
            continue
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
            "No identical frozen questions can be paired. Overall scores are descriptive only."
        )
    if len(paired) < max(len(left), len(right)):
        warnings.append(
            "Only the shared, unchanged questions contribute to the paired comparison."
        )
    return {
        "warnings": list(dict.fromkeys(warnings)),
        "setting_differences": differences,
        "paired_tests": paired,
        "excluded_assessments": excluded_assessments,
        "counts": counts,
        "paired_delta_percentage_points": round(
            (counts["fixed"] - counts["regressed"]) * 100 / len(paired), 3
        )
        if paired
        else None,
        "unpaired_before": len(left) - len(paired),
        "unpaired_after": len(right) - len(paired),
    }
