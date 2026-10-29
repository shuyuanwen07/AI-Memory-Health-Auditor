"""Insert the published four-strategy dashboard results into the experiment report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BEGIN = "<!-- four-strategy-v7:start -->"
END = "<!-- four-strategy-v7:end -->"
EXPECTED = ["weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"]
LABELS = {"weak_first_hit": "First-match retrieval", "strong_rule_based": "Relationship-priority retrieval",
          "scope_aware": "Match the task and project", "temporal_importance": "Consider time and importance"}


def format_rate(correct: int, total: int) -> str:
    return f"{correct}/{total} ({100 * correct / total:.1f}%)" if total else "Not measured"


def update(report_path: Path, source_path: Path) -> None:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if data.get("format") != "phase4-c-four-strategy-v7":
        raise ValueError("The source is not the published v7 dashboard report.")
    rows = data.get("strategies", [])
    if [row.get("id") for row in rows] != EXPECTED or any(row.get("label") != LABELS[row["id"]] for row in rows):
        raise ValueError("The dashboard strategy identities or names do not match the frozen comparison.")
    lines = [BEGIN, "### Experiment C extension: four-strategy comparison (v7)", "",
             "This exploratory follow-up uses the same 30 LongMemEval histories already observed in v6. "
             "All four strategies were run afresh for three repetitions per history with OpenRouter GPT-6 Luna. "
             "The same model also supplied the automatic answer grades. Repeated answers share histories and "
             "are not additional independent cases; this is a local compatibility comparison.", "",
             f"Collection status: **{data['collection_status']}**. Saved {data['total_target_answers']}/360 target answers "
             f"and {data['total_usable_grades']}/360 usable automatic grades.", "",
             "| Retrieval strategy | Correct / usable automatic grades | Repeat 1 | Repeat 2 | Repeat 3 |",
             "|---|---:|---:|---:|---:|"]
    for row in rows:
        repetitions = row.get("per_repetition", [])
        if len(repetitions) != 3 or sum(r["correct"] for r in repetitions) != row["correct"] or sum(r["total"] for r in repetitions) != row["total"]:
            raise ValueError("A strategy's pooled score does not reconcile with its three repetitions.")
        repeat_text = " | ".join(format_rate(r["correct"], r["total"]) for r in repetitions)
        lines.append(f"| {row['label']} | {format_rate(row['correct'], row['total'])} | {repeat_text} |")
    lines += ["", "The table uses correct answers divided by usable automatic grades. Each repeat covers the same "
              "30 histories. The repeat values describe variation under this setup; they do not establish population-level reliability.", ""]
    chosen = data.get("recommended_strategy", "no_clear_winner")
    if data.get("complete_for_decision") and chosen in LABELS:
        lines.append(f"Under the frozen exploratory decision rule, **{LABELS[chosen]}** met the local selection rule. "
                     "This is a recommendation for this tested setup, not a general ranking of all memory systems.")
    elif not data.get("complete_for_decision"):
        lines.append("A protocol winner decision was withheld because the collection did not satisfy every verification gate.")
    else:
        lines.append("The frozen decision rule did not establish a clear winner for this collection.")
    if data.get("pacing_status") == "utc_timing_unverifiable":
        lines += ["", "One recorded UTC interval is shorter than the planned four-second dispatch interval. "
                  "The frozen runner uses a monotonic wait, but no monotonic timing trace was saved, so the actual interval "
                  "and the cause of the discrepancy cannot be independently established. The preserved results are therefore descriptive."]
    lines += ["", f"Estimated cost: US${data['estimated_cost_usd']:.3f} under the US$0.40 estimated-cost ceiling; "
              "the ledger is an estimate, not an independently verified provider invoice. Independent human answer review remains pending.", "",
              "The dashboard reports the full per-category and matched pairwise results, including usable denominators. "
              "This four-policy follow-up does not change the archived proposal A/B/C results or establish independent Auditor validity.", "",
              f"Evidence: protocol SHA-256 `{data['protocol_sha256']}`; run SHA-256 `{data['run_sha256']}`. "
              "The public dashboard contains aggregate results only.", "", END, ""]
    section = "\n".join(lines)
    text = report_path.read_text(encoding="utf-8")
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError("The existing v7 report markers are inconsistent.")
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        text = text[:start] + section.rstrip() + text[stop:]
    else:
        anchor = "### Proposal acceptance criteria"
        if text.count(anchor) != 1:
            raise ValueError("Could not find the unique insertion point in the existing experiment report.")
        text = text.replace(anchor, section + "\n" + anchor, 1)
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dashboard-json", type=Path, required=True)
    args = parser.parse_args()
    update(args.report, args.dashboard_json)
    print(f"Updated experiment report from {args.dashboard_json}")


if __name__ == "__main__":
    main()
