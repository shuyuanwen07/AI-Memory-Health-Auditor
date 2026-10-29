"""Freeze an unexecuted official LongMemEval candidate-held-out C subset.

This preparer makes no network or model calls. It verifies the locally pinned
source, the pre-execution release manifest, and every selected Oracle record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE = Path("output/longmemeval-official-v1")
UPSTREAM = Path("experiments/longmemeval-expanded-20261019/upstream-evaluator")
DEFAULT_OUTPUT = Path("artifacts/local/phase4-c-openrouter-20261027-v5")
DEFAULT_PRIOR_RUN = Path("artifacts/local/phase4-c-openrouter-20261027-v4/C-live.json")
DEFAULT_PRIOR_INTERRUPTION = Path("artifacts/local/phase4-c-openrouter-20261027-v4/interruption-receipt.json")
MODEL = "openai/gpt-6-luna"
STRATEGIES = ["weak_first_hit", "strong_rule_based"]
CATEGORIES = {
    "abstention", "knowledge-update", "multi-session", "single-session-assistant",
    "single-session-preference", "single-session-user", "temporal-reasoning",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(root: Path = ROOT, output: Path | None = None,
            prior_run: Path | None = None,
            prior_interruption: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    destination = (output or root / DEFAULT_OUTPUT).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty candidate directory: {destination}")

    release = root / RELEASE
    source_manifest_path = release / "source-manifest.json"
    prepared_path = release / "prepared-release.json"
    execution_path = release / "execution-manifest.json"
    source_manifest = _read_json(source_manifest_path)
    if "MIT" not in str(source_manifest.get("license", "")):
        raise ValueError("The official dataset license is not recorded as MIT in its manifest.")
    oracle_meta = next((item for item in source_manifest.get("files", [])
                        if item.get("file", "").endswith("/source/longmemeval_oracle.json")), None)
    if oracle_meta is None:
        raise ValueError("The pinned source manifest has no LongMemEval Oracle file entry.")
    oracle_path = root / oracle_meta["file"]
    if oracle_path.stat().st_size != oracle_meta["bytes"] or _sha(oracle_path) != oracle_meta["sha256"]:
        raise ValueError("The downloaded Oracle source does not match its manifest bytes and hash.")
    source_records = _read_json(oracle_path)
    if len(source_records) != 500:
        raise ValueError(f"Expected 500 official Oracle records, found {len(source_records)}.")
    source_by_id = {record["question_id"]: record for record in source_records}
    if len(source_by_id) != len(source_records):
        raise ValueError("The Oracle source contains duplicate question IDs.")

    prepared = _read_json(prepared_path)
    if "no answer or target output used" not in prepared.get("selection", "").casefold():
        raise ValueError("Prepared release does not document outcome-independent selection.")
    selected = [item for item in prepared.get("records", [])
                if item.get("split") == "candidate-held-out"]
    if len(selected) != 14:
        raise ValueError(f"Expected 14 frozen candidate-held-out cases, found {len(selected)}.")
    counts = Counter(item.get("category") for item in selected)
    if set(counts) != CATEGORIES or any(counts[category] != 2 for category in CATEGORIES):
        raise ValueError("Candidate-held-out release is not balanced at two cases per category.")

    execution = _read_json(execution_path)
    if (execution.get("candidate_held_out_executions") != 0
            or execution.get("semantic_scores") != 0
            or execution.get("human_labels") != 0):
        raise ValueError("Candidate-held-out outcomes already exist; refusing to relabel them as unused.")

    cases: list[dict[str, Any]] = []
    selection_receipts: list[dict[str, Any]] = []
    seen_evidence_sessions: set[str] = set()
    for item in selected:
        files = [candidate for candidate in item.get("files", []) if candidate.get("mode") == "oracle"]
        if len(files) != 1:
            raise ValueError("Each selected question must bind exactly one Oracle input file.")
        receipt = files[0]
        path = root / receipt["file"]
        if path.stat().st_size != receipt["bytes"] or _sha(path) != receipt["sha256"]:
            raise ValueError(f"Prepared Oracle item does not match its manifest: {receipt['file']}")
        prepared_record = _read_json(path)
        if isinstance(prepared_record, list) and len(prepared_record) == 1:
            record = prepared_record[0]
        else:
            record = prepared_record
        if not isinstance(record, dict) or record.get("question_id") != item.get("question_id"):
            raise ValueError("Prepared Oracle item question ID does not match its release entry.")
        if record["question_id"] not in source_by_id or source_by_id[record["question_id"]] != record:
            raise ValueError("Prepared Oracle item is not byte-equivalent to a record in the pinned source.")
        sessions = set(item.get("evidence_session_ids", []))
        if seen_evidence_sessions.intersection(sessions):
            raise ValueError("Frozen candidate cases reuse an official evidence session.")
        seen_evidence_sessions.update(sessions)
        cases.append(record)
        selection_receipts.append({
            "question_id": item["question_id"], "category": item["category"],
            "oracle_file": receipt["file"], "oracle_sha256": receipt["sha256"],
            "evidence_session_ids": sorted(sessions),
        })

    upstream_source = root / UPSTREAM / "evaluate_qa.py"
    upstream_binding_path = root / UPSTREAM / "source-binding.json"
    upstream_license = root / UPSTREAM / "LICENSE"
    binding = _read_json(upstream_binding_path)
    if _sha(upstream_source) != binding.get("source_sha256"):
        raise ValueError("Pinned LongMemEval scorer source does not match source-binding.json.")

    amendment = None
    if prior_run is not None:
        prior_path = prior_run if prior_run.is_absolute() else root / prior_run
        prior = _read_json(prior_path)
        prior_usable_grades = sum(bool(item.get("verdict_usable")) for item in prior.get("grades", []))
        if prior.get("status") != "failed" or len(prior.get("target_receipts", [])) < 1:
            raise ValueError("The prior candidate must be a preserved partial run with target receipts.")
        if prior_usable_grades < 1 or len(prior.get("grades", [])) < prior_usable_grades:
            raise ValueError("The prior candidate grade counts are inconsistent.")
        interruption = None
        interruption_path = prior_interruption
        if interruption_path is None and (prior_path.parent / "interruption-receipt.json").is_file():
            interruption_path = prior_path.parent / "interruption-receipt.json"
        if interruption_path is not None:
            interruption_path = interruption_path if interruption_path.is_absolute() else root / interruption_path
            interruption = _read_json(interruption_path)
            if (interruption.get("status_code") != 503
                    or interruption.get("last_saved_target_receipt_count") != len(prior.get("target_receipts", []))
                    or interruption.get("run_file_sha256") != _sha(prior_path)):
                raise ValueError("Prior interruption receipt does not match the preserved partial run.")
        elif prior.get("error_type") == "HTTPException":
            raise ValueError("The provider interruption receipt is required for this partial run.")
        prior_failed_grades = len(prior.get("grades", [])) - prior_usable_grades
        triggers = [
            f"The prior run preserved {len(prior.get('target_receipts', []))} target responses and {prior_usable_grades}/{len(prior.get('grades', []))} usable grades before interruption.",
            "Five prior grader calls ended with finish_reason=length and no yes/no text at a 128-token limit.",
        ]
        if interruption:
            triggers.append("The prior target request then failed with HTTP 503; its exact request body and provider request ID were not captured by v4.")
        amendment = {
            "kind": "unified_scorer_control_and_target_retry_receipt_amendment_after_partial_execution",
            "prior_candidate_run": str(prior_path.resolve().relative_to(root)),
            "prior_candidate_run_sha256": _sha(prior_path),
            "prior_protocol_sha256": prior.get("protocol_sha256"),
            "target_responses_before_amendment": len(prior.get("target_receipts", [])),
            "usable_grades_before_amendment": prior_usable_grades,
            "unusable_grades_before_amendment": prior_failed_grades,
            "prior_grading_labels_regraded_as_a_separate_round": True,
            "prior_interruption_receipt": str(interruption_path.resolve().relative_to(root)) if interruption_path else None,
            "prior_interruption_receipt_sha256": _sha(interruption_path) if interruption_path else None,
            "trigger": triggers,
            "change": "Score every target response in one new round using OpenRouter default routing, reasoning_effort=none, and max_tokens=128; preserve the previous grading round; capture failed target request payloads before retrying.",
            "unchanged": ["selected cases", "target model and settings", "memory strategies", "target prompts", "upstream grading prompt", "yes/no scoring rule"],
            "interpretation": "This scorer amendment follows prior target outputs and automated grades. The new grading round is a post-hoc exploratory sensitivity round, not a preregistered or independent result.",
        }

    destination.mkdir(parents=True, exist_ok=True)
    subset_path = destination / "longmemeval-subset.json"
    _write_json(subset_path, cases)
    scorer_dir = destination / "upstream"
    scorer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(upstream_source, scorer_dir / upstream_source.name)
    shutil.copyfile(upstream_binding_path, scorer_dir / upstream_binding_path.name)
    shutil.copyfile(upstream_license, scorer_dir / upstream_license.name)

    app_files = sorted((root / "backend/app").rglob("*.py"))
    app_source = {
        str(path.relative_to(root)): _sha(path)
        for path in [*app_files, root / "scripts/run_phase4_c.py", root / "scripts/longmemeval_grading.py",
                     root / "scripts/prepare_phase4_c_candidate.py"]
    }
    protocol = {
        "format": "proposal-c-candidate-protocol-v1",
        "id": "phase4-c-openrouter-gpt6-luna-candidate-heldout-v3",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_before_candidate_execution; human_reference_pending",
        "authorization": {
            "provider": "OpenRouter", "model": MODEL,
            "budget": "User authorized an unlimited model-call budget for this work.",
        },
        "source": {
            "dataset": "LongMemEval cleaned Oracle",
            "license": source_manifest["license"],
            "revision": oracle_meta["commit"],
            "source_manifest": str(source_manifest_path.relative_to(root)),
            "source_manifest_sha256": _sha(source_manifest_path),
            "oracle_source": oracle_meta["file"],
            "oracle_source_sha256": oracle_meta["sha256"],
            "oracle_record_count": len(source_records),
        },
        "selection": {
            "split": "candidate-held-out",
            "release_manifest": str(prepared_path.relative_to(root)),
            "release_manifest_sha256": _sha(prepared_path),
            "execution_manifest": str(execution_path.relative_to(root)),
            "execution_manifest_sha256_at_freeze": _sha(execution_path),
            "case_count": len(cases),
            "strata": dict(sorted(counts.items())),
            "selected_cases": selection_receipts,
            "selection_invariant": "Use the already frozen pre-execution selection; do not replace cases after observing outputs.",
        },
        "target": {
            "provider": "openrouter", "model": MODEL,
            "temperature": 0, "random_seed": 42,
            "memory_strategies": STRATEGIES,
            "repetitions_per_strategy": 3,
            "target_memory_capacity": 50,
            "reader_configuration": "strong",
            "target_memory_profile": {
                "label": "C candidate shared reader",
                "max_retrieved_records": 50,
                "context_character_budget": 16000,
                "output_token_limit": 2048,
                "retain_assistant_history": True,
                "retrieve_message_context": False,
                "isolate_project_scope": False,
                "prefer_current_state": False,
            },
            "planned_target_requests": len(cases) * len(STRATEGIES) * 3,
        },
        "scorer": {
            "provider": "openrouter", "model": MODEL,
            "prompt_source": "Pinned LongMemEval get_anscheck_prompt from the bound upstream revision.",
            "transport": "OpenRouter chat completions using default provider routing; temperature 0; reasoning_effort none; max_tokens 128; bounded three attempts.",
            "provider_routing": "No scorer endpoint filters are sent. OpenRouter documents a reasoning_effort parameter for the chat-completions API; this round sets it to none to avoid exhausting the output budget on hidden reasoning.",
            "parsing": "LongMemEval yes/no response convention; raw response and finish reason retained.",
            "deviation": "GPT-6 Luna is not LongMemEval's official metric model and is the same model as the target; scores are model-graded pilot evidence only.",
        },
        "C": {"judge_model": MODEL},
        "analysis": {
            "unit": "case within repetition",
            "reported_values": "all per-strategy, per-repetition scores plus paired score differences and ordering",
            "compare_only_within_each_repetition": True,
            "cross_benchmark_score_subtraction": False,
            "minimum_decided_cases_for_ranking": 14,
            "threshold": None,
            "no_significance_or_generalisation_claim": True,
        },
        "protocol_amendment": amendment,
        "human_review": {
            "independent_reviewers_required": 2,
            "reviewers_must_not_see_model_scores_or_each_others_labels": True,
            "status": "pending; automated grader is not a human reference",
        },
        "limitations": [
            "14/500 cases; a local compatibility subset, not the complete official benchmark.",
            "The official candidate-held-out partition is public; this is not a secret dataset.",
            "The target and model grader use the same GPT-6 Luna model, so model scores are not independent.",
            "A recorded seed does not guarantee provider-deterministic output.",
            "No independent human references or preregistered performance threshold are available yet.",
            "The v5 scorer configuration was introduced after v4 had produced target outputs and automated grades; v5 therefore preserves v4 grades separately and re-grades all 84 target responses under one consistent scorer configuration. This is an exploratory post-hoc round. The target run also resumes after a recorded HTTP 503; earlier v4 did not preserve that failed request body.",
        ],
        "app_source": app_source,
        "source_files": {"benchmark_subset_sha256": _sha(subset_path)},
        "runner_sha256": _sha(root / "scripts/run_phase4_c.py"),
        "grader_helper_sha256": _sha(root / "scripts/longmemeval_grading.py"),
        "frozen_subset_sha256": _sha(subset_path),
        "upstream_scorer_binding": binding,
    }
    _write_json(destination / "protocol.json", protocol)
    return {
        "output": str(destination), "case_count": len(cases),
        "categories": dict(sorted(counts.items())),
        "planned_target_requests": protocol["target"]["planned_target_requests"],
        "planned_scorer_requests": len(cases) * len(STRATEGIES) * 3,
        "subset_sha256": protocol["frozen_subset_sha256"],
        "protocol_sha256": _sha(destination / "protocol.json"),
        "model_calls_made": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prior-run", type=Path, help="Preserved partial C run requiring a documented continuation.")
    parser.add_argument("--prior-interruption", type=Path, help="Sidecar receipt for a prior HTTP 503 interruption.")
    args = parser.parse_args()
    prior_run = args.prior_run
    if prior_run is None and (args.root / DEFAULT_PRIOR_RUN).is_file():
        prior_run = DEFAULT_PRIOR_RUN
    prior_interruption = args.prior_interruption
    if prior_interruption is None and (args.root / DEFAULT_PRIOR_INTERRUPTION).is_file():
        prior_interruption = DEFAULT_PRIOR_INTERRUPTION
    print(json.dumps(prepare(args.root, args.output, prior_run, prior_interruption), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
