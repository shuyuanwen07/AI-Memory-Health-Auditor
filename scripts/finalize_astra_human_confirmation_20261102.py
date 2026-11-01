"""Apply the user's explicit two-person verification to this fixed 552-answer batch.

No model calls, regrading, resolution of uncertainty, or edits to original AI
reviews occur here. Approval binds immutable evidence and semantic outcomes.
If either changes, the old human confirmation cannot silently cover it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output/proposal-delivery"
A = BASE / "a-astra-max-retest-20261101-v2"
BC = BASE / "bc-reader-retest-20261101-v2"
AC3 = BASE / "ac3-astra-max-retest-20261101-v2"
DEST = BASE / "all-astra-main-results-20261101"
RECEIPT = DEST / "human-confirmation.json"
COUNTS = {"A": 48, "B": 192, "C": 192, "AC3": 120}


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def write(path, value):
    stage = path.with_suffix(path.suffix + ".pending")
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    stage.replace(path)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def semantic_hashes(a, bc, ac3):
    # Derived status/timestamps may change; substantive judgments may not.
    views = {
        "A": {k: a[k] for k in ("methods", "items")},
        "BC": {k: bc[k] for k in ("sources", "items")},
        "AC3": {"cohort": ac3["cohort"], **{
            arm: {k: ac3[arm][k] for k in ("counts", "confusion_matrix", "metrics")}
            for arm in ("baseline", "candidate")}},
    }
    return {k: sha(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()) for k, v in views.items()}


def verify_bindings(receipt):
    if receipt.get("answer_counts") != COUNTS or receipt.get("status") != "user_reported_independent_ai_assisted":
        raise ValueError("Confirmation is for a different batch or review mode")
    for name, expected in receipt["bound_files_sha256"].items():
        path = ROOT / name
        if path.resolve().is_relative_to(ROOT.resolve()) is False or sha(path.read_bytes()) != expected:
            raise ValueError(f"Human-confirmed evidence changed: {name}")


def main(record_confirmation=False):
    a = read(A / "analysis.json")
    bc = read(BC / "review/consensus.json")
    ac3 = read(AC3 / "analysis.json")
    assert len(a["items"]) == 48 and len(bc["items"]) == 384 and len(ac3["items"]) == 120
    outcomes = semantic_hashes(a, bc, ac3)
    if RECEIPT.exists():
        confirmation = read(RECEIPT)
    elif record_confirmation:
        evidence = [
            DEST / "Astra-MAX-全部新增实验-待人工复核.zip",
            A / "protocol.json", A / "sources.json", A / "blind-review/material.json",
            A / "review-max/reviewer-1.review.json", A / "review-max/reviewer-2.review.json",
            BC / "B/protocol.json", BC / "C/protocol.json", BC / "C/compact-review/final-all.json",
            *sorted((BC / "B/blind-review").glob("compact-batch-*.json")),
            *[BC / f"review-max/reviewer-{r}/{s}-all.review.json" for r in (1, 2) for s in ("B", "C")],
            AC3 / "protocol.json", AC3 / "sources.json", AC3 / "blind-review/compact-all.json",
            AC3 / "review-max/reviewer-1/batch-1-80.review.json",
            AC3 / "review-max/reviewer-1/batch-2-40.review.json",
            AC3 / "review-max/reviewer-2/all-120.review.json",
        ]
        confirmation = {
            "format": "astra-max-552-human-confirmation-v1",
            "status": "user_reported_independent_ai_assisted",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "confirmation_source": "Explicit user message in the project conversation",
            "user_statement_verbatim": "两位人工逐一确认并且独立审核没有问题",
            "answer_counts": COUNTS, "total_answers": 552,
            "human_reviewers": 2, "reviewed_each_item": True,
            "completed_independently": True, "used_ai_assistance": True,
            "blindness_to_automatic_scores": "not newly established",
            "identities_independently_authenticated": False,
            "approved_scope": "Original MAX AI opinions and the conservative conclusions in the supplied unified package; no individual edits supplied.",
            "unresolved_preserved": {"A_mapping_disputes": 1, "C_question_reference_flags": 4,
                                     "BC_unresolved_answers": 59, "AC3_unclassifiable_failures": 27},
            "interpretation": "Human verification does not turn uncertain references into valid ones, create a single primary failure type, or certify full AC3 acceptance.",
            "bound_files_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in evidence},
            "semantic_result_sha256": outcomes,
        }
        write(RECEIPT, confirmation)
    else:
        raise ValueError("No recorded explicit human confirmation exists")
    verify_bindings(confirmation)
    if confirmation["semantic_result_sha256"] != outcomes:
        raise ValueError("Substantive results changed after human confirmation")
    link = {"path": str(RECEIPT.relative_to(ROOT)), "sha256": sha(RECEIPT.read_bytes()),
            "mode": confirmation["status"]}
    for folder in (A, BC, AC3):
        write(folder / "human-confirmation.json", confirmation)
    a.update(review_status="human_confirmed", human_confirmation_pending=False, human_confirmation=link)
    a["limitations"] = [x.replace("Human confirmation remains pending.", "Two independent humans verified the AI-assisted judgments, as reported by the user.") for x in a["limitations"]]
    write(A / "analysis.json", a)
    bc.update(human_confirmed=True, human_confirmation_pending=False, human_confirmation=link)
    # completed_by_human remains false: the consensus computation is automated.
    write(BC / "review/consensus.json", bc)
    bc_analysis = read(BC / "analysis.json")
    bc_analysis.update(human_confirmed=True, human_confirmation_pending=False, human_confirmation=link)
    write(BC / "analysis.json", bc_analysis)
    ac3.update(status="descriptive_ai_assisted_human_confirmed_reference", human_confirmed=True, human_confirmation=link)
    ac3["limitations"][0] = "The user reports two people independently verified every new AI-assisted reference judgment. Original AI opinions remain preserved; identities and blindness to automatic scores are not independently established. Human approval does not establish complete AC3 acceptance."
    for arm in ("baseline", "candidate"):
        ac3[arm]["threshold_evaluation"]["acceptance_status"] = "not_certified_conservative_classification_unmet_and_reference_type_coverage_incomplete"
    write(AC3 / "analysis.json", ac3)
    references = read(AC3 / "reference-consensus.json")
    references.update(status="ai_assisted_reference_consensus_human_confirmed", human_confirmation_pending=False, human_confirmed=True, human_confirmation=link)
    write(AC3 / "reference-consensus.json", references)
    public = ROOT / "frontend/public/reports"
    a_summary = read(public / "a-astra-max-retest-v2.json")
    for key in ("review_status", "human_confirmation_pending", "human_confirmation"):
        a_summary[key] = a[key]
    write(public / "a-astra-max-retest-v2.json", a_summary)
    fields = ("format", "complete", "status", "human_confirmed", "human_confirmation", "provenance", "cohort", "baseline", "candidate", "limitations")
    write(public / "ac3-astra-max-retest-v2.json", {k: ac3[k] for k in fields})
    subprocess.run(["python3", str(ROOT / "scripts/publish_bc_retest_progress_20261101.py")], check=True)
    print(json.dumps({"human_confirmation": str(RECEIPT), "answers": 552, "substantive_judgments_changed": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-user-confirmation", action="store_true",
                        help="Record this conversation's explicit confirmation, once; never silently rescope it")
    main(parser.parse_args().record_user_confirmation)
