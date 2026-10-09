"""Resumable AI-reviewed synthetic pilot through the actual Auditor execution path.

python scripts/run_repair_study.py --prepare --database-url sqlite:////tmp/study.db
python scripts/run_repair_study.py --execute --split diagnostic --max-runs 20
Run inside the backend environment, or provide its dependencies locally.
Human annotation gates are not bypassed: this is explicitly a provisional pilot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def ident(prefix, *parts):
    return (
        prefix
        + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:30].upper()
    )


def load_environment():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def prepare(db, study, fingerprint, offline):
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.models import (
        AuditRunModel,
        ConversationModel,
        ExperimentModel,
        MemoryModel,
        MemoryRelationshipModel,
        MessageModel,
        TestCaseModel,
    )

    groups = []
    models = ["offline-policy-smoke"] if offline else study["target_models"]
    for scenario in study["scenarios"]:
        conversation_id = ident("CS", fingerprint, scenario["conversation_id"], offline)
        if not db.get(ConversationModel, conversation_id):
            db.add(ConversationModel(id=conversation_id, authorised=True))
            db.flush()
            for sequence, message in enumerate(scenario["messages"]):
                db.add(
                    MessageModel(
                        id=ident("MSG", conversation_id, message["message_id"]),
                        conversation_id=conversation_id,
                        source_message_id=message["message_id"],
                        sequence=sequence,
                        role=message["role"],
                        content=message["content"],
                        timestamp=datetime.fromisoformat(message["timestamp"]),
                    )
                )
            for memory in scenario["gold_memories"]:
                db.add(
                    MemoryModel(
                        id=ident("M", conversation_id, memory["memory_id"]),
                        conversation_id=conversation_id,
                        canonical_value=memory["canonical_value"],
                        source_message_ids=memory["source_message_ids"],
                        timestamp=datetime.fromisoformat(memory["timestamp"]),
                        status="confirmed",
                    )
                )
            db.flush()
            for memory in scenario["gold_memories"]:
                for relation in memory["relationships"]:
                    db.add(
                        MemoryRelationshipModel(
                            id=ident(
                                "REL",
                                conversation_id,
                                memory["memory_id"],
                                relation["target_memory_id"],
                            ),
                            memory_id=ident("M", conversation_id, memory["memory_id"]),
                            target_memory_id=ident(
                                "M", conversation_id, relation["target_memory_id"]
                            ),
                            relationship_type=relation["type"],
                        )
                    )
            db.commit()
        for model in models:
            experiment_id = ident(
                "EXP",
                fingerprint,
                study["implementation_fingerprint_sha256"],
                conversation_id,
                model,
            )
            first_id = ident("RUN", experiment_id, study["strategies"][0], 0)
            if not db.get(ExperimentModel, experiment_id):
                dimensions = [test["dimension"] for test in scenario["gold_tests"]]
                db.add(
                    ExperimentModel(
                        id=experiment_id,
                        conversation_id=conversation_id,
                        label=f"AI-reviewed pilot · {scenario['split']} · {scenario['conversation_id']} · {model}",
                        status="TEST_SUITE_GENERATED",
                        test_suite_configuration={
                            "test_budget": len(dimensions),
                            "random_seed": study["random_seed"],
                            "prompt_template_version": study["protocol_id"],
                            "pipeline_provider": "rule_based",
                            "pipeline_model": "ai-reviewed-frozen-suite",
                            "evaluator_provider": "rule_based"
                            if offline
                            else study.get("evaluator_provider", "openrouter"),
                            "evaluator_model": "rule-based-v5"
                            if offline
                            else study["evaluator_model"],
                            "dimensions": dimensions,
                            "suite_mode": "fixed_template",
                        },
                        test_suite_metadata={
                            "test_count": len(dimensions),
                            "dimensions": dimensions,
                            "generator_version": study["protocol_id"],
                        },
                    )
                )
                db.commit()
            run_ids = []
            for strategy in study["strategies"]:
                repeats = 1 if offline else study["repetitions"][scenario["split"]]
                for repeat in range(repeats):
                    run_id = ident("RUN", experiment_id, strategy, repeat)
                    run_ids.append(run_id)
                    if db.get(AuditRunModel, run_id):
                        continue
                    db.add(
                        AuditRunModel(
                            id=run_id,
                            conversation_id=conversation_id,
                            experiment_id=experiment_id,
                            status="TESTS_GENERATED",
                            target_configuration="weak"
                            if strategy == "weak_first_hit"
                            else "strong",
                            provider="rule_based"
                            if offline
                            else study.get("target_provider", "openrouter"),
                            model=model,
                            temperature=study["temperature"],
                            random_seed=study["random_seed"],
                            test_budget=len(scenario["gold_tests"]),
                            prompt_template_version=study["protocol_id"],
                            pipeline_provider="rule_based",
                            pipeline_model="ai-reviewed-frozen-suite",
                            evaluator_provider="rule_based"
                            if offline
                            else study.get("evaluator_provider", "openrouter"),
                            evaluator_model="rule-based-v5"
                            if offline
                            else study["evaluator_model"],
                            memory_strategy=strategy,
                            memory_maintenance_policy="update_aware_consolidation",
                            target_memory_capacity=50,
                            target_memory_writer="rule_based",
                            target_memory_writer_version=RuleBasedMemoryExtractor.VERSION,
                            target_system_adapter="controlled-memory",
                            target_system_adapter_version="controlled-memory-v1",
                            reproducibility_metadata={
                                "schema_version": "reproducibility-v1",
                                "study_protocol": study["protocol_id"],
                                "dataset_fingerprint_sha256": fingerprint,
                                "annotation_origin": study["annotation_origin"],
                                "implementation_fingerprint_sha256": study[
                                    "implementation_fingerprint_sha256"
                                ],
                                "human_validation": "pending",
                                "split": scenario["split"],
                                "repeat": repeat,
                                "seed_control": {
                                    "target": "deterministic_local"
                                    if offline
                                    else "recorded_only",
                                    "pipeline": "frozen_suite",
                                },
                                "execution_budget": {
                                    "max_target_calls": len(scenario["gold_tests"]),
                                    "max_execution_seconds": 300,
                                },
                            },
                        )
                    )
                    db.flush()
                    for test in scenario["gold_tests"]:
                        db.add(
                            TestCaseModel(
                                id=ident("T", run_id, test["test_id"]),
                                run_id=run_id,
                                suite_test_id=None
                                if run_id == first_id
                                else ident("T", first_id, test["test_id"]),
                                dimension=test["dimension"],
                                prompt=test["prompt"],
                                expected_behavior=test["expected_behavior"],
                                supporting_memory_ids=[
                                    ident("M", conversation_id, m)
                                    for m in test["supporting_memory_ids"]
                                ],
                                generator_version=study["protocol_id"],
                                test_type=test["test_type"],
                                quality_status="accepted",
                                grounding_status="grounded",
                                validation_notes="AI pre-review of synthetic facts only; independent human review pending.",
                                target_memory_context=[],
                            )
                        )
                    db.commit()
            experiment = db.get(ExperimentModel, experiment_id)
            if not experiment.test_suite_source_run_id:
                experiment.test_suite_source_run_id = first_id
                db.commit()
            groups.append(
                {
                    "split": scenario["split"],
                    "scenario": scenario["conversation_id"],
                    "model": model,
                    "experiment_id": experiment_id,
                    "run_ids": run_ids,
                }
            )
    return groups


def export(db, groups, study, fingerprint, output):
    from app.api.routes import (
        audit_schema,
        evaluation_review_items_for,
        memory_schema,
        result_for,
        target_memory_trace_payload,
    )
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    from app.models import AuditRunModel, MemoryModel
    from app.services.audit_comparison import compare_audit_evidence
    from sqlalchemy import select

    runs = []
    queue = []
    comparisons = []
    for group in groups:
        for run_id in group["run_ids"]:
            run = db.get(AuditRunModel, run_id)
            item = {
                "group": group["experiment_id"],
                "split": group["split"],
                "run": audit_schema(run).model_dump(mode="json"),
            }
            if run.status == "COMPLETED":
                item["result"] = result_for(run_id, db).model_dump(mode="json")
                item["trace"] = target_memory_trace_payload(run, db).model_dump(
                    mode="json"
                )
                item["evaluations"] = [
                    row.model_dump(mode="json")
                    for row in evaluation_review_items_for(run_id, db)
                ]
                memories = [
                    memory_schema(db, m)
                    for m in db.scalars(
                        select(MemoryModel).where(
                            MemoryModel.conversation_id == run.conversation_id
                        )
                    ).all()
                ]
                for row in evaluation_review_items_for(run_id, db):
                    lexical = RuleBasedBehaviourEvaluator().evaluate(
                        row.test, row.response, memories
                    )
                    receipt = row.response.execution_metadata.memory_input
                    reasons = ["Independent human validation pending"]
                    if lexical.passed != row.automated.passed:
                        reasons.append("Lexical/LLM judge disagreement")
                    if row.automated.evaluator.startswith("fallback"):
                        reasons.append("LLM judge fell back to rules")
                    if row.automated.passed and (
                        receipt is None or receipt.record_count == 0
                    ):
                        reasons.append("Passed without recorded supplied memory")
                    if "Expected concrete answer absent from supplied memory" in row.automated.reason:
                        reasons.append("Expected answer absent from actual supplied memory")
                    if row.test.dimension.value == "conflict_resolution":
                        reasons.append("Conflict handling requires semantic review")
                    queue.append(
                        {
                            "run_id": run_id,
                            "test_id": row.test.test_id,
                            "priority": "high" if len(reasons) > 1 else "sample",
                            "reasons": reasons,
                            "prompt": row.test.prompt,
                            "expected_behavior": row.test.expected_behavior,
                            "response": row.response.response_text,
                            "automated_passed": row.automated.passed,
                            "lexical_passed": lexical.passed,
                            "human_review_status": "pending",
                        }
                    )
            runs.append(item)
        completed = [
            db.get(AuditRunModel, run_id)
            for run_id in group["run_ids"]
            if db.get(AuditRunModel, run_id).status == "COMPLETED"
        ]
        declared_comparisons = [{"name": "primary", **study["primary_comparison"]}]
        if study.get("mechanism_ablation"):
            declared_comparisons.append({"name": "mechanism_ablation", **study["mechanism_ablation"]})
        declared_comparisons.extend(study.get("additional_comparisons", []))
        for comparison in declared_comparisons:
            for before in completed:
                if before.memory_strategy != comparison["before"]:
                    continue
                for after in completed:
                    if (
                        after.memory_strategy == comparison["after"]
                        and before.reproducibility_metadata["repeat"]
                        == after.reproducibility_metadata["repeat"]
                    ):
                        comparisons.append(
                            {
                                "comparison_name": comparison["name"],
                                "before": before.id,
                                "after": after.id,
                                "split": group["split"],
                                **compare_audit_evidence(db, before, after),
                            }
                        )
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol_id": study["protocol_id"],
        "dataset_fingerprint_sha256": fingerprint,
        "notice": study["notice"],
        "human_validation": "pending",
        "implementation_fingerprint_sha256": study["implementation_fingerprint_sha256"],
        "runs": runs,
        "before_after_comparisons": comparisons,
    }
    summary = {}
    for item in runs:
        run = item["run"]
        key = (item["split"], run["model"], run["memory_strategy"])
        row = summary.setdefault(
            key,
            {
                "split": key[0],
                "model": key[1],
                "strategy": key[2],
                "completed_runs": 0,
                "pending_runs": 0,
                "scores": [],
                "tests_passed": 0,
                "tests_total": 0,
            },
        )
        if "result" not in item:
            row["pending_runs"] += 1
            continue
        row["completed_runs"] += 1
        row["tests_passed"] += item["result"]["tests_passed"]
        row["tests_total"] += item["result"]["tests_total"]
        if item["result"]["overall_score"] is not None:
            row["scores"].append(item["result"]["overall_score"])
    for row in summary.values():
        values = row.pop("scores")
        row["mean_memory_health"] = (
            round(sum(values) / len(values), 3) if values else None
        )
    payload["condition_summary"] = list(summary.values())
    (output / "study-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "human-review-queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n"
    )
    annotation_review = {
        "reviewer_type": "AI",
        "human_review_status": "pending",
        "notice": "AI pre-review and source checks are not independent human annotation.",
        "scenarios": [
            {
                "scenario_id": scenario["conversation_id"],
                "split": scenario["split"],
                "memory_source_checks": [
                    {
                        "memory_id": memory["memory_id"],
                        "canonical_value": memory["canonical_value"],
                        "source_message_ids": memory["source_message_ids"],
                        "verbatim_source_match": all(
                            memory["canonical_value"] in message["content"]
                            for message in scenario["messages"]
                            if message["message_id"] in memory["source_message_ids"]
                        ),
                        "relationships": memory["relationships"],
                    }
                    for memory in scenario["gold_memories"]
                ],
                "test_pre_review": scenario["gold_tests"],
                "AI_review_notes": [
                    "Stable location explicitly stated by the synthetic user.",
                    "Database update names the same project and a later replacement value.",
                    "Assignment requirement is distinct from the general language preference.",
                    "Conflicting deployment policies explicitly state neither supersedes the other.",
                    "Log storage is a separate topic and must not update the database record.",
                ],
            }
            for scenario in study["scenarios"]
        ],
    }
    (output / "annotation-pre-review.json").write_text(
        json.dumps(annotation_review, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_sha256": fingerprint,
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in output.glob("*.json")
                    if p.name != "manifest.json"
                },
                "completed_runs": sum("result" in r for r in runs),
                "pending_runs": sum("result" not in r for r in runs),
            },
            indent=2,
        )
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--study",
        type=Path,
        default=ROOT / "datasets/studies/repair-pilot-v1/study.json",
    )
    parser.add_argument("--database-url")
    parser.add_argument("--output", type=Path, default=ROOT / "output/repair-pilot-v1")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--split", choices=["diagnostic", "held_out"], default="diagnostic"
    )
    parser.add_argument("--max-runs", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.max_runs <= 200:
        parser.error("--max-runs must be between 1 and 200")
    load_environment()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    from app.api.routes import evaluate, execute, retry_audit
    from app.database.session import Base, SessionLocal, engine
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.models import AuditRunModel
    from app.schemas import Conversation, Memory, TestCase
    from app.test_generator.quality import RuleBasedTestQualityValidator
    from fastapi import HTTPException
    from sqlalchemy.exc import SQLAlchemyError

    raw = args.study.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    study = json.loads(raw)
    implementation_files = [
        "extraction/rule_based.py",
        "memory_agent/store.py",
        "target_systems/controlled.py",
        "target_ai/providers.py",
        "target_ai/rule_based.py",
        "evaluator/rule_based.py",
        "services/memory_grounding.py",
        "evaluator/llm_judge.py",
        "test_generator/quality.py",
    ]
    if (ROOT / "backend/app/services/memory_entities.py").exists():
        implementation_files.append("services/memory_entities.py")
    study["implementation_fingerprint_sha256"] = hashlib.sha256(
        b"".join(
            (ROOT / "backend/app" / name).read_bytes() for name in implementation_files
        )
    ).hexdigest()
    expected_implementation = study.get("expected_implementation_fingerprint_sha256")
    if expected_implementation and expected_implementation != study["implementation_fingerprint_sha256"]:
        raise SystemExit("Frozen implementation changed. Do not collect or resume this protocol under changed policies.")
    # Preflight validates the synthetic evidence and answer-independent questions.
    for scenario in study["scenarios"]:
        conversation = Conversation(
            conversation_id=scenario["conversation_id"],
            messages=scenario["messages"],
            authorised=True,
            created_at=datetime.fromisoformat(scenario["messages"][0]["timestamp"]),
        )
        extracted = RuleBasedMemoryExtractor().extract(conversation)
        assert extracted, "Independent target ingestion produced no memories"
        memories = [
            Memory(conversation_id=scenario["conversation_id"], status="confirmed", **m)
            for m in scenario["gold_memories"]
        ]
        for test in scenario["gold_tests"]:
            case = TestCase(
                run_id="PREFLIGHT",
                generator_version=study["protocol_id"],
                **{
                    k: v
                    for k, v in test.items()
                    if k
                    in {
                        "test_id",
                        "dimension",
                        "prompt",
                        "expected_behavior",
                        "supporting_memory_ids",
                        "test_type",
                    }
                },
            )
            assessment = RuleBasedTestQualityValidator().validate(case, memories)
            if assessment.quality_status.value != "accepted":
                raise SystemExit(
                    f"Preflight rejected {scenario['conversation_id']}/{case.test_id}: {assessment.reason}"
                )
    if (
        args.execute
        and not args.offline
        and "openrouter"
        in {
            study.get("target_provider", "openrouter"),
            study.get("evaluator_provider", "openrouter"),
        }
        and not os.getenv("OPENROUTER_API_KEY", "").strip()
    ):
        raise SystemExit("OPENROUTER_API_KEY is missing. No cloud requests were made.")
    if args.offline:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        groups = prepare(db, study, fingerprint, args.offline)
        if args.execute and args.split == "held_out":
            diagnostic_ids = [
                run_id
                for group in groups
                if group["split"] == "diagnostic"
                for run_id in group["run_ids"]
            ]
            if any(
                db.get(AuditRunModel, run_id).status != "COMPLETED"
                for run_id in diagnostic_ids
            ):
                raise SystemExit(
                    "Finish diagnostic runs before executing the frozen held-out suite."
                )
        calls = 0
        if args.execute:
            for group in groups:
                if group["split"] != args.split:
                    continue
                for run_id in group["run_ids"]:
                    if calls >= args.max_runs:
                        break
                    run = db.get(AuditRunModel, run_id)
                    if run.status == "COMPLETED":
                        continue
                    try:
                        if run.status == "FAILED":
                            retry_audit(run_id, db)
                        if run.status == "TESTS_GENERATED":
                            execute(run_id, db)
                        db.refresh(run)
                        if run.status == "TESTS_EXECUTED":
                            evaluate(run_id, db)
                        print(
                            f"Completed {group['split']} {run.memory_strategy} {group['model']}",
                            flush=True,
                        )
                    except (
                        HTTPException,
                        SQLAlchemyError,
                        ValueError,
                        RuntimeError,
                    ) as exc:
                        db.rollback()
                        print(
                            f"Run paused: {run_id}; {type(exc).__name__}. Saved responses will be reused.",
                            flush=True,
                        )
                        export(db, groups, study, fingerprint, args.output)
                        raise SystemExit(1) from None
                    calls += 1
        export(db, groups, study, fingerprint, args.output)
        print(
            json.dumps(
                {
                    "groups": len(groups),
                    "runs": sum(len(g["run_ids"]) for g in groups),
                    "executed_this_call": calls,
                    "output": str(args.output),
                    "human_validation": "pending",
                }
            )
        )


if __name__ == "__main__":
    main()
