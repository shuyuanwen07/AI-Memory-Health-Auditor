"""Reproduce generation/review on the exact user-approved synthetic facts.

This performs real selected-provider model calls but writes no audit database and supplies
no research labels. Run with --output to preserve both failed and passed traces.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.schemas import AuditRun, Memory, MemoryRelationship
from app.test_generator.agent import AgentTestGenerator
from app.test_generator.llm_generator import LLMTestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.target_ai.providers import ollama_base_url


def approved_memories(source_path: Path, approval_path: Path) -> tuple[list[Memory], str]:
    raw = source_path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    source = json.loads(raw)
    approval = json.loads(approval_path.read_text())
    if (source.get("source_origin") != "synthetic" or source.get("authorised") is not True
            or approval.get("approval_scope") != "synthetic_engineering_smoke_only"
            or approval.get("source_sha256") != source_hash):
        raise ValueError("This runner requires the exact authorised, approved synthetic release.")
    messages = {message["message_id"]: message for message in source["messages"]}
    confirmed = approval["confirmed_source_message_ids"]
    if len(confirmed) != len(set(confirmed)) or set(confirmed) != set(messages):
        raise ValueError("The synthetic approval must bind every source fact exactly once.")
    ids = {source_id: f"M{index:03d}" for index, source_id in enumerate(confirmed, 1)}
    memories = []
    for source_id in confirmed:
        message = messages[source_id]
        memories.append(Memory(
            memory_id=ids[source_id], conversation_id="SYN-QWEN-MAPLE",
            canonical_value=message["content"], status="confirmed",
            source_message_ids=[source_id], timestamp=message.get("timestamp"),
            relationships=[MemoryRelationship(
                type=edge["type"], target_memory_id=ids[edge["target_message_id"]],
                evidence_message_ids=[edge["source_message_id"], edge["target_message_id"]],
            ) for edge in approval["relationships"] if edge["source_message_id"] == source_id],
        ))
    return memories, source_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    selected_model = args.model or ("qwen3:1.7b" if args.provider == "ollama" else "openai/gpt-6-luna")
    memories, source_hash = approved_memories(
        ROOT / "datasets/smoke/qwen-four-dimension-source-v1.json",
        ROOT / "datasets/smoke/qwen-four-dimension-approval-v1.json",
    )
    now = datetime.now(timezone.utc)
    audit = AuditRun(
        run_id="SYN-QWEN-GENERATION", conversation_id="SYN-QWEN-MAPLE", status="CREATED",
        target_configuration="strong", provider=args.provider, model=selected_model,
        temperature=0, random_seed=42, test_budget=4,
        prompt_template_version="synthetic-generation-smoke-v1", created_at=now,
    )
    client = PipelineLLMClient(args.provider, selected_model)
    generator = AgentTestGenerator(client=client, planner_client=client, reviewer_client=client)
    announced = set()

    def progress():
        for index, row in enumerate((generator.last_observation or {}).get("writer_rounds", [])):
            event = (index, row.get("stage"), row.get("status"))
            if event not in announced:
                announced.add(event)
                print(json.dumps({"event": "writer_round", "index": event[0], "stage": event[1], "status": event[2]}), flush=True)
        for index, row in enumerate((generator.last_observation or {}).get("semantic_reviews", [])):
            event = ("review", index, row.get("status"))
            if event not in announced:
                announced.add(event)
                mode = (row.get("input_payload") or {}).get("review_mode", "combined")
                print(json.dumps({"event":"review_pass", "index":index, "mode":mode, "status":event[2]}), flush=True)

    generator.progress_observer = progress
    report = {
        "scope": "synthetic_generation_and_review_smoke_only", "research_evidence": False,
        "source_sha256": source_hash, "approval_scope": "synthetic_engineering_smoke_only",
        "provider": client.provider, "model": client.model, "started_at": now.isoformat(),
        "agent_version": generator.VERSION, "reviewer_version": generator.REVIEWER_VERSION,
        "structured_writer_version": LLMTestGenerator.VERSION, "template_version": RuleBasedTestGenerator.VERSION,
        "test_budget": 4, "audit_database_writes": 0,
    }
    try:
        if client.provider == "ollama":
            response = httpx.get(f"{ollama_base_url()}/api/tags", timeout=10)
            response.raise_for_status()
            inventory = next((row for row in response.json().get("models", [])
                              if row.get("name") == client.model or row.get("model") == client.model), None)
            if inventory is None:
                raise PipelineRequestError("The selected local Qwen model is not installed; the smoke did not dispatch inference.", 503)
            report["model_inventory"] = {key: inventory.get(key) for key in ("name", "model", "digest", "size", "details")}
            report["inventory_observed_at"] = datetime.now(timezone.utc).isoformat()
        tests = generator.generate(memories, audit)
        report.update(status="completed", tests=[test.model_dump(mode="json") for test in tests])
    except PipelineRequestError as exc:
        report.update(status="failed", error_code=type(exc).__name__, error=exc.detail)
    except Exception as exc:
        report.update(status="failed", error_code=type(exc).__name__)
    report.update(observation=generator.last_observation, finished_at=datetime.now(timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "test_count": len(report.get("tests", [])),
                      "error": report.get("error"), "report": str(args.output)}), flush=True)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
