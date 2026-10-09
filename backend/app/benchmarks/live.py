"""Real-model benchmark runs using the ordinary controlled memory boundary.

Each condition/case gets a separate transient database; the operational audit
database and imported benchmark reference annotations never enter this target.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4
from threading import Event

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.session import Base
from app.models import AuditRunModel, ConversationModel, TestCaseModel, TargetAgentMemoryModel, TargetAgentRetrievalModel
from app.schemas.domain import AuditRun, Conversation, ConversationMessage, Dimension, TestCase, TargetProvider, TargetConfiguration
from app.schemas.benchmark import LiveBenchmarkRequest, LiveBenchmarkResponse, LiveBenchmarkCondition, LiveBenchmarkCaseResult
from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.target_systems.controlled import ControlledTargetSystemAdapter


class LiveBenchmarkRunner:
    VERSION = "shared-reader-live-benchmark-v4"

    def run(self, request: LiveBenchmarkRequest, cancelled: Event | None = None) -> LiveBenchmarkResponse:
        if not request.source_authorised:
            raise ValueError("Confirm that you are authorised to process this benchmark source.")
        if request.provider not in {TargetProvider.OLLAMA, TargetProvider.OPENROUTER}:
            raise ValueError("Real-model benchmark execution supports Ollama or OpenRouter; use the separate rule baseline for simulation.")
        if len(set(request.strategies)) != len(request.strategies):
            raise ValueError("Choose each memory strategy only once.")
        cases, report = LongMemEvalAdapter().adapt(request.payload)
        if len(cases) > request.max_cases:
            raise ValueError(f"The file has {len(cases)} cases; limit it to {request.max_cases} before live execution. No cases were silently dropped.")
        if sum(len(m.content) for c in cases for m in c.messages) > 1_000_000:
            raise ValueError("Live benchmark history exceeds the 1 MB source-text limit.")
        if request.native_repair_comparison and not request.include_mem0:
            raise ValueError("Enable native Mem0 before selecting its repair comparison.")
        if request.native_repair_comparison:
            from app.benchmarks.mem0 import GENERIC_INSTRUCTION
            if len((request.target_memory_profile.additional_instructions+'\n'+GENERIC_INSTRUCTION).strip())>4000:
                raise ValueError('Leave room for the frozen generic instruction within the 4,000 character instruction limit.')
        if request.native_repair_comparison and len(request.strategies)>1:
            raise ValueError("Choose one controlled reference alongside the three native repair conditions.")
        if request.include_mem0:
            from app.benchmarks.mem0 import endpoint
            if not endpoint():
                raise ValueError("Configure the local native Mem0 target before this comparison.")
            if request.provider != TargetProvider.OLLAMA or request.model != 'qwen3:1.7b':
                raise ValueError("The current native Mem0 pilot requires local qwen3:1.7b for every condition.")
            if len(request.strategies) > 3:
                raise ValueError("Select at most three controlled strategies alongside native Mem0.")
            if request.target_memory_profile.isolate_project_scope or request.target_memory_profile.prefer_current_state:
                raise ValueError("Native Mem0 cannot implement these custom retrieval filters; disable them for a native comparison.")
            if any(len(c.messages)>40 or sum(len(m.content) for m in c.messages)>24000 for c in cases):
                raise ValueError("Each native Mem0 pilot history must contain at most 40 messages and 24,000 characters.")
        source_hash = LongMemEvalDeterministicRunner._fingerprint(request.payload)
        configuration = request.model_dump(mode="json", exclude={"payload", "source_authorised", "source_label"})
        conditions = []
        writer_version = ""
        for strategy in request.strategies:
            results = []
            for case in cases:
                if cancelled is not None and cancelled.is_set():
                    raise ValueError("The live benchmark connection was cancelled; no further case was started.")
                # Never use global engine/SessionLocal, even when called via API.
                engine = create_engine("sqlite://")
                try:
                    Base.metadata.create_all(engine)
                    with Session(engine) as db:
                        now = datetime.now(timezone.utc)
                        cid, rid = "BC" + uuid4().hex[:20], "BR" + uuid4().hex[:20]
                        audit = AuditRun(run_id=rid, conversation_id=cid, status="CREATED",
                            # Keep the reader instruction fixed. Weak retrieval
                            # is already implemented by the store's policy.
                            target_configuration=TargetConfiguration.STRONG,
                            provider=request.provider, model=request.model, temperature=request.temperature,
                            random_seed=request.random_seed, test_budget=1, prompt_template_version=self.VERSION,
                            memory_strategy=strategy, target_memory_capacity=request.target_memory_capacity,
                            target_memory_profile=request.target_memory_profile, created_at=now)
                        db.add(ConversationModel(id=cid, authorised=True, created_at=now))
                        db.flush()
                        db.add(AuditRunModel(id=rid, conversation_id=cid, target_configuration=audit.target_configuration.value,
                            provider=audit.provider.value, model=audit.model, temperature=audit.temperature,
                            random_seed=audit.random_seed, test_budget=1, prompt_template_version=self.VERSION,
                            memory_strategy=strategy.value, target_memory_capacity=request.target_memory_capacity))
                        db.flush()
                        conversation = Conversation(conversation_id=cid, created_at=now, authorised=True,
                            messages=[ConversationMessage(message_id=m.message_id, role=m.role, content=m.content, timestamp=m.timestamp) for m in case.messages])
                        target = ControlledTargetSystemAdapter(db, audit)
                        writer_version = target.store.writer_version
                        target.ingest(conversation)
                        # Question date is available source chronology, not gold.
                        prompt = case.question + (f"\nQuestion date: {case.question_timestamp.isoformat()}" if case.question_timestamp else "")
                        private_test = TestCase(test_id="BT" + uuid4().hex[:20], run_id=rid,
                            # Benchmark type/dimension annotations must not
                            # influence retrieval. Classify from the query only.
                            dimension=Dimension.CONFLICT_RESOLUTION if re.search(r"\b(?:conflict|contradict|disagree)\w*\b", case.question, re.I) else Dimension.ACCURACY,
                            prompt=prompt, expected_behavior="", supporting_memory_ids=[], generator_version=self.VERSION)
                        db.add(TestCaseModel(id=private_test.test_id, run_id=rid, dimension=private_test.dimension.value,
                            prompt=prompt, expected_behavior="", supporting_memory_ids=[], generator_version=self.VERSION))
                        db.flush()
                        response = target.answer(private_test, audit)
                        retrieval = db.scalar(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id == rid))
                        records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == rid)).all()
                        receipt = response.execution_metadata.memory_input
                        results.append(LiveBenchmarkCaseResult(case_id=case.case_id, category=case.category,
                            question=case.question, expected_answer=case.expected_answer, response_text=response.response_text,
                            lexical_match=self._lexical_match(case.expected_answer, response.response_text),
                            token_f1=LongMemEvalDeterministicRunner._token_f1(case.expected_answer, response.response_text),
                            execution_metadata=response.execution_metadata, retrieved_memory_ids=list(retrieval.selected_memory_ids),
                            supplied_memory_ids=(receipt.sent_memory_ids or []) if receipt else [], stored_memory_count=len(records),
                            memory_evidence=[{"memory_id":r.id, "canonical_value":r.canonical_value, "lifecycle_state":r.lifecycle_state,
                                "scope":r.scope, "source_message_ids":r.source_message_ids,
                                "retrieved":r.id in retrieval.selected_memory_ids,
                                "supplied":r.id in (receipt.sent_memory_ids or []) if receipt else False} for r in records],
                            ranking_evidence=retrieval.ranking_evidence,
                            retained_memory_count=sum(r.lifecycle_state not in {"EVICTED", "SUPERSEDED"} for r in records),
                            message_count=len(case.messages), assistant_message_count=sum(m.role == "assistant" for m in case.messages)))
                finally:
                    engine.dispose()
            matches = sum(r.lexical_match for r in results)
            conditions.append(LiveBenchmarkCondition(strategy=strategy, cases=results, lexical_matches=matches,
                total=len(results), percentage=round(100 * matches / len(results), 2)))
        if request.include_mem0:
            from app.benchmarks.mem0 import run_case, run_case_comparison, REPAIR_VERSION, GENERIC_INSTRUCTION
            if request.native_repair_comparison:
                paired = [run_case_comparison(request,case,cancelled,self.VERSION) for case in cases]
                native_conditions = {name:[r[name] for r in paired] for name in ('baseline','generic','directed')}
                configuration['native_interventions'] = {'policy_version':REPAIR_VERSION,'generic_instruction':GENERIC_INSTRUCTION}
            else:
                native_conditions = {'baseline':[run_case(request,case,cancelled,self.VERSION) for case in cases]}
            for name, native_results in native_conditions.items():
                matches=sum(r.lexical_match for r in native_results)
                conditions.append(LiveBenchmarkCondition(strategy='mem0_native' if name=='baseline' else 'mem0_'+name,
                    cases=native_results,lexical_matches=matches,total=len(native_results),percentage=round(100*matches/len(native_results),2)))
            configuration['native_mem0_versions']=[{k:r.memory_preparation.get(k) for k in ('sdk_version','target_service')} for r in native_conditions['baseline']]
        configuration.update({"reader_configuration":"strong", "runner_version":self.VERSION,
            "adapter_version":report.adapter_version, "target_adapter_version":ControlledTargetSystemAdapter.version,
            "writer_version":writer_version})
        config_hash = sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return LiveBenchmarkResponse(run_id="LB" + uuid4().hex[:20], source_fingerprint_sha256=source_hash,
            configuration_fingerprint_sha256=config_hash, runner_version=self.VERSION, adapter_version=report.adapter_version,
            target_adapter_version=ControlledTargetSystemAdapter.version, writer_version=writer_version,
            provider=request.provider, model=request.model, temperature=request.temperature,
            seed_control="Recorded for provenance; provider seed is not sent and deterministic generation is not guaranteed.",
            target_memory_capacity=request.target_memory_capacity, target_memory_profile=request.target_memory_profile,
            conditions=conditions,
            notice=("Native Mem0, when selected, uses the same answer connector/instructions and reader budget. Its native extraction and embedding costs are additional and not counted in reader requests; source timestamps and per-fact attribution are unsupported. Native retention is not constrained by the controlled-store capacity. Native repair variants share one extraction/retrieval snapshot; generic adds a careful-answer instruction, directed filters separable task facts, without changing model weights. " if request.include_mem0 else "") + "Actual model calls using the ordinary controlled rule-based memory writer and retrieval policies. The writer extracts user facts; assistant-only evidence may not be retained. Capacity and context limits apply. Every case is isolated; no benchmark history is saved in the audit database. Lexical matches and token F1 are exploratory proxies, not official LongMemEval scores or calibrated semantic judgments. Download hypotheses for the upstream evaluator and independently review answers. Full reference answers, evidence-session IDs and has_answer labels are excluded from model inputs.")

    @staticmethod
    def _lexical_match(expected: str, response: str) -> bool:
        anchor = re.split(r"\b(?:because|although|however)\b", expected, maxsplit=1, flags=re.I)[0]
        def normalize(value: str) -> str:
            return " ".join(re.findall(r"\w+", value.lower()))
        gold, answer = normalize(anchor), normalize(response)
        return bool(gold) and f" {gold} " in f" {answer} "
