"""Double-annotation pilot agreement and readiness calculations."""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from app.schemas.pilot import (
    PilotAgreementMetrics,
    PilotAnalysisRequest,
    PilotAnnotationPackage,
    PilotReadinessReport,
    PilotTask,
)


def _fingerprint(package: PilotAnnotationPackage) -> str:
    canonical = json.dumps(package.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def _kappa(left: list[str], right: list[str]) -> float | None:
    """Unweighted Cohen's kappa for matching categorical item labels."""
    if not left:
        return None
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum((left_counts[label] / len(left)) * (right_counts[label] / len(right)) for label in set(left_counts) | set(right_counts))
    if expected == 1:
        return None
    return round((observed - expected) / (1 - expected), 3)


class PilotAnnotationService:
    """Analyse a request-scoped package without retaining labels or source data."""

    def analyse(self, request: PilotAnalysisRequest) -> PilotReadinessReport:
        package = request.package
        annotator_a, annotator_b = package.annotators
        declared = {(item.item_id, item.task) for item in package.items}
        labels_a = {(label.item_id, label.task): label.label for label in annotator_a.labels}
        labels_b = {(label.item_id, label.task): label.label for label in annotator_b.labels}
        adjudications = {(label.item_id, label.task): label for label in package.adjudications}

        tasks = sorted({item.task for item in package.items}, key=lambda task: task.value)
        by_task = [
            self._metrics(task, {key for key in declared if key[1] == task}, labels_a, labels_b, adjudications)
            for task in tasks
        ]
        overall = self._metrics(None, declared, labels_a, labels_b, adjudications)
        blockers = self._blockers(package, by_task, overall)
        return PilotReadinessReport(
            pilot_id=package.pilot_id,
            dataset_id=package.dataset_id,
            dataset_version=package.dataset_version,
            fingerprint_sha256=_fingerprint(package),
            annotator_ids=[annotator_a.annotator_id, annotator_b.annotator_id],
            minimum_paired_items_per_task=package.minimum_paired_items_per_task,
            minimum_kappa=package.minimum_kappa,
            overall=overall,
            by_task=by_task,
            ready_for_formal_evaluation=not blockers,
            blocking_reasons=blockers,
        )

    @staticmethod
    def _metrics(
        task: PilotTask | None,
        declared: set[tuple[str, PilotTask]],
        labels_a: dict[tuple[str, PilotTask], str],
        labels_b: dict[tuple[str, PilotTask], str],
        adjudications: dict,
    ) -> PilotAgreementMetrics:
        keys_a, keys_b = set(labels_a) & declared, set(labels_b) & declared
        paired = sorted(keys_a & keys_b, key=lambda item: (item[1].value, item[0]))
        agreements = sum(labels_a[key] == labels_b[key] for key in paired)
        disagreements = [key for key in paired if labels_a[key] != labels_b[key]]
        disagreement_adjudications = sum(key in adjudications for key in disagreements)
        kappa = _kappa([labels_a[key] for key in paired], [labels_b[key] for key in paired])
        return PilotAgreementMetrics(
            task=task,
            declared_items=len(declared),
            annotator_a_labelled=len(keys_a),
            annotator_b_labelled=len(keys_b),
            paired_items=len(paired),
            adjudicated_items=len(set(adjudications) & declared),
            agreement_count=agreements,
            disagreement_count=len(disagreements),
            percent_agreement=_percentage(agreements, len(paired)),
            cohens_kappa=kappa,
            kappa_applicable=kappa is not None,
            disagreements_adjudicated=disagreement_adjudications,
            unresolved_disagreements=len(disagreements) - disagreement_adjudications,
        )

    @staticmethod
    def _blockers(
        package: PilotAnnotationPackage,
        by_task: list[PilotAgreementMetrics],
        overall: PilotAgreementMetrics,
    ) -> list[str]:
        blockers: list[str] = []
        for metric in by_task:
            name = metric.task.value if metric.task else "overall"
            if metric.paired_items < package.minimum_paired_items_per_task:
                blockers.append(f"{name}: only {metric.paired_items} paired items; minimum is {package.minimum_paired_items_per_task}.")
            if metric.paired_items != metric.declared_items:
                blockers.append(f"{name}: both annotators have not labelled every declared item.")
            if metric.adjudicated_items != metric.declared_items:
                blockers.append(f"{name}: every declared item needs an adjudicated or external-reference label.")
            if metric.unresolved_disagreements:
                blockers.append(f"{name}: {metric.unresolved_disagreements} disagreement(s) remain unadjudicated.")
            if (
                package.minimum_kappa is not None
                and metric.kappa_applicable
                and metric.cohens_kappa is not None
                and metric.cohens_kappa < package.minimum_kappa
            ):
                blockers.append(f"{name}: Cohen's kappa {metric.cohens_kappa} is below the declared minimum {package.minimum_kappa}.")
        if overall.declared_items == 0:
            blockers.append("No pilot items were declared.")
        return blockers
