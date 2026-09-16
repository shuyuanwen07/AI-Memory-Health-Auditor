#!/usr/bin/env python3
"""Create deterministic, presentation-only artifacts from an experiment CSV.

The generated files never impute missing values, test statistical significance,
or convert synthetic illustrations into empirical findings.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Iterable


CHART_WIDTH = 920
COLOURS = ("#176b87", "#5a8f4c", "#b36a3c", "#765aa6", "#a13e66")
NOTE = "Deterministic presentation of supplied export; no significance inference is added."


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def condition_rows(rows: Iterable[dict[str, str]]) -> list[tuple[str, float]]:
    values: dict[str, float] = {}
    for row in rows:
        if row.get("record_type") == "condition" and row.get("metric") == "overall_mean":
            score = number(row.get("value"))
            if score is not None and row.get("condition"):
                values[row["condition"]] = score
    return sorted(values.items())


def dimension_rows(rows: Iterable[dict[str, str]]) -> list[tuple[str, str, float]]:
    values: dict[tuple[str, str], float] = {}
    for row in rows:
        if row.get("record_type") == "dimension" and row.get("metric") == "mean_percentage":
            score = number(row.get("value"))
            condition, dimension = row.get("condition", ""), row.get("dimension", "")
            if score is not None and condition and dimension:
                values[(condition, dimension)] = score
    return [(condition, dimension, score) for (condition, dimension), score in sorted(values.items())]


def failure_rows(rows: Iterable[dict[str, str]]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("record_type") == "failure" and row.get("metric") == "detected_failure":
            counts[row.get("dimension") or "unclassified"] += 1
    return sorted(counts.items())


def write_csv(destination: Path, header: list[str], rows: Iterable[Iterable[object]]) -> None:
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg_document(title: str, height: int, content: str, aria_label: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CHART_WIDTH}" height="{height}" viewBox="0 0 {CHART_WIDTH} {height}" role="img" aria-label="{escape(aria_label)}">
<style>text{{font:14px Arial,sans-serif;fill:#19324a}} .title{{font-weight:bold;font-size:18px}} .note{{font-size:12px;fill:#496178}}</style>
<text class="title" x="24" y="28">{escape(title)}</text>{content}
<text class="note" x="24" y="{height - 16}">{escape(NOTE)}</text></svg>'''


def write_overall_svg(values: list[tuple[str, float]], destination: Path) -> None:
    left, top, row_height, plot_width = 230, 54, 58, 590
    height = max(210, top + row_height * len(values) + 72)
    grid = "".join(
        f'<line x1="{left + value * plot_width / 100:.1f}" y1="42" x2="{left + value * plot_width / 100:.1f}" y2="{height - 48}" stroke="#d8e2ec"/>'
        f'<text x="{left + value * plot_width / 100:.1f}" y="{height - 32}" text-anchor="middle">{value}</text>'
        for value in range(0, 101, 20)
    )
    bars: list[str] = []
    for index, (condition, score) in enumerate(values):
        y, width = top + index * row_height, max(0, min(100, score)) * plot_width / 100
        bars.extend((
            f'<text x="{left - 10}" y="{y + 22}" text-anchor="end">{escape(condition)}</text>',
            f'<rect x="{left}" y="{y}" width="{width:.1f}" height="30" fill="#176b87"/>',
            f'<text x="{left + width + 8:.1f}" y="{y + 22}">{score:.1f}%</text>',
        ))
    destination.write_text(svg_document("Overall Memory Health by condition", height, grid + "".join(bars), "Overall Memory Health by condition"), encoding="utf-8")


def write_dimension_svg(values: list[tuple[str, str, float]], destination: Path) -> None:
    dimensions = sorted({dimension for _, dimension, _ in values})
    conditions = sorted({condition for condition, _, _ in values})
    lookup = {(condition, dimension): score for condition, dimension, score in values}
    left, top, group_width, bar_width, plot_height = 110, 64, 170, 24, 270
    height = 420
    grid = "".join(
        f'<line x1="{left}" y1="{top + plot_height - value * plot_height / 100:.1f}" x2="{left + max(1, len(dimensions)) * group_width}" y2="{top + plot_height - value * plot_height / 100:.1f}" stroke="#d8e2ec"/>'
        f'<text x="{left - 8}" y="{top + plot_height - value * plot_height / 100 + 5:.1f}" text-anchor="end">{value}</text>'
        for value in range(0, 101, 20)
    )
    bars: list[str] = []
    for dimension_index, dimension in enumerate(dimensions):
        group_x = left + dimension_index * group_width
        bars.append(f'<text x="{group_x + group_width / 2:.1f}" y="{top + plot_height + 24}" text-anchor="middle">{escape(dimension.replace("_", " "))}</text>')
        for condition_index, condition in enumerate(conditions):
            score = lookup.get((condition, dimension))
            if score is None:
                continue
            value_height = max(0, min(100, score)) * plot_height / 100
            x, y = group_x + 12 + condition_index * (bar_width + 5), top + plot_height - value_height
            bars.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_width}" height="{value_height:.1f}" fill="{COLOURS[condition_index % len(COLOURS)]}"/>')
    legend = "".join(
        f'<rect x="{left + index * 170}" y="{top + plot_height + 54}" width="13" height="13" fill="{COLOURS[index % len(COLOURS)]}"/><text x="{left + 19 + index * 170}" y="{top + plot_height + 65}">{escape(condition)}</text>'
        for index, condition in enumerate(conditions)
    )
    destination.write_text(svg_document("Memory Health dimensions by condition", height, grid + "".join(bars) + legend, "Memory Health dimension percentages by condition"), encoding="utf-8")


def write_failure_svg(values: list[tuple[str, int]], destination: Path) -> None:
    left, top, row_height, plot_width = 230, 54, 58, 590
    maximum, height = max((count for _, count in values), default=1), max(190, top + row_height * len(values) + 72)
    bars: list[str] = []
    for index, (dimension, count) in enumerate(values):
        y, width = top + index * row_height, count * plot_width / maximum
        bars.extend((
            f'<text x="{left - 10}" y="{y + 22}" text-anchor="end">{escape(dimension.replace("_", " "))}</text>',
            f'<rect x="{left}" y="{y}" width="{width:.1f}" height="30" fill="#b36a3c"/>',
            f'<text x="{left + width + 8:.1f}" y="{y + 22}">{count}</text>',
        ))
    destination.write_text(svg_document("Detected failures by dimension", height, "".join(bars), "Detected failures by dimension"), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(input_path: Path, output: Path, artifacts: list[Path], counts: dict[str, int]) -> None:
    manifest = {
        "schema_version": "mha-paper-artifacts-v2",
        "input": {"filename": input_path.name, "sha256": sha256(input_path)},
        "artifacts": [{"filename": path.name, "sha256": sha256(path)} for path in sorted(artifacts, key=lambda item: item.name)],
        "row_counts": counts,
        "notice": NOTE,
        "analysis_boundary": "Presentation only. No statistical significance, causal, or benchmark-official claim is produced.",
    }
    (output / "paper_artifacts_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: generate_paper_artifacts.py INPUT_EXPORT.csv OUTPUT_DIRECTORY")
    input_path, output = Path(sys.argv[1]), Path(sys.argv[2])
    rows = read_rows(input_path)
    overall, dimensions, failures = condition_rows(rows), dimension_rows(rows), failure_rows(rows)
    if not overall:
        raise SystemExit("No condition/overall_mean rows were found in the supplied export.")
    output.mkdir(parents=True, exist_ok=True)
    overall_csv, overall_svg = output / "condition_overall_means.csv", output / "condition_overall_means.svg"
    write_csv(overall_csv, ["condition", "overall_mean_percentage", "provenance_note"], ((condition, f"{score:.2f}", NOTE) for condition, score in overall))
    write_overall_svg(overall, overall_svg)
    artifacts = [overall_csv, overall_svg]
    if dimensions:
        dimensions_csv, dimensions_svg = output / "dimension_comparison.csv", output / "dimension_comparison.svg"
        write_csv(dimensions_csv, ["condition", "dimension", "mean_percentage", "provenance_note"], ((condition, dimension, f"{score:.2f}", NOTE) for condition, dimension, score in dimensions))
        write_dimension_svg(dimensions, dimensions_svg)
        artifacts.extend((dimensions_csv, dimensions_svg))
    if failures:
        failures_csv, failures_svg = output / "failure_distribution.csv", output / "failure_distribution.svg"
        write_csv(failures_csv, ["dimension", "detected_failure_count", "provenance_note"], ((dimension, count, NOTE) for dimension, count in failures))
        write_failure_svg(failures, failures_svg)
        artifacts.extend((failures_csv, failures_svg))
    write_manifest(input_path, output, artifacts, {"input_rows": len(rows), "overall_rows": len(overall), "dimension_rows": len(dimensions), "failure_rows": len(failures)})


if __name__ == "__main__":
    main()
