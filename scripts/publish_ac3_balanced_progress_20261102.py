"""Publish saved diagnostic progress and verified final metrics; no model calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
import os

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
DEST = ROOT / "frontend/public/reports/ac3-balanced-diagnostic-v1.json"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = read(STUDY / "protocol.json")
    refs = read(STUDY / "reference-consensus.json")
    progress = {}
    for arm in ("original", "revised"):
        counts = Counter()
        for job in protocol["jobs"]:
            if job["arm"] != arm:
                continue
            path = STUDY / "scores" / arm / (job["review_id"] + ".json")
            counts[read(path)["state"] if path.exists() else "not_dispatched"] += 1
        errors = sum(n for state, n in counts.items() if state not in ("returned", "dispatched", "not_dispatched"))
        progress[arm] = {"planned": 150, "returned": counts["returned"], "errors": errors,
                         "remaining": 150 - counts["returned"] - errors}
    analysis_path = STUDY / "analysis.json"
    analysis = None
    final = None
    if analysis_path.exists():
        candidate = read(analysis_path)
        if candidate.get("complete"):
            # A stale analysis never overrides current journals or inputs.
            for relative, expected in candidate["provenance"]["input_file_sha256"].items():
                if sha(ROOT / relative) != expected:
                    raise ValueError("Analysis inputs changed; preserve the previous public summary")
            for relative, expected in candidate["provenance"]["score_file_sha256"].items():
                if sha(STUDY / relative) != expected:
                    raise ValueError("Analysis score receipt changed")
            final = candidate
            analysis = {k: final[k] for k in ("cohort", "original", "revised", "paired_counts", "history_cluster_bootstrap", "limitations", "execution")}
    report = {
        "format": "ac3-balanced-diagnostic-dashboard-v1", "updated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max", "curated_answers": True,
        "histories": 30, "cases": 150, "planned_calls": 300,
        "paired_order": {"original_first": 75, "revised_first": 75},
        "complete": final is not None, "human_confirmed": bool(final and final.get("human_confirmed")),
        "reference_review": {"model": "gpt-6-astra", "reasoning_effort": "max", "independent_reviewers": 2,
                             "ready": refs["ready_for_scoring"], "actual_failure_types": refs["actual_agreed_failure_type_counts"],
                             "passes": refs["verdict_counts"].get("pass", 0)},
        "progress": progress, "analysis": analysis, "protocol_sha256": sha(STUDY / "protocol.json"),
    }
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=DEST.parent, prefix=DEST.name, suffix=".pending", delete=False) as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
        temp = f.name
    os.replace(temp, DEST)
    print(json.dumps({"complete": report["complete"], "progress": progress}), flush=True)
    return report["complete"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    while True:
        complete = main()
        if complete or not args.watch:
            break
        time.sleep(15)
