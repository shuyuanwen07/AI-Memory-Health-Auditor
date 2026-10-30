"""The deterministic, persisted controlled target used by Foundation."""
import copy
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import uuid4
from app.models import TargetAgentMemoryModel, TargetAgentRetrievalModel

from app.memory_agent import SqlTargetMemoryStore, get_target_memory_writer
from app.memory_agent.retrieval_agent import AgentMemoryRetriever
from app.schemas import (
    AuditRun, Conversation, MemoryStrategy, TargetMemoryMaintenancePolicy,
    TargetResponse, TestCase,
)
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.openrouter import validate_profile_reasoning
from app.target_ai.rule_based import selected_memory_context, target_question_input
from app.memory_agent.identity_applicability import identity_analysis_applicable
from app.services.agent_trace import record_agent_execution
from app.target_systems.interfaces import TargetSystemAdapter


class ControlledTargetSystemAdapter(TargetSystemAdapter):
    """Wrap the built-in private memory store behind the target-system seam."""

    adapter_id = "controlled-memory"
    version = "controlled-memory-v35"

    def __init__(self, db: Session, audit: AuditRun):
        try:
            validate_profile_reasoning(audit.provider.value, audit.model, audit.target_memory_profile)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        self.db = db
        self.audit = audit
        self.store = SqlTargetMemoryStore(
            db,
            extractor=get_target_memory_writer(
                audit.pipeline_provider, audit.pipeline_model,
                audit.target_memory_writer or "rule_based",
                retain_assistant_history=audit.target_memory_profile.retain_assistant_history,
            ),
            maintenance_policy=TargetMemoryMaintenancePolicy(
                audit.memory_maintenance_policy or "update_aware_consolidation"
            ),
            capacity=audit.target_memory_capacity if audit.target_memory_capacity is not None else 50,
            profile=audit.target_memory_profile,
            retrieval_agent=(AgentMemoryRetriever(audit.retrieval_provider, audit.retrieval_model)
                            if audit.retrieval_mode.value == "agent"
                            and audit.retrieval_provider and audit.retrieval_model else None),
        )
        self._conversation: Conversation | None = None
        self._last_retrieval_id: str | None = None
        self._diagnostic_packet_id: str | None = None
        # Private harness capture only; never included in trace() or ordinary ledger output.
        self.last_answer_validation_observation: dict | None = None

    def ingest(self, conversation: Conversation) -> None:
        if not conversation.authorised:
            raise HTTPException(403, "Authorise this conversation before initialising the target memory system.")
        messages = [message for message in conversation.messages if message.role.strip().lower() == "user"]
        if self.audit.reproducibility.intervention == "supplement_source_evidence" and not messages:
            raise HTTPException(422, "Source replay requires authorised user messages; this history has none.")
        replay_value = None
        if self.audit.reproducibility.intervention == "supplement_source_evidence":
            replay_value = "Authorised user source history:\n" + "\n".join(
                f"Source statement ({message.original_timestamp or 'time not recorded'}): {message.content}"
                for message in messages
            )
            if len(replay_value) > self.audit.target_memory_profile.context_character_budget:
                raise HTTPException(422, "The source replay exceeds this run's memory context budget. Prepare a new diagnostic configuration before replaying this history.")
        self.store.ingest(self.audit.run_id, conversation)
        self._conversation = conversation
        self._diagnostic_packet_id = None
        if replay_value is not None:
            # Prepare replay from the target's original input, independently of
            # audit memories, expected answers, question IDs or review labels.
            value = replay_value
            record = self.db.scalar(select(TargetAgentMemoryModel).where(
                TargetAgentMemoryModel.run_id == self.audit.run_id,
                TargetAgentMemoryModel.canonical_value == value,
                TargetAgentMemoryModel.lifecycle_state == "DIAGNOSTIC_ONLY"))
            if record is None:
                record = TargetAgentMemoryModel(id=f"TM{uuid4().hex[:20].upper()}", run_id=self.audit.run_id,
                    source_conversation_id=conversation.conversation_id, canonical_value=value,
                    scope="episodic", lifecycle_state="DIAGNOSTIC_ONLY",
                    source_message_ids=[message.message_id for message in messages],
                    observed_at=messages[-1].timestamp or conversation.created_at, write_order=10000)
                self.db.add(record)
                self.db.flush()
            self._diagnostic_packet_id = record.id

    def prepare_answer(self, test: TestCase, audit: AuditRun):
        """Prepare the exact private target input through the normal memory store.

        The returned test contains retrieved context but no expected answer or
        evaluator evidence. Callers must retain the returned retrieval record
        and must not treat preparation as an authorized model dispatch.
        """
        try:
            validate_profile_reasoning(audit.provider.value, audit.model, audit.target_memory_profile)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if self._conversation is None:
            raise RuntimeError("The target system must ingest its authorised conversation before answering.")
        self.last_answer_validation_observation = None
        target_test = test.model_copy(update={"expected_behavior": "", "supporting_memory_ids": [],
                                             "target_identity_evidence": None,
                                             "target_identity_failure_receipt": None})
        retrieval = self.store.retrieve(
            self.audit.run_id, self._conversation, target_test, MemoryStrategy(audit.memory_strategy),
            retrieval_mode=audit.retrieval_mode.value,
        )
        self._last_retrieval_id = retrieval.evidence.retrieval_id
        intervention = audit.reproducibility.intervention
        if intervention and audit.memory_strategy == MemoryStrategy.RELATIONSHIP_PACKET:
            raise HTTPException(422, 'Relationship packet is not supported with diagnostic source interventions.')
        if intervention == "remove_memory":
            retrieval.context = []
            retrieval.evidence.selected_memory_ids = []
        elif intervention == "supplement_source_evidence" and self._diagnostic_packet_id:
            record = self.db.get(TargetAgentMemoryModel, self._diagnostic_packet_id)
            if record is None or record.run_id != self.audit.run_id:
                raise RuntimeError("The target-owned source replay packet is unavailable.")
            context, selected_ids = [record.canonical_value], [record.id]
            used = len(record.canonical_value)
            profile = self.audit.target_memory_profile
            for value, memory_id in zip(retrieval.context, retrieval.evidence.selected_memory_ids, strict=True):
                if len(context) >= profile.max_retrieved_records:
                    break
                if value in context or used + len(value) > profile.context_character_budget:
                    continue
                context.append(value)
                selected_ids.append(memory_id)
                used += len(value)
            retrieval.context = context
            retrieval.evidence.selected_memory_ids = selected_ids
        if intervention:
            row = self.db.get(TargetAgentRetrievalModel, self._last_retrieval_id)
            row.selected_memory_ids = list(retrieval.evidence.selected_memory_ids)
            row.ranking_evidence = [{**item, "selected": item["memory_id"] in row.selected_memory_ids} for item in row.ranking_evidence]
            self.db.flush()
        private_test = target_test.model_copy(update={"target_memory_context": retrieval.context})
        private_test, identity_metadata = self._identity_evidence(private_test, audit)
        return private_test, retrieval, identity_metadata

    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        private_test, retrieval, identity_metadata = self.prepare_answer(test, audit)
        response = HttpTargetAIConnector().execute(private_test, audit)
        response.execution_metadata.identity_analysis = identity_metadata
        receipt = response.execution_metadata.memory_input
        if receipt is not None:
            # Preserve the same first occurrence and whitespace normalisation
            # as the final provider instruction, including Weak's last trim.
            if audit.memory_strategy == MemoryStrategy.RELATIONSHIP_PACKET:
                # One delivered packet contains all these private record IDs.
                receipt.sent_memory_ids = list(retrieval.evidence.selected_memory_ids)
            else:
                by_value = {}
                for value, memory_id in zip(retrieval.context, retrieval.evidence.selected_memory_ids, strict=True):
                    by_value.setdefault(value.strip(), memory_id)
                receipt.sent_memory_ids = [by_value[value] for value in selected_memory_context(private_test, audit.target_configuration)]
        if audit.target_memory_profile.answer_validation != "off":
            response = self._validate_answer(private_test, audit, response, retrieval)
        return response

    @staticmethod
    def _answer_digest(value) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()

    def _answer_source_roles(self, selected_ids: list[str]) -> list[str]:
        """Bind roles to original authorised messages, never to stored text claims."""
        roles_by_source: dict[str, list[str]] = {}
        for message in self._conversation.messages:
            roles_by_source.setdefault(message.message_id, []).append(message.role.strip().lower())
        result = []
        for memory_id in selected_ids:
            record = self.db.get(TargetAgentMemoryModel, memory_id)
            role = "unknown"
            if (record is not None and record.run_id == self.audit.run_id
                    and record.source_conversation_id == self._conversation.conversation_id
                    and record.source_message_ids):
                values = [roles_by_source.get(source_id, []) for source_id in record.source_message_ids]
                if all(len(value) == 1 and value[0] in {"user", "assistant"} for value in values):
                    distinct = {value[0] for value in values}
                    if len(distinct) == 1:
                        role = next(iter(distinct))
            result.append(role)
        return result

    def _validate_answer(self, test: TestCase, audit: AuditRun, response: TargetResponse, retrieval) -> TargetResponse:
        """One fixed draft, then one separately metered review; never a quality retry."""
        from app.memory_agent.answer_validation import TargetAnswerValidator

        visible = selected_memory_context(test, audit.target_configuration)
        by_value = {}
        for value, memory_id in zip(retrieval.context, retrieval.evidence.selected_memory_ids, strict=True):
            by_value.setdefault(value.strip(), memory_id)
        selected_ids = [by_value[value] for value in visible]
        roles = self._answer_source_roles(selected_ids)
        question = target_question_input(test.prompt)
        refs = {"test_id": test.test_id, "selected_memory_ids": selected_ids, "source_roles": roles,
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "source_context_sha256": self._answer_digest(visible),
                "source_roles_sha256": self._answer_digest(roles),
                "draft_answer_sha256": hashlib.sha256(response.response_text.encode("utf-8")).hexdigest()}
        primary = response.execution_metadata.model_dump(mode="json", exclude_none=True)
        primary.update(provider=audit.provider.value, model=audit.model,
                       elapsed_ms=response.execution_metadata.latency_ms)
        # This ledger entry mirrors the already completed target HTTP call. It is
        # not another provider execution and must not be counted a second time.
        draft_stage = record_agent_execution(
            self.db, role="target_answer_draft", provider=audit.provider.value, model=audit.model,
            prompt_template_version="target-answer-draft-ledger-v1", instructions="", prompt="", schema=None,
            input_payload=refs, input_refs={**refs, "execution_origin": "copy_of_primary_target_answer"},
            output_data={"execution_origin": "copy_of_primary_target_answer",
                         "response": response.model_dump(mode="json")}, status="completed", execution=primary,
            conversation_id=audit.conversation_id, run_id=audit.run_id,
            handoff_from="target_answering", handoff_to="target_answer_validation")
        refs["draft_execution_id"] = draft_stage.id
        validator = TargetAnswerValidator(audit.provider.value, audit.model)
        try:
            receipt = response.execution_metadata.memory_input
            if (receipt is None or receipt.context_sha256 != refs["source_context_sha256"]
                    or receipt.prompt_sha256 != refs["question_sha256"]
                    or receipt.sent_memory_ids != selected_ids):
                raise HTTPException(502, "The primary draft input binding is missing or inconsistent.")
            result = validator.validate(
                question=question, context=visible, draft_answer=response.response_text,
                max_output_tokens=audit.target_memory_profile.answer_validation_output_token_limit,
                context_character_budget=audit.target_memory_profile.context_character_budget,
                reasoning_effort=audit.target_memory_profile.answer_validation_reasoning_effort,
                source_roles=roles)
        except Exception as exc:
            stage = self._record_answer_validation(validator, refs, audit)
            failure = HTTPException(502, "The required target answer validation failed.")
            failure.target_execution = self._answer_validation_failure(response, audit, test, draft_stage, stage)
            raise failure from exc
        stage = self._record_answer_validation(validator, refs, audit)
        if stage is None or stage.status != "completed":
            failure = HTTPException(502, "The required target answer validation observation is missing.")
            failure.target_execution = self._answer_validation_failure(response, audit, test, draft_stage, stage)
            raise failure
        response.execution_metadata.answer_validation = {
            **result.public_metadata(), "draft_execution_id": draft_stage.id, "execution_id": stage.id,
            "execution": self._answer_validation_meter(validator.last_execution),
            "final_text_source": {"supported": "original_draft", "corrected": "validator_corrected",
                                  "uncertain": "fixed_abstention"}[result.decision],
            "primary_execution_scope": "original_draft_only; draft ledger mirrors this call, do not double count",
            "budget_note": "One additional target-owned review, metered separately from the primary draft."}
        response.response_text = result.final_answer
        return response

    @staticmethod
    def _answer_validation_meter(execution: dict | None) -> dict:
        from app.schemas.request_contracts import wire_metadata
        receipt = execution or {}
        fields = ("version", "provider", "model", "reported_model", "agent_role", "prompt_template_version",
                  "status", "request_attempts", "failed_http_attempts", "elapsed_ms", "last_http_status",
                  "response_choice_count", "reported_finish_reason", "completion_status", "finish_reason",
                  "requested_output_token_limit", "declared_output_token_limit", "configured_output_token_cap",
                  "requested_reasoning_effort", "prompt_fingerprint", "input_fingerprint", "output_fingerprint",
                  "reported_input_tokens", "reported_output_tokens", "reported_total_tokens", "reported_reasoning_tokens",
                  "input_tokens", "output_tokens", "total_tokens", "reasoning_tokens")
        return {**{key: copy.deepcopy(receipt[key]) for key in fields if key in receipt
                   and (receipt[key] is None or type(receipt[key]) in {str, int, float, bool})}, **wire_metadata(receipt)}

    def _answer_validation_failure(self, response, audit, test, draft_stage, stage):
        primary = response.execution_metadata.model_dump(mode="json", exclude_none=True)
        meter = self._answer_validation_meter(primary)
        return {**meter, "version": "target-answer-validation-failure-v1", "provider": audit.provider.value,
                "model": audit.model, "test_id": test.test_id,
                "execution_origin": "copy_of_primary_target_answer", "primary_status": "completed",
                "status": "failed", "failure_stage": "target_answer_validation",
                "error_code": "TargetAnswerValidationFailed",
                "error_summary": "The primary draft completed but its required source review was not accepted.",
                "draft_execution_id": draft_stage.id,
                "answer_validation": {"status": "failed", "draft_execution_id": draft_stage.id,
                    "execution_id": stage.id if stage else None,
                    "execution": self._answer_validation_meter(
                        self.last_answer_validation_observation.get("execution")
                        if self.last_answer_validation_observation else None)}}

    def _record_answer_validation(self, validator, refs: dict, audit: AuditRun):
        observation = validator.last_observation
        self.last_answer_validation_observation = copy.deepcopy(observation)
        if not observation:
            return record_agent_execution(
                self.db, role=validator.ROLE, provider=audit.provider.value, model=audit.model,
                prompt_template_version=validator.VERSION, instructions="", prompt="", schema=None,
                input_payload=refs, input_refs=refs, output_data={"result": None, "raw_model_review": None},
                status="failed", execution=None, error_code="missing_validation_observation",
                error_summary="The required review did not produce an observation; no successful review is claimed.",
                conversation_id=audit.conversation_id, run_id=audit.run_id,
                handoff_from="target_answer_draft", handoff_to="target_answering")
        # Full source/question/draft input remains in the private harness sidecar.
        # The ordinary ledger stores input fingerprints and explicit references.
        return record_agent_execution(
            self.db, role=validator.ROLE, provider=audit.provider.value, model=audit.model,
            prompt_template_version=validator.VERSION, instructions=observation["instructions"],
            prompt=observation["prompt"], schema=observation["schema"],
            input_payload=observation["input_payload"], input_refs=refs,
            output_data={"result": observation.get("output_data"),
                         "raw_model_review": observation.get("raw_model_review")},
            status=observation["status"], execution=observation.get("execution"),
            error_code=observation.get("error_code"), error_summary=observation.get("error_summary"),
            conversation_id=audit.conversation_id, run_id=audit.run_id,
            handoff_from="target_answer_draft", handoff_to="target_answering")

    def _identity_evidence(self, test: TestCase, audit: AuditRun) -> tuple[TestCase, dict | None]:
        """Propose links from the same selected evidence, with separate metering."""
        # Runtime-only advisory fields never survive from another condition.
        test = test.model_copy(update={"target_identity_evidence": None,
                                       "target_identity_failure_receipt": None})
        if audit.target_memory_profile.identity_analysis == "off":
            return test, None
        visible = selected_memory_context(test, audit.target_configuration)
        if not identity_analysis_applicable(
                question=test.prompt, selected_record_count=len(visible),
                configuration=audit.target_configuration.value,
                identity_analysis=audit.target_memory_profile.identity_analysis):
            return test, {"status": "skipped_not_applicable", "request_attempts": 0,
                          "reason": "The selected condition/question does not request multi-record identity analysis."}
        if audit.provider.value == "rule_based":
            raise HTTPException(422, "Identity evidence analysis requires a configured model target.")
        from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
        analyzer = TargetIdentityEvidenceAnalyzer(audit.provider.value, audit.model)
        try:
            result = analyzer.analyze(
                question=test.prompt, context=visible,
                max_output_tokens=audit.target_memory_profile.identity_analysis_output_token_limit,
                context_character_budget=audit.target_memory_profile.context_character_budget,
                **({'reasoning_effort': audit.target_memory_profile.identity_analysis_reasoning_effort}
                   if audit.target_memory_profile.identity_analysis_reasoning_effort is not None else {}),
            )
        except Exception:
            stage = self._record_identity_stage(analyzer.last_observation, test, audit)
            if audit.target_memory_profile.identity_analysis_failure_policy == "continue_without_advisory":
                from app.memory_agent.identity_failure import (
                    build_identity_failure_receipt, identity_failure_receipt_sha256,
                    recorded_identity_failure_matches,
                )
                from app.services.agent_trace import agent_execution_schema
                failure = build_identity_failure_receipt(
                    observation=analyzer.last_observation, question=test.prompt, context=visible,
                    provider=audit.provider.value, model=audit.model,
                    max_output_tokens=audit.target_memory_profile.identity_analysis_output_token_limit,
                    reasoning_effort=audit.target_memory_profile.identity_analysis_reasoning_effort,
                )
                if (failure is not None and stage is not None
                        and recorded_identity_failure_matches(failure, agent_execution_schema(stage))):
                    digest = identity_failure_receipt_sha256(failure)
                    metadata = {
                        "version": analyzer.VERSION, "status": "degraded_without_advisory",
                        "advisory_applied": False, "execution_id": stage.id,
                        "execution": analyzer.last_execution, "failure_receipt": failure,
                        "failure_receipt_sha256": digest,
                        "budget_note": "Failed auxiliary analysis retained; no retry or model change. Final answer uses the original selected memories.",
                    }
                    return test.model_copy(update={"target_identity_failure_receipt": failure}), metadata
            raise
        stage = self._record_identity_stage(analyzer.last_observation, test, audit)
        metadata = {
            "version": analyzer.VERSION, "status": result.status,
            "execution_id": stage.id if stage is not None else None,
            "selected_context_sha256": result.source_context_sha256,
            "validation_scope": result.validation_scope,
            "quote_count": len(result.quotes), "relation_count": len(result.relations),
            "advisory": result.to_advisory(),
            "execution": analyzer.last_execution,
            "budget_note": "Additional target-owned analysis; metered separately from the final answer.",
        }
        return test.model_copy(update={"target_identity_evidence": result.to_advisory()}), metadata

    def _record_identity_stage(self, observation: dict | None, test: TestCase, audit: AuditRun):
        if not observation:
            return None
        return record_agent_execution(
            self.db, role=observation["role"], provider=observation["provider"], model=observation["model"],
            prompt_template_version=observation["prompt_template_version"],
            instructions=observation["instructions"], prompt=observation["prompt"], schema=observation["schema"],
            input_payload=observation["input_payload"],
            input_refs={**observation["input_refs"], "test_id": test.test_id},
            output_data=observation["output_data"], status=observation["status"],
            execution=observation["execution"], error_code=observation["error_code"],
            error_summary=observation["error_summary"],
            error_diagnostics=observation.get("error_diagnostics"),
            conversation_id=audit.conversation_id, run_id=audit.run_id,
            handoff_from="target_memory_selection", handoff_to="target_answering",
        )

    def trace(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.version,
            "run_id": self.audit.run_id,
            "last_retrieval_id": self._last_retrieval_id,
        }

    def reset(self) -> None:
        # Run-scoped persistence is intentional.  The database lifecycle owns
        # deletion; this method simply drops the in-process session reference.
        self.last_answer_validation_observation = None
        self._conversation = None
        self._last_retrieval_id = None
        self._diagnostic_packet_id = None
