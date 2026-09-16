#!/usr/bin/env python3
"""Create deterministic table and SVG chart from an exported experiment CSV.

Presentation only: it never infers significance, fills missing values, or turns
the bundled illustrative synthetic CSV into research evidence.
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def condition_rows(rows: list[dict[str, str]]) -> list[tuple[str, float]]:
    values: dict[str, float] = {}
    for row in rows:
        if row.get("record_type") == "condition" and row.get("metric") == "overall_mean":
            try:
                values[row["condition"]] = float(row["value"])
            except (KeyError, ValueError):
                continue
    return sorted(values.items())


def write_table(values: list[tuple[str, float]], destination: Path) -> None:
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["condition", "overall_mean_percentage", "provenance_note"])
        for condition, score in values:
            writer.writerow([condition, f"{score:.2f}", "Copied deterministically from supplied export; interpret under the frozen protocol."])


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg(values: list[tuple[str, float]], destination: Path) -> None:
    left, baseline = 190, 295
    bars: list[str] = []
    for index, (condition, score) in enumerate(values):
        y, width = 52 + index * 70, max(0, min(100, score)) * 5
        bars.extend((
            f'<text x="{left - 10}" y="{y + 22}" text-anchor="end">{escape(condition)}</text>',
            f'<rect x="{left}" y="{y}" width="{width:.1f}" height="32" fill="#176b87"/>',
            f'<text x="{left + width + 8:.1f}" y="{y + 22}">{score:.1f}%</text>',
        ))
    grid = "".join(f'<line x1="{left + value * 5}" y1="35" x2="{left + value * 5}" y2="{baseline}" stroke="#d8e2ec"/><text x="{left + value * 5}" y="{baseline + 22}" text-anchor="middle">{value}</text>' for value in range(0, 101, 20))
    destination.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="360" viewBox="0 0 760 360" role="img" aria-label="Overall Memory Health by condition">
<style>text{{font:14px Arial,sans-serif;fill:#19324a}} .title{{font-weight:bold;font-size:18px}}</style>
<text class="title" x="20" y="24">Overall Memory Health by condition</text><text x="20" y="340">Values copied from supplied export; no significance inference is added.</text>{grid}{''.join(bars)}</svg>''', encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: generate_paper_artifacts.py INPUT_EXPORT.csv OUTPUT_DIRECTORY")
    values = condition_rows(read_rows(Path(sys.argv[1])))
    if not values:
        raise SystemExit("No condition/overall_mean rows were found in the supplied export.")
    output = Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    write_table(values, output / "condition_overall_means.csv")
    write_svg(values, output / "condition_overall_means.svg")


if __name__ == "__main__":
    main()
