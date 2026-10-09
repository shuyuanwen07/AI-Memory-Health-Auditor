"""Deterministic controlled target used for offline experiments.

This connector intentionally receives the same private memory context as cloud
targets. It must never read ``TestCase.expected_behavior``: that field belongs
to the evaluator and is deliberately withheld from the system under test.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from app.schemas import AuditRun, Dimension, TargetConfiguration, TargetMemoryInputEvidence, TargetResponse, TestCase
from app.services.interfaces import TargetAIConnector


def selected_memory_context(test: TestCase, configuration: TargetConfiguration) -> list[str]:
    """Return records deliberately exposed to this controlled target.

    The generator orders records from older/general to newer/contextual. A
    strong target sees all relevant records and can reconcile them. A weak
    target sees only the first candidate record, modelling first-hit retrieval.
    """
    context = list(dict.fromkeys(item.strip() for item in test.target_memory_context if item and item.strip()))
    return context[:1] if configuration == TargetConfiguration.WEAK else context


def private_context_instruction(test: TestCase, configuration: TargetConfiguration) -> str:
    """Build target-side instructions without evaluator-only expected behaviour.

    All test-specific content comes from ``target_memory_context``. The static
    policy defines the experimental condition; ``expected_behavior`` is never
    interpolated, logged, or supplied to an external provider.
    """
    context = selected_memory_context(test, configuration)
    records = "\n".join(f"- {record}" for record in context) or "- No relevant memory records were supplied."
    if configuration == TargetConfiguration.STRONG:
        policy = (
            "Use all supplied records. Prefer an explicit later update over an older record; "
            "treat a current requirement as more relevant than a general preference; and if "
            "records directly conflict without a stated resolution, acknowledge the conflict and request clarification."
        )
    else:
        policy = "Use only the single retrieved record below. Do not reconcile records that were not retrieved."
    if configuration == TargetConfiguration.STRONG and len(context) > 1 and any(
        "neither" in record.lower() and "supersedes" in record.lower() for record in context
    ):
        policy += (
            " The supplied policies explicitly say neither supersedes the other. This is an unresolved "
            "conflict, not a later update. Your answer must identify the two incompatible options and "
            "ask which policy to follow. Do not suggest selecting by recency or invent a priority."
            " Describe each policy as a source statement, not as your recommendation. "
            "Do not begin or end with a chosen storage option and then add a clarification request. "
            "Logging destinations and database technologies are separate facts, not secret-storage policies."
        )
    return (
        f"PRIVATE TARGET MEMORY CONTEXT\n{records}\n\nMEMORY POLICY\n{policy}\n\n"
        "RESPONSE FORMAT\n"
        "Answer personal and project facts only when supported by the supplied records. If no relevant "
        "record supports the answer, say you do not have enough remembered information; do not guess "
        "from a project name or general knowledge. For unresolved conflicting records, state the conflict "
        "and ask for clarification before selecting either option; later chronology alone does not "
        "resolve an explicitly unresolved conflict. Otherwise start with one unambiguous concrete factual "
        "answer from the records, followed by at most one short sentence of reasoning."
    )


def memory_input_evidence(test: TestCase, configuration: TargetConfiguration, instructions: str) -> TargetMemoryInputEvidence:
    context = selected_memory_context(test, configuration)
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    return TargetMemoryInputEvidence(
        record_count=len(context),
        context_sha256=digest(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
        instruction_sha256=digest(instructions), prompt_sha256=digest(test.prompt),
    )


class RuleBasedTargetAIConnector(TargetAIConnector):
    """Offline baseline with the same private-context isolation as cloud targets."""

    def execute(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        context = selected_memory_context(test, audit.target_configuration)
        text = self._respond(test.dimension, context, audit.target_configuration)
        return TargetResponse(
            response_id=f"R{test.test_id[1:]}", test_id=test.test_id, run_id=audit.run_id,
            response_text=text, model=audit.model, temperature=audit.temperature,
            execution_metadata={"request_attempts": 0, "latency_ms": 0.0, "response_source": "rule_based",
                                "memory_input": memory_input_evidence(test, audit.target_configuration,
                                                                      private_context_instruction(test, audit.target_configuration))},
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _respond(dimension: Dimension, context: list[str], configuration: TargetConfiguration) -> str:
        if not context:
            return "I do not have a relevant remembered record, so I cannot answer reliably."

        retrieved = context[0] if configuration == TargetConfiguration.WEAK else context[-1]
        if configuration == TargetConfiguration.WEAK:
            return f"Based on the retrieved record, {retrieved}"
        if dimension == Dimension.CONFLICT_RESOLUTION:
            records = " ".join(context).lower()
            if "conflict" in records or "must not" in records:
                return "The remembered records conflict, so I would request clarification before relying on either one."
            return f"I would use the later record because it takes precedence: {retrieved}"
        if dimension == Dimension.APPROPRIATE_USE:
            return f"I would follow the current contextual requirement: {retrieved}"
        if dimension == Dimension.FRESHNESS:
            return f"I would use the later remembered record: {retrieved}"
        return retrieved
