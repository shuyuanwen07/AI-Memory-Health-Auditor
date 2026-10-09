"""Reliability is measured against explicit human references, never invented labels."""
from math import sqrt


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total))/denominator
    radius = z*sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator
    return [round(max(0, center-radius)*100, 2), round(min(1, center+radius)*100, 2)]


def reliability_summary(items: list) -> dict:
    references = [item for item in items if item.human_review is not None]
    resolved = [item for item in references if item.automated.passed is not None]
    tp = fp = fn = tn = 0
    dimensions = {}
    for item in resolved:
        automatic_failure = item.automated.passed is False
        human_failure = item.human_review.human_passed is False
        if automatic_failure and human_failure:
            tp += 1
        elif automatic_failure:
            fp += 1
        elif human_failure:
            fn += 1
        else:
            tn += 1
        bucket = dimensions.setdefault(item.test.dimension.value, {"reviewed": 0, "correct": 0})
        bucket["reviewed"] += 1
        bucket["correct"] += automatic_failure == human_failure
    def metric(numerator, denominator):
        return {"percentage": round(numerator*100/denominator, 2) if denominator else None,
                "numerator": numerator, "denominator": denominator, "interval_95": wilson(numerator, denominator)}
    classified = [item for item in resolved if item.human_review.human_passed is False and item.human_review.human_failure_type is not None]
    detected = [item for item in classified if item.automated.passed is False]
    def category_matches(item):
        return item.automated.passed is False and item.automated.failure_type == item.human_review.human_failure_type
    category_cells = {}
    for item in classified:
        expected = item.human_review.human_failure_type.value
        actual = item.automated.failure_type.value if item.automated.passed is False and item.automated.failure_type else ("unclassified_failure" if item.automated.passed is False else "no_failure_detected")
        category_cells[(expected, actual)] = category_cells.get((expected, actual), 0) + 1
    independent = [item for item in items if len({review.reviewer_label for review in item.human_reviews if review.review_role.value == "independent"}) >= 2]
    return {"evaluated": len(items), "decided": sum(item.automated.passed is not None for item in items),
            "uncertain": sum(item.automated.passed is None for item in items),
            "resolved_reference_count": len(references), "decided_reference_count": len(resolved), "double_reviewed_count": len(independent),
            "review_coverage": metric(len(references), len(items)),
            "labelled_abstention_rate": metric(len(references)-len(resolved), len(references)),
            "failure_classification_accuracy": metric(sum(category_matches(item) for item in detected), len(detected)),
            "failure_detection_and_classification_recall": metric(sum(category_matches(item) for item in classified), len(classified)),
            "category_confusion": [{"human_category": expected, "automatic_category": actual, "count": count} for (expected, actual), count in sorted(category_cells.items())],
            "accuracy": metric(tp+tn, len(resolved)), "failure_precision": metric(tp, tp+fp),
            "failure_recall": metric(tp, tp+fn), "false_positive_rate": metric(fp, fp+tn),
            "confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
            "by_dimension": dimensions,
            "evidence_status": "human_references_available" if references else "not_calibrated",
            "notice": "Binary metrics exclude uncertain automated decisions; review coverage includes their human references. Category accuracy measures jointly detected failures with human categories; detection-and-classification recall also counts missed failures. Missing human categories are excluded from category metrics. Coverage, selection bias and scenario dependence must be reported; this is not a general reliability guarantee."}


def paired_probe_summary(items: list) -> dict:
    groups = {}
    for item in items:
        if item.test.probe_group_id:
            groups.setdefault(item.test.probe_group_id, {})[item.test.probe_variant] = item
    rows = []
    for identity, probes in groups.items():
        direct, task = probes.get("direct"), probes.get("task")
        if not direct or not task:
            continue
        decided = direct.automated.passed is not None and task.automated.passed is not None
        rows.append({"group_id": identity, "dimension": direct.test.dimension.value,
                     "direct_question": direct.test.prompt, "task_question": task.test.prompt,
                     "direct_passed": direct.automated.passed, "task_passed": task.automated.passed,
                     "recall_use_gap": decided and direct.automated.passed is True and task.automated.passed is False})
    return {"complete_groups": len(rows), "recall_use_gaps": sum(row["recall_use_gap"] for row in rows), "groups": rows,
            "notice": "Paired answers are automated evidence. Count related probes as one group; independently review gaps before claiming a discovered defect."}
