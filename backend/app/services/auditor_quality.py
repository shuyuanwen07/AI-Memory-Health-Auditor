"""Reliability is measured against explicit human references, never invented labels."""
from math import sqrt
from app.services.reviewer_identity import distinct_reviewers


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total))/denominator
    radius = z*sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator
    return [round(max(0, center-radius)*100, 2), round(min(1, center+radius)*100, 2)]


def metric(numerator, denominator):
    return {"percentage": round(numerator*100/denominator, 2) if denominator else None,
            "numerator": numerator, "denominator": denominator, "interval_95": wilson(numerator, denominator)}


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
    classified = [item for item in references if item.human_review.human_passed is False and item.human_review.human_failure_type is not None]
    detected = [item for item in classified if item.automated.passed is False]
    def category_matches(item):
        return item.automated.passed is False and item.automated.failure_type == item.human_review.human_failure_type
    category_cells = {}
    for item in classified:
        expected = item.human_review.human_failure_type.value
        actual = item.automated.failure_type.value if item.automated.passed is False and item.automated.failure_type else ("unclassified_failure" if item.automated.passed is False else "abstained" if item.automated.passed is None else "no_failure_detected")
        category_cells[(expected, actual)] = category_cells.get((expected, actual), 0) + 1
    human_failures = [item for item in references if item.human_review.human_passed is False]
    human_passes = [item for item in references if item.human_review.human_passed is True]
    adjudicated = []
    for item in references:
        review = item.human_review
        if getattr(getattr(review, "review_role", None), "value", None) != "adjudication":
            continue
        cited_ids = set(getattr(review, "based_on_review_ids", []))
        cited = [row for row in item.human_reviews if getattr(row, "review_id", None) in cited_ids
                 and row.review_role.value == "independent"]
        if len(distinct_reviewers(cited)) >= 2:
            adjudicated.append(item)
    independent = [item for item in items if len(distinct_reviewers([review for review in item.human_reviews if review.review_role.value == "independent"])) >= 2]
    return {"evaluated": len(items), "decided": sum(item.automated.passed is not None for item in items),
            "uncertain": sum(item.automated.passed is None for item in items),
            "resolved_reference_count": len(references), "decided_reference_count": len(resolved), "double_reviewed_count": len(independent),
            "adjudicated_reference_count": len(adjudicated),
            "reference_only_count": len(references) - len(adjudicated),
            "failure_recall_including_abstentions": metric(tp, len(human_failures)),
            "reference_outcomes": {"human_failures": len(human_failures), "human_passes": len(human_passes),
                "uncertain_on_failure": sum(item.automated.passed is None for item in human_failures),
                "uncertain_on_pass": sum(item.automated.passed is None for item in human_passes)},
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


def scenario_reliability(groups: dict[str, list], *, resamples: int = 1000) -> dict:
    """Descriptive percentile intervals resampling complete source-history groups.

    Repeats and related questions remain together. Stored history identity is
    the grouping unit, not a verification of semantic independence or human
    label validity. These intervals do not establish causal superiority.
    """
    from random import Random
    counts = []
    for key in sorted(groups):
        labelled = [item for item in groups[key] if item.human_review is not None]
        if not labelled:
            continue
        tp = tn = fp = fn = uncertain = human_failures = 0
        for item in labelled:
            human_failed = item.human_review.human_passed is False
            human_failures += human_failed
            if item.automated.passed is None:
                uncertain += 1
            elif item.automated.passed is False:
                tp += human_failed
                fp += not human_failed
            else:
                fn += human_failed
                tn += not human_failed
        counts.append((tp, tn, fp, fn, uncertain, human_failures, len(labelled)))
    metrics = {key: [] for key in ('accuracy', 'failure_precision', 'failure_recall_including_abstentions', 'false_positive_rate')}
    if len(counts) >= 2:
        rng = Random('source-history-bootstrap-v1')
        for _ in range(resamples):
            totals = [0] * 7
            for _ in counts:
                sample = counts[rng.randrange(len(counts))]
                for index, value in enumerate(sample):
                    totals[index] += value
            tp, tn, fp, fn, _, human_failures, _ = totals
            for key, numerator, denominator in (
                ('accuracy', tp + tn, tp + tn + fp + fn),
                ('failure_precision', tp, tp + fp),
                ('failure_recall_including_abstentions', tp, human_failures),
                ('false_positive_rate', fp, fp + tn),
            ):
                if denominator:
                    metrics[key].append(100 * numerator / denominator)
    def interval(samples):
        if not samples:
            return None
        samples.sort()
        return [round(samples[int((len(samples)-1)*p)], 2) for p in (0.025, 0.975)]
    return {'method': 'source-history-cluster-bootstrap-v1', 'labelled_histories': len(counts),
            'resamples': resamples if len(counts) >= 2 else 0,
            'metrics': {key: {'interval_95': interval(values), 'valid_resamples': len(values)} for key, values in metrics.items()},
            'notice': 'Related questions and repeat audits stay within the same stored source history. At least two labelled histories are needed to calculate an interval; small samples, unreviewed cases and selection bias remain limitations. Distinct stored histories are not automatically independent. These are descriptive intervals, not proof of superiority.'}


def apply_evidence_integrity(report: dict, run_counts: list[dict]) -> dict:
    """Keep saved-question coverage visible when corrupt receipts are excluded."""
    from collections import Counter
    reasons = Counter()
    for row in run_counts:
        reasons.update(row['reasons'])
    coverage = {key: sum(row[key] for row in run_counts) for key in
                ('expected_questions', 'eligible_questions', 'excluded_questions', 'discarded_review_labels')}
    coverage['reasons'] = dict(sorted(reasons.items()))
    report['evidence_integrity'] = coverage
    report['review_coverage'] = metric(report['resolved_reference_count'], coverage['expected_questions'])
    report['notice'] += ' Review coverage uses all saved questions, including questions excluded for missing or inconsistent answer/assessment records. Excluded evidence does not count as a model failure or a pass.'
    return report
