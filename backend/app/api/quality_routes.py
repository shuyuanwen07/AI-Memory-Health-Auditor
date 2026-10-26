"""Auditor reliability, exploratory diagnosis and controlled repair workflows."""
import os
import hashlib
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models import AuditRunModel, ConversationModel, ExperimentModel, TestCaseModel, MemoryModel, MemoryRelationshipModel, MessageModel, AgentExecutionModel
from app.schemas import (AuditCreate, AuditStatus, Dimension, TestSuiteConfiguration, TestSuiteMode, TestCase,
                         TestQualityStatus, HumanValidityStatus, GroundingStatus, MethodComparisonInventoryImport,
                         MethodComparisonDiscoveryMappingImport)
from app.schemas.target_profile import RepairExperimentRequest, TargetMemoryProfile, FollowUpRequest
from app.api.routes import (audit_schema, build_audit, evaluation_review_items_for, evaluation_review_batches_for, target_memory_trace_payload,
                            ident, memory_schema, persist_generated_tests, public_test_schema)
from app.services.auditor_quality import reliability_summary, paired_probe_summary, scenario_reliability, apply_evidence_integrity
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.services.evidence_correspondence import correspondence, evidence_units
from app.services.memory_availability import availability
from app.services.repair_recommendation import recommend_repair
from app.services.input_delivery import input_delivery
from app.services.reviewer_identity import distinct_reviewers
from app.extraction.llm import PipelineLLMClient
from app.services.agent_trace import record_agent_execution
from app.diagnostics.post_run_agent import PostRunDiagnosticAgent
from app.test_generator.baselines import FixedTemplateTestGenerator

quality_router = APIRouter(prefix="/api/v1")


def completed(run_id: str, db: Session) -> AuditRunModel:
    run = db.get(AuditRunModel, run_id)
    if not run:
        raise HTTPException(404, "Audit was not found.")
    if run.status != AuditStatus.COMPLETED.value:
        raise HTTPException(409, "Complete the source audit before diagnosis or validation.")
    return run


@quality_router.get("/target-systems")
def target_systems():
    return [{"value": "controlled-memory", "label": "Configurable memory system", "configured": True, "observability": "memory_trace"},
            {"value": "external-http", "label": "Independent target service", "configured": bool(os.getenv("EXTERNAL_TARGET_URL", "").strip()), "observability": "black_box"}]


@quality_router.get("/auditor-quality")
def quality_overview(db: Session = Depends(get_db)):
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.status == "COMPLETED").order_by(AuditRunModel.created_at.desc(), AuditRunModel.id)).all()
    integrity = {}
    batches = evaluation_review_batches_for([run.id for run in runs], db, integrity)
    items = [item for run in runs for item in batches[run.id]]
    report = apply_evidence_integrity(reliability_summary(items), list(integrity.values()))
    method_batches = {}
    method_names = {"rules": "Rule tests + rule review", "model_generation": "Model tests + rule review", "hybrid": "Model tests + hybrid review"}
    for run in runs:
        # Only explicitly declared experiment conditions have method identity.
        # Historical/custom settings must not silently become rule baselines.
        method = (run.reproducibility_metadata or {}).get("auditor_method") or "custom"
        if method not in method_names:
            method = "custom"
        bucket = method_batches.setdefault(method, {"runs": [], "items": []})
        bucket["runs"].append(run)
        bucket["items"].extend(batches[run.id])
    report["by_method"] = [dict(method=method, label=method_names.get(method, "Other audit configurations"),
        completed_runs=len(bucket["runs"]), scenario_count=len({run.conversation_id for run in bucket["runs"]}),
        run_ids=[run.id for run in bucket["runs"]], **apply_evidence_integrity(reliability_summary(bucket["items"]), [integrity[run.id] for run in bucket["runs"]]))
        for method, bucket in sorted(method_batches.items(), key=lambda row: ["rules", "model_generation", "hybrid", "custom"].index(row[0]))]
    history_groups = {}
    for run in runs:
        history_groups.setdefault(run.conversation_id, []).extend(batches[run.id])
    report["scenario_analysis"] = scenario_reliability(history_groups)
    for method_report in report["by_method"]:
        method_histories = {}
        for run in method_batches[method_report["method"]]["runs"]:
            method_histories.setdefault(run.conversation_id, []).extend(batches[run.id])
        method_report["scenario_analysis"] = scenario_reliability(method_histories)
        differences = [item for item in method_batches[method_report["method"]]["items"]
            if item.human_review is not None and item.automated.passed != item.human_review.human_passed]
        method_report["reviewed_difference_count"] = len(differences)
        method_report["reviewed_examples"] = [{"run_id": item.response.run_id,
            "question": item.test.prompt, "answer": item.response.response_text,
            "automated_passed": item.automated.passed, "human_passed": item.human_review.human_passed,
            "assessment_reason": item.automated.reason, "review_note": item.human_review.note,
            "review_role": item.human_review.review_role.value,
            "kind": "uncertain" if item.automated.passed is None else "false_alarm" if item.automated.passed is False else "missed_failure"}
            for item in differences[:20]]
    report["method_comparison_notice"] = "These are descriptive groups across stored audits. Different histories, targets and strategies are not a controlled method comparison. Use the shared-answer experiment for paired claims."
    report["completed_runs"] = len(runs)
    report["scenario_count"] = len({run.conversation_id for run in runs})
    report["review_queue"] = [{"run_id": run.id, "model": run.model,
                                "created_at": run.created_at.isoformat(),
                                "unreviewed": sum(item.human_review is None for item in batches[run.id])}
                               for run in runs]
    for queue in report["review_queue"]:
        items_for_run = batches[queue["run_id"]]
        queue["independent_pending"] = sum(len(distinct_reviewers([review for review in item.human_reviews
            if review.review_role.value == "independent"])) < 2 for item in items_for_run)
        queue["adjudication_pending"] = sum(len(distinct_reviewers([review for review in item.human_reviews
            if review.review_role.value == "independent"])) >= 2 and
            (item.human_review is None or item.human_review.review_role.value != "adjudication") for item in items_for_run)
    report["review_queue"] = [queue for queue in report["review_queue"] if
        queue["unreviewed"] or queue["independent_pending"] or queue["adjudication_pending"]]
    return report


@quality_router.get("/audits/{run_id}/blind-review")
def blind_review(run_id: str, db: Session = Depends(get_db)):
    # Actual server-side withholding: no automated verdict, model, configuration,
    # judge reason or another reviewer's labels are returned.
    items = evaluation_review_items_for(run_id, db)
    run = db.get(AuditRunModel, run_id)
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == run.conversation_id).order_by(MessageModel.sequence)).all()
    return [{"test": {"test_id": item.test.test_id, "prompt": item.test.prompt,
                       "expected_behavior": item.test.expected_behavior},
             "response": {"response_text": item.response.response_text},
             "automated": {"evaluation_id": item.automated.evaluation_id},
             "source_statements": [{"role": message.role, "content": message.content, "timestamp": message.observation_timestamp.isoformat()} for message in messages],
             "human_reviews": [], "human_review": None}
            for item in items]


@quality_router.get("/audits/{run_id}/blind-review-pack")
def blind_review_pack(run_id: str, db: Session = Depends(get_db)):
    """Portable complete blank pack; no verdict-based selection or identity leakage."""
    rows = blind_review(run_id, db)
    content = {
        "format": "memory-auditor-blind-review-v1",
        "notice": "Generated references are proposals. Check the complete source independently. This is an unlabelled packet, not human validation. Submit final labels through independent blind review; do not import this file as a gold release.",
        "source_statements": rows[0]["source_statements"] if rows else [],
        "items": [{"item_id": f"Response {index + 1}",
                   "question": row["test"]["prompt"],
                   "proposed_reference_behavior": row["test"]["expected_behavior"],
                   "response": row["response"]["response_text"],
                   "human_passed": None, "human_failure_type": None,
                   "corrected_reference_behavior": None, "decision_note": None}
                  for index, row in enumerate(rows)],
        "reviewer_pseudonym": None, "completed_independently_by_human": False,
    }
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")).encode()).hexdigest()
    return {**content, "packet_sha256": fingerprint}


@quality_router.get("/audits/{run_id}/diagnosis")
def diagnosis(run_id: str, db: Session = Depends(get_db)):
    run = completed(run_id, db)
    items = evaluation_review_items_for(run_id, db)
    trace = target_memory_trace_payload(run, db)
    records = {record.memory_id: record for record in trace.records}
    stored_sources = {source for record in trace.records for source in record.source_message_ids}
    memory_rows = {memory.id: memory_schema(db, memory) for memory in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == run.conversation_id)).all()}
    authorised_sources = set(db.scalars(select(MessageModel.source_message_id).where(MessageModel.conversation_id == run.conversation_id)).all())
    retrievals = {retrieval.test_id: retrieval for retrieval in trace.retrievals if retrieval.final_response_id}
    by_response = {retrieval.final_response_id: retrieval for retrieval in trace.retrievals if retrieval.final_response_id}
    if trace.shared_answer_source_run_id:
        retrievals = {item.test.test_id: by_response.get((item.response.execution_metadata.shared_source_response_id
                      if item.response.execution_metadata else None)) for item in items}
    cases = []
    for item in items:
        expected_sources = {source for key in item.test.supporting_memory_ids if key in memory_rows for source in memory_rows[key].source_message_ids}
        retrieval = retrievals.get(item.test.test_id)
        receipt = retrieval.memory_input if retrieval else None
        sent_ids = receipt.sent_memory_ids if receipt else None
        sent_sources = {source for key in sent_ids or [] if key in records for source in records[key].source_message_ids}
        reference = [memory_rows[key] for key in item.test.supporting_memory_ids if key in memory_rows]
        missing_references = sorted(set(item.test.supporting_memory_ids) - memory_rows.keys())
        invalid_references = sorted(memory.memory_id for memory in reference if
            not memory.canonical_value.strip() or not memory.source_message_ids or
            not set(memory.source_message_ids).issubset(authorised_sources))
        provenance = {"complete": bool(item.test.supporting_memory_ids) and not missing_references and not invalid_references,
                      "missing_reference_count": len(missing_references), "invalid_reference_count": len(invalid_references)}
        facts = correspondence(reference,
            list(records.values()), [records[key] for key in sent_ids if key in records] if sent_ids is not None else None)
        available = availability(reference, list(records.values()), retrieval.ranking_evidence if retrieval else [],
                                 [records[key] for key in sent_ids if key in records] if sent_ids is not None else None)
        delivery = input_delivery(reference, list(records.values()), retrieval.selected_memory_ids if retrieval else None,
                                  sent_ids, retrieval.ranking_evidence if retrieval else [])
        supplied_units = set().union(*(evidence_units(records[key]) for key in sent_ids or [] if key in records))
        reference_units = set().union(*(evidence_units(fact) for fact in reference))
        replaced_units = set().union(*(evidence_units(memory_rows[relation.target_memory_id])
            for fact in reference if evidence_units(fact) and evidence_units(fact).issubset(supplied_units)
            for relation in fact.relationships if relation.type.value == 'UPDATE'
            and relation.target_memory_id in item.test.supporting_memory_ids
            and relation.target_memory_id in memory_rows))
        supplied_update_covers_missing = bool(reference_units - supplied_units) and (
            reference_units - supplied_units).issubset(replaced_units)
        if item.automated.passed is True:
            if not provenance['complete']:
                layer, explanation = "unobserved_pass", "The answer passed, but supporting reference facts or their authorised source links are incomplete. Restore and review reference provenance before attributing memory use. This is not a detected model failure."
            elif facts['complete_supplied_match']:
                continue
            elif sent_ids is None:
                layer, explanation = "unobserved_pass", "The answer passed but actual supplied records are unobserved. This cannot establish memory use."
            else:
                layer, explanation = "unattributed_pass", "The answer passed, but exact source-and-fact correspondence is incomplete. Reworded or bundled facts may still support it; prior knowledge or a guess is also possible. Review fact text and a memory-removal control before attributing memory use. This is not a detected failure."
        elif item.automated.passed is None:
            layer, explanation = "uncertain_assessment", "The evaluator has no reliable verdict; resolve assessment before attributing a memory defect."
        elif not provenance['complete']:
            layer, explanation = "unobserved", "A behavioural failure was detected, but supporting reference facts or their authorised source links are incomplete. Restore and review reference provenance before attributing an internal memory defect."
        elif run.target_system_adapter != "controlled-memory" or sent_ids is None:
            layer, explanation = "unobserved", "A behavioural failure was detected, but available evidence cannot establish its internal cause."
        elif run.memory_strategy == "no_memory" and not sent_ids:
            layer, explanation = "no_memory_reference", "Memory was intentionally disabled for this reference condition, and the recorded final input contains zero memory records. The failed answer is an observed baseline outcome, not evidence of a broken retrieval mechanism. Enabling memory would create a different experimental condition; review stored facts separately before any internal-cause claim."
        elif not expected_sources.issubset(stored_sources):
            layer, explanation = "encoding_hypothesis", "Some supporting source messages were not represented in the stored-memory trace. Verify fact-level extraction before intervention."
        elif not facts['complete_stored_match']:
            layer, explanation = "fact_correspondence_review", "The source messages are represented, but their recorded fact text does not exactly match all supporting facts. Compare old values, paraphrases and bundled facts before attributing extraction or generation failure. Text differences alone do not establish a defect."
        elif delivery['selected_not_supplied_fact_units']:
            layer, explanation = "input_delivery_review", "Some exact supporting facts were selected by retrieval but absent from the final input receipt. Inspect reader trimming, deduplication and input assembly before changing retrieval. Other supporting facts may also be missing at earlier stages; source-and-text matching alone does not prove the sole cause."
        elif not facts['complete_supplied_match'] and available['capacity_excluded_fact_units']:
            layer, explanation = "retention_hypothesis", "At least one exact supporting source-and-fact pair was recorded but excluded by capacity at answer time, with no observed eligible exact copy. Inspect retention and capacity before retrieval tuning; paraphrases and alternative evidence still require review. This observation does not establish the sole cause of the failed answer."
        elif delivery['context_budget_excluded_fact_units']:
            layer, explanation = "context_budget_review", "Some exact supporting facts were excluded by the recorded context budget before final selection. Inspect the retrieved-record limit and character budget before changing retrieval strategy. The recorded reason does not distinguish which limit bound; alternative evidence and other missing facts still require review."
        elif delivery['profile_filter_excluded_fact_units']:
            layer, explanation = "profile_filter_review", "Some exact supporting facts were excluded by recorded project or current-state profile filters. Inspect whether those facts were necessary and whether the filter fits the question before changing retrieval strategy; this is not proof that the filter caused the failed answer."
        elif not facts['complete_supplied_match'] and available['observed_fact_units']<available['expected_fact_units']:
            layer, explanation = "availability_review", "Supporting facts were recorded, but answer-time eligibility is incomplete or unknown. Current lifecycle states cannot establish their past availability. Check retention and policy evidence before attributing a retrieval miss."
        elif (facts['supplied_fact_units'] and not facts['complete_supplied_match']
              and supplied_update_covers_missing
              and available['superseded_only_missing_fact_units'] ==
              facts['expected_fact_units'] - facts['supplied_fact_units']):
            layer, explanation = "answer_and_history_review", "The supplied input contains exact supporting facts, while the only missing supporting facts were observed as older states excluded by policy. Check the answer and assessment against the supplied newer fact, then determine whether the question also required the older history. This does not establish that historical exclusion caused the failed answer or that restoring old memories would improve it."
        elif not facts['complete_supplied_match'] and available['other_excluded_fact_units']:
            layer, explanation = "policy_exclusion_hypothesis", "Exact supporting facts were excluded by an observed policy other than capacity. Inspect update and diagnostic-packet exclusions and whether those facts were actually necessary before blaming retrieval or generation."
        elif not expected_sources.issubset(sent_sources):
            layer, explanation = "retrieval_hypothesis", "Supporting source messages exist in the store but were not all represented in the actual memory-input receipt."
        elif not facts['complete_supplied_match']:
            layer, explanation = "fact_supply_review", "Supporting facts have exact matches in the store, but the supplied facts do not all match. Same-message attribution alone cannot confirm the needed value was supplied. Review paraphrases and filtering before causal attribution."
        else:
            layer, explanation = "generation_hypothesis", "Exact supporting source-and-fact pairs were represented in supplied records. Check relevance, contradictions and the assessment before attributing generation failure; presence does not prove model reliance."
        cases.append({"test_id": item.test.test_id, "question": item.test.prompt, "dimension": item.test.dimension.value,
                      "response": item.response.response_text, "assessment": item.automated.reason, "automated_passed": item.automated.passed,
                      "supporting_memory_ids": list(item.test.supporting_memory_ids),
                      "layer": layer, "explanation": explanation, "evidence_status": "hypothesis_not_causal_proof",
                      "supporting_source_count": len(expected_sources), "stored_source_coverage": len(expected_sources & stored_sources),
                      "sent_source_coverage": len(expected_sources & sent_sources) if sent_ids is not None else None})
        cases[-1]['fact_correspondence'] = facts
        cases[-1]['memory_availability'] = available
        cases[-1]['reference_provenance'] = provenance
        cases[-1]['input_delivery'] = delivery
    candidate = recommend_repair(cases, audit_schema(run).target_memory_profile, run.memory_strategy,
                                run.target_memory_capacity, len(records), configurable=run.target_system_adapter=='controlled-memory')
    return {"run_id": run_id, "cases": cases, "paired_probes": paired_probe_summary(items),
            "reliability": reliability_summary(items), "suggested_profile": candidate['profile'].model_dump(), "suggested_memory_strategy": candidate['strategy'],
            "repair_recommendation": candidate['recommendation'],
            **({"source_memory_capacity":run.target_memory_capacity,"suggested_memory_capacity":candidate['capacity']} if run.target_system_adapter=='controlled-memory' else {}),
            "diagnosis_version": "fact-aware-diagnosis-v8",
            "notice": "Source-message overlap and exact fact correspondence are separate proxies. Paraphrases or bundled facts may not match exactly; neither proxy proves semantic completeness or causal memory use. Interventions are exploratory; independent held-out scenarios and human review are required for value claims."}


@quality_router.post("/audits/{run_id}/diagnostic-agent")
def run_post_diagnostic_agent(run_id: str, db: Session = Depends(get_db)):
    """Run a separate, evidence-bounded model synthesis over a saved diagnosis."""
    run = completed(run_id, db)
    if run.pipeline_provider == "rule_based":
        raise HTTPException(409, "Choose an audit configured with a language model to run the diagnostic Agent.")
    saved = diagnosis(run_id, db)
    cases = saved["cases"]
    if not cases:
        return {
            "run_id": run_id, "diagnosis_version": saved["diagnosis_version"],
            "diagnostic_agent": None,
            "notice": "No diagnosis cases need a model review. No additional model call was made.",
        }

    ids = {memory_id for case in cases for memory_id in case.get("supporting_memory_ids", [])}
    memories = db.scalars(select(MemoryModel).where(MemoryModel.id.in_(ids))).all() if ids else []
    memory_evidence: dict[str, list[dict]] = {}
    for case in cases:
        memory_evidence[case["test_id"]] = [
            {
                "memory_id": memory.id,
                "canonical_value": memory.canonical_value,
                "source_message_ids": memory.source_message_ids or [],
                "confidence": memory.confidence,
                "relationships": [
                    {"type": relation.relationship_type, "target_memory_id": relation.target_memory_id,
                     "evidence_message_ids": relation.evidence_message_ids or [], "confidence": relation.confidence}
                    for relation in db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id == memory.id)).all()
                ],
            }
            for memory in memories if memory.id in case.get("supporting_memory_ids", [])
        ]

    agent = PostRunDiagnosticAgent(PipelineLLMClient(run.pipeline_provider, run.pipeline_model))
    latest = db.scalar(select(AgentExecutionModel).where(AgentExecutionModel.run_id == run_id)
                       .order_by(AgentExecutionModel.created_at.desc(), AgentExecutionModel.id.desc()).limit(1))
    try:
        output = agent.analyse(cases, memory_evidence)
    except Exception as exc:
        observation = agent.last_observation or {}
        failed_row = record_agent_execution(
            db, role="post_run_diagnostic", provider=run.pipeline_provider, model=run.pipeline_model,
            prompt_template_version=PostRunDiagnosticAgent.VERSION,
            instructions=observation.get("instructions", ""), prompt=observation.get("prompt", ""),
            schema=observation.get("schema"), input_payload=observation.get("input_payload", {}),
            input_refs=observation.get("input_refs", {}), output_data=None, status="failed",
            execution=observation.get("execution"), error_code=observation.get("error_code") or type(exc).__name__,
            error_summary="The post-run diagnostic Agent did not return a valid evidence-bounded result.",
            conversation_id=run.conversation_id, run_id=run_id,
            handoff_from=latest.id if latest else None,
        )
        if latest:
            latest.handoff_to = failed_row.id
        db.commit()
        raise HTTPException(502, "The diagnostic Agent could not return a valid result. The failed attempt was recorded.") from exc

    observation = agent.last_observation or {}
    row = record_agent_execution(
        db, role="post_run_diagnostic", provider=run.pipeline_provider, model=run.pipeline_model,
        prompt_template_version=PostRunDiagnosticAgent.VERSION,
        instructions=observation.get("instructions", ""), prompt=observation.get("prompt", ""),
        schema=observation.get("schema"), input_payload=observation.get("input_payload", {}),
        input_refs=observation.get("input_refs", {}), output_data=output, status="completed",
        execution=observation.get("execution"), conversation_id=run.conversation_id, run_id=run_id,
        handoff_from=latest.id if latest else None,
    )
    if latest:
        latest.handoff_to = row.id
    db.commit()
    return {"run_id": run_id, "diagnosis_version": saved["diagnosis_version"],
            "execution_id": row.id, "provider": row.provider, "model": row.model,
            "reported_model": row.reported_model, "diagnostic_agent": output}


def fork_conditions(source: AuditRunModel, db: Session, profiles: list[TargetMemoryProfile], *, role: str, note: str, same_suite: bool = True, conversation_id: str | None = None, commit: bool = True, targeted_memory_strategy: str | None = None, targeted_memory_capacity: int | None = None) -> dict:
    original = audit_schema(source)
    experiment = db.get(ExperimentModel, source.experiment_id) if source.experiment_id else None
    configuration = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration) if experiment else TestSuiteConfiguration(
        test_budget=source.test_budget, random_seed=source.random_seed, pipeline_provider=source.pipeline_provider,
        pipeline_model=source.pipeline_model, semantic_review_provider=source.semantic_review_provider,
        semantic_review_model=source.semantic_review_model,
        evaluator_provider=source.evaluator_provider, evaluator_model=source.evaluator_model)
    configuration = TestSuiteConfiguration.model_validate({**configuration.model_dump(mode="json"),
        "auditor_comparison_id": None, "compare_evaluators": False,
        "random_seed": source.random_seed, "test_budget": source.test_budget,
        "prompt_template_version": source.prompt_template_version,
        "pipeline_provider": source.pipeline_provider, "pipeline_model": source.pipeline_model,
        "semantic_review_provider": source.semantic_review_provider,
        "semantic_review_model": source.semantic_review_model,
        "evaluator_provider": source.evaluator_provider, "evaluator_model": source.evaluator_model,
    })
    group = ExperimentModel(id=ident("EXP"), conversation_id=conversation_id or source.conversation_id, label=f"{role.replace('_',' ').title()} · {datetime.now(timezone.utc).strftime('%d %b %H:%M')}",
                            status="CREATED", test_suite_configuration=configuration.model_dump(mode="json"),
                            test_suite_metadata={"study_role": role, "diagnostic_source_run_id": source.id})
    db.add(group); db.flush()
    runs = []
    local_canonical = {}
    for condition_index, profile in enumerate(profiles):
        candidate_strategy = targeted_memory_strategy if targeted_memory_strategy and condition_index == len(profiles)-1 else None
        target_configuration = ("weak" if candidate_strategy == "weak_first_hit" else "strong") if candidate_strategy and candidate_strategy!=original.memory_strategy else original.target_configuration
        retrieval_mode = ("fixed" if candidate_strategy and candidate_strategy != original.memory_strategy
                         else original.retrieval_mode)
        candidate_capacity = targeted_memory_capacity if targeted_memory_capacity is not None and condition_index==len(profiles)-1 else original.target_memory_capacity
        run = build_audit(AuditCreate(conversation_id=conversation_id or source.conversation_id, experiment_id=group.id,
                          target_configuration=target_configuration, provider=original.provider,
                          model=original.model, temperature=original.temperature,
                          memory_strategy=candidate_strategy or original.memory_strategy, memory_maintenance_policy=original.memory_maintenance_policy,
                          target_memory_capacity=candidate_capacity, target_memory_writer=original.target_memory_writer,
                          retrieval_mode=retrieval_mode,
                          retrieval_provider=original.retrieval_provider if retrieval_mode == "agent" else None,
                          retrieval_model=original.retrieval_model if retrieval_mode == "agent" else None,
                          target_system_adapter=original.target_system_adapter, target_memory_profile=profile), db)
        row = db.get(AuditRunModel, run.run_id)
        metadata = dict(row.reproducibility_metadata)
        metadata.update({"study_role": role, "diagnostic_source_run_id": source.id, "diagnosis_note": note,
                         "human_validation": "pending", "validation_split": "candidate_held_out" if conversation_id else "diagnostic_replay"})
        row.reproducibility_metadata = metadata
        if same_suite:
            originals = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source.id).order_by(TestCaseModel.id)).all()
            copied = persist_generated_tests(db, row, originals)
            for original_case, copy in zip(originals, copied, strict=True):
                identity = original_case.comparison_test_id or original_case.suite_test_id or original_case.id
                copy.comparison_test_id = identity
                if local_canonical:
                    copy.suite_test_id = local_canonical[identity]
            if not local_canonical:
                local_canonical = {copy.comparison_test_id: copy.id for copy in copied}
            row.status = "TESTS_GENERATED"
            if not group.test_suite_source_run_id:
                group.test_suite_source_run_id = row.id
                group.test_suite_metadata = {"test_count": len(copied), "generator_version": originals[0].generator_version if originals else None,
                                             "study_role": role, "diagnostic_source_run_id": source.id}
        runs.append({"run_id": row.id, "label": profile.label})
    if same_suite:
        group.status = "TEST_SUITE_GENERATED"
    if commit:
        db.commit()
    return {"experiment_id": group.id, "runs": runs, "notice": "Candidate new-history validation. This history differs from diagnosis; independent scenario and label review are still required before claiming generalisation." if conversation_id else "Diagnostic replay only: unchanged questions help inspect a repair but cannot establish generalisation. Run these profiles on independent held-out histories."}


@quality_router.post("/audits/{run_id}/repair-experiment", status_code=201)
def create_repair(run_id: str, request: RepairExperimentRequest, db: Session = Depends(get_db)):
    source = completed(run_id, db)
    if request.targeted_memory_capacity is not None and source.target_system_adapter!='controlled-memory':
        raise HTTPException(422,"Capacity changes require the configurable memory target; this independent target does not expose retention control.")
    base = audit_schema(source).target_memory_profile
    if source.provider != 'rule_based':
        fixed_output_limit = base.output_token_limit or 512
        if request.targeted_profile.output_token_limit not in {None, fixed_output_limit}:
            raise HTTPException(422, 'Keep the same answer length limit for original, generic and targeted memory repairs. Test a different answer limit in a separate audit.')
        base = base.model_copy(update={'output_token_limit': fixed_output_limit})
        request.targeted_profile = request.targeted_profile.model_copy(update={'output_token_limit': fixed_output_limit})
    generic_rule = "Read the provided memories carefully and answer accurately. If uncertain, say so rather than guessing."
    generic = base.model_copy(update={"label": "Generic instruction control", "additional_instructions":
        (base.additional_instructions + "\n\n" + generic_rule).strip()})
    if len(generic.additional_instructions) > 4000:
        raise HTTPException(422, "The original instructions leave no room for a generic control instruction. Shorten the original configuration in a new audit before constructing this control.")
    validation_id = request.validation_conversation_id
    if validation_id:
        if validation_id == source.conversation_id:
            raise HTTPException(422, "Choose a different, independently prepared history for held-out validation.")
        conversation = db.get(ConversationModel, validation_id)
        confirmed_memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == validation_id, MemoryModel.status.in_(["confirmed", "edited"]))).all()
        if not conversation or not conversation.authorised or not confirmed_memories:
            raise HTTPException(422, "Prepare and confirm an authorised new history before held-out validation.")
        from app.models import MessageModel
        def source_texts(identity):
            return {" ".join(row.content.casefold().split()) for row in db.scalars(select(MessageModel).where(MessageModel.conversation_id == identity)).all()}
        if source_texts(validation_id) & source_texts(source.conversation_id):
            raise HTTPException(422, "The validation history repeats source messages from diagnosis. Prepare independent scenario content.")
    return fork_conditions(source, db, [base.model_copy(update={"label": "Original configuration"}), generic, request.targeted_profile], role="held_out_repair" if validation_id else "repair_comparison", note=request.diagnosis_note, same_suite=not validation_id, conversation_id=validation_id, targeted_memory_strategy=request.targeted_memory_strategy, targeted_memory_capacity=request.targeted_memory_capacity)


@quality_router.post("/audits/{run_id}/follow-up", status_code=201)
def create_follow_up(run_id: str, request: FollowUpRequest, db: Session = Depends(get_db)):
    source = completed(run_id, db)
    items = [item for item in evaluation_review_items_for(run_id, db) if item.automated.passed is False]
    if not items:
        raise HTTPException(409, "No decided failures are available for exploratory follow-up.")
    package = fork_conditions(source, db, [audit_schema(source).target_memory_profile.model_copy(update={"label": "Exploratory follow-up"})], role="adaptive_follow_up", note="Bounded follow-up selected from decided failures.", same_suite=False, commit=False)
    row = db.get(AuditRunModel, package["runs"][0]["run_id"])
    memories = [memory_schema(db, memory) for memory in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == source.conversation_id)).all()]
    validator = RuleBasedTestQualityValidator()
    tests = []
    for index, item in enumerate(items[:request.test_budget]):
        case = TestCase(**item.test.model_dump()).model_copy(update={"test_id": f"F{index+1}", "run_id": row.id,
                     "prompt": "Before performing the user's next task, verify the following against remembered records. " + item.test.prompt,
                     "generator_version": "adaptive-follow-up-v1", "quality_status": TestQualityStatus.PENDING,
                     "probe_group_id": None, "probe_variant": None, "target_memory_context": []})
        assessment = validator.validate(case, memories)
        if assessment.quality_status == TestQualityStatus.REJECTED:
            continue
        tests.append(case.model_copy(update={"grounding_status": assessment.grounding_status, "validation_notes": "Exploratory probe; review before execution. " + assessment.reason}))
    if not tests:
        db.rollback()
        raise HTTPException(422, "No grounded follow-up questions were produced.")
    persisted = persist_generated_tests(db, row, tests)
    row.status = "TESTS_GENERATED"
    group = db.get(ExperimentModel, package["experiment_id"])
    group.test_suite_source_run_id = row.id
    group.status = "TEST_SUITE_GENERATED"
    group.test_suite_metadata = {**group.test_suite_metadata, "test_count": len(tests), "generator_version": "adaptive-follow-up-v1", "study_role": "adaptive_follow_up"}
    db.commit()
    return {**package, "tests": [public_test_schema(case).model_dump(mode="json") for case in persisted], "notice": "Failure-selected exploratory tests. They do not provide unbiased final performance estimates."}


@quality_router.get("/validation-histories")
def validation_histories(db: Session = Depends(get_db)):
    from app.models import MessageModel
    rows = db.scalars(select(ConversationModel).where(ConversationModel.authorised.is_(True)).order_by(ConversationModel.created_at.desc())).all()
    result = []
    for row in rows:
        confirmed = db.scalar(select(MemoryModel.id).where(MemoryModel.conversation_id == row.id, MemoryModel.status.in_(["confirmed", "edited"])).limit(1))
        message = db.scalar(select(MessageModel).where(MessageModel.conversation_id == row.id).order_by(MessageModel.sequence))
        if confirmed:
            result.append({"conversation_id": row.id, "label": (message.content[:70] if message else "Reviewed history") + " · " + row.created_at.strftime("%d %b %H:%M")})
    return result


@quality_router.post("/audits/{run_id}/interventions", status_code=201)
def create_interventions(run_id: str, db: Session = Depends(get_db)):
    source = completed(run_id, db)
    if source.target_system_adapter != "controlled-memory":
        raise HTTPException(422, "Internal-memory interventions require the configurable target system. Black-box diagnosis remains observational.")
    base = audit_schema(source).target_memory_profile
    profiles = [base.model_copy(update={"label": label}) for label in ("Repeated original", "Remove supplied memory", "Supplement source evidence")]
    package = fork_conditions(source, db, profiles, role="diagnostic_intervention", note="Exploratory intervention: repeated original, removed memory, and target-owned user-history replay. Excluded from generalisation claims.", commit=False)
    for item, intervention in zip(package["runs"], (None, "remove_memory", "supplement_source_evidence"), strict=True):
        row = db.get(AuditRunModel, item["run_id"])
        row.reproducibility_metadata = {**row.reproducibility_metadata, "intervention": intervention}
    db.commit()
    return {**package, "notice": "Exploratory causal probes only. Supplemental evidence replays the original authorised user messages as one source packet. This changes supplied context and is not a production repair, proof of failure cause, or a held-out performance score."}


@quality_router.post("/audits/{run_id}/method-comparison", status_code=201)
def create_method_comparison(run_id: str, db: Session = Depends(get_db)):
    """Fixed target configuration, equal maximum calls, separately frozen suites."""
    source = completed(run_id, db)
    base = audit_schema(source).target_memory_profile
    comparison_id = ident("MCA")
    source_fingerprint = method_comparison_source_fingerprint(source, db)
    draft_questions, draft_fingerprint = method_comparison_fixed_template_draft(source, db)
    packages = []
    for mode, label in ((TestSuiteMode.DIRECT_GROUND_TRUTH, "Direct questions"),
                        (TestSuiteMode.FIXED_TEMPLATE, "Fixed templates"),
                        (TestSuiteMode.CONTEXTUAL_INDIRECT, "Contextual/indirect Auditor tests")):
        package = fork_conditions(source, db, [base.model_copy(update={"label": label})], role="audit_method_comparison", note="Compare test construction methods at one target configuration and equal call caps.", same_suite=False, commit=False)
        group = db.get(ExperimentModel, package["experiment_id"])
        configuration = dict(group.test_suite_configuration)
        configuration["suite_mode"] = mode.value
        group.test_suite_configuration = configuration
        group.test_suite_metadata = {**(group.test_suite_metadata or {}), "method_comparison_id": comparison_id}
        child = db.get(AuditRunModel, package["runs"][0]["run_id"])
        child.reproducibility_metadata = {**(child.reproducibility_metadata or {}), "method_comparison_id": comparison_id}
        packages.append(package)
    db.commit()
    return {"experiment_id": packages[0]["experiment_id"], "comparison_id": comparison_id,
            "study_role": "audit_method_comparison",
            "test_budget": source.test_budget,
            "inventory_template": {"schema_version": "mha-experiment-a-inventory-v1", "comparison_id": comparison_id,
                "release_id": "", "source_fingerprint_sha256": source_fingerprint,
                "annotation_mode": "two_independent_reviewers_with_adjudication", "reviewers": [], "defects": [],
                "fixed_template_release_id": "", "fixed_template_reviewers": [],
                "fixed_template_draft_generator_version": FixedTemplateTestGenerator.VERSION,
                "fixed_template_draft_fingerprint_sha256": draft_fingerprint,
                "fixed_template_review_confirmed": False,
                "fixed_template_questions": draft_questions},
            "runs": [run for package in packages for run in package["runs"]],
            "notice": "Three durable conditions share the reviewed source, target settings and test cap. The fixed-template arm starts from a deterministic rule-generated draft; researchers must review and edit it as needed, fill any missing budget or dimension coverage, and explicitly confirm the final release before freezing. Then review every suite, run and blind-label every response. Target pass rates alone do not establish Auditor effectiveness."}


def method_comparison_fixed_template_draft(source: AuditRunModel, db: Session) -> tuple[list[dict], str]:
    """Create and fingerprint the deterministic, source-bound fixed-template draft."""
    confirmed_rows = db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == source.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    ).order_by(MemoryModel.id)).all()
    memories = [memory_schema(db, row) for row in confirmed_rows]
    source_ids_by_memory = {row.id: set(row.source_message_ids or []) for row in confirmed_rows}
    cases = FixedTemplateTestGenerator().generate(memories, audit_schema(source))
    questions = [{
        "template_id": f"RULE-{case.test_id}",
        "dimension": case.dimension.value,
        "prompt": case.prompt,
        "expected_behavior": case.expected_behavior,
        "supporting_memory_ids": list(case.supporting_memory_ids),
        "source_message_ids": sorted(set().union(*(source_ids_by_memory[memory_id] for memory_id in case.supporting_memory_ids))),
        "test_type": case.test_type.value,
    } for case in cases]
    draft_fingerprint = _method_comparison_template_fingerprint(FixedTemplateTestGenerator.VERSION, questions)
    return questions, draft_fingerprint


def _method_comparison_template_fingerprint(generator_version: str, questions: list[dict]) -> str:
    payload = {"generator_version": generator_version, "questions": questions}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def method_comparison_source_fingerprint(source: AuditRunModel, db: Session) -> str:
    """Bind an Experiment A inventory to the exact authorised source release."""
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == source.conversation_id)
        .order_by(MessageModel.sequence, MessageModel.id)).all()
    memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == source.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"])).order_by(MemoryModel.id)).all()
    payload = {
        "conversation_id": source.conversation_id,
        "messages": [{"message_id": row.source_message_id, "role": row.role, "content": row.content,
                      "timestamp": row.observation_timestamp.isoformat() if row.observation_timestamp else None}
                     for row in messages],
        "confirmed_memories": [memory_schema(db, row).model_dump(mode="json") for row in memories],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@quality_router.post("/audits/{run_id}/method-comparison-inventory", status_code=201)
def freeze_method_comparison_inventory(run_id: str, payload: MethodComparisonInventoryImport, db: Session = Depends(get_db)):
    source = completed(run_id, db)
    if payload.source_fingerprint_sha256 != method_comparison_source_fingerprint(source, db):
        raise HTTPException(409, "The failure inventory was prepared for a different source release. Download a fresh inventory template and reconcile it before freezing.")
    _, current_draft_fingerprint = method_comparison_fixed_template_draft(source, db)
    if payload.fixed_template_draft_fingerprint_sha256 != current_draft_fingerprint:
        raise HTTPException(409, "The rule-generated template draft does not match the current source release. Download a fresh draft and reconcile your review before freezing.")
    groups = [row for row in db.scalars(select(ExperimentModel).where(ExperimentModel.conversation_id == source.conversation_id)
        .order_by(ExperimentModel.created_at, ExperimentModel.id)).all()
        if (row.test_suite_metadata or {}).get("study_role") == "audit_method_comparison"
        and (row.test_suite_metadata or {}).get("diagnostic_source_run_id") == run_id
        and (row.test_suite_metadata or {}).get("method_comparison_id") == payload.comparison_id]
    if len(groups) != 3:
        raise HTTPException(404, "This saved three-method comparison was not found.")
    runs = [run for group in groups for run in db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == group.id)).all()]
    if len(runs) != 3 or any(run.status != AuditStatus.CREATED.value for run in runs):
        raise HTTPException(409, "Freeze the independently reviewed inventory before generating questions or starting any condition.")
    existing = [group.test_suite_metadata.get("failure_inventory") for group in groups]
    packed = payload.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(packed, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if any(item for item in existing):
        if all(item and item.get("inventory_fingerprint_sha256") == fingerprint for item in existing):
            return {"comparison_id": payload.comparison_id, "inventory_fingerprint_sha256": fingerprint,
                    "defect_count": len(payload.defects), "status": "already_frozen"}
        raise HTTPException(409, "The failure inventory is frozen for this comparison. Start a new comparison to use a revised inventory.")
    confirmed_memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == source.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]))).all()
    confirmed_ids = {memory.id for memory in confirmed_memories}
    source_ids_by_memory = {memory.id: set(memory.source_message_ids or []) for memory in confirmed_memories}
    conversation_messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == source.conversation_id)).all()
    user_message_ids = {message.source_message_id for message in conversation_messages if message.role.strip().casefold() == "user"}
    evidence_items = [(f"Defect {item.defect_id}", item) for item in payload.defects]
    evidence_items.extend((f"Fixed template {item.template_id}", item) for item in payload.fixed_template_questions)
    for label, item in evidence_items:
        if not set(item.supporting_memory_ids).issubset(confirmed_ids):
            raise HTTPException(422, f"{label} cites a memory outside the confirmed source ground truth.")
        if not set(item.source_message_ids).issubset(user_message_ids):
            raise HTTPException(422, f"{label} cites a message outside the authorised user source.")
        supported_source_ids = set().union(*(source_ids_by_memory[memory_id] for memory_id in item.supporting_memory_ids))
        if not set(item.source_message_ids).issubset(supported_source_ids):
            raise HTTPException(422, f"{label} cites source messages not linked to its confirmed memories.")
    fixed_runs = [run for run in runs if db.get(ExperimentModel, run.experiment_id).test_suite_configuration.get("suite_mode") == TestSuiteMode.FIXED_TEMPLATE.value]
    if len(fixed_runs) != 1:
        raise HTTPException(409, "The fixed-template condition could not be identified in this saved comparison.")
    fixed_run = fixed_runs[0]
    if len(payload.fixed_template_questions) != fixed_run.test_budget:
        raise HTTPException(422, f"The researcher-reviewed fixed-template release must contain exactly {fixed_run.test_budget} questions to match the frozen test budget.")
    if fixed_run.test_budget >= 4:
        minimum_per_dimension = fixed_run.test_budget // 4
        counts = {dimension: sum(question.dimension == dimension for question in payload.fixed_template_questions) for dimension in Dimension}
        missing = [dimension.value for dimension, count in counts.items() if count < minimum_per_dimension]
        if missing:
            raise HTTPException(422, f"Fixed templates need at least {minimum_per_dimension} questions in each dimension; short: {', '.join(missing)}.")
    template_fingerprint = _method_comparison_template_fingerprint(
        payload.fixed_template_draft_generator_version, [question.model_dump(mode="json") for question in payload.fixed_template_questions])
    inventory = {**packed, "inventory_fingerprint_sha256": fingerprint,
                 "fixed_template_final_fingerprint_sha256": template_fingerprint,
                 "frozen_at": datetime.now(timezone.utc).isoformat(),
                 "fixed_template_review_confirmed_at": datetime.now(timezone.utc).isoformat(),
                 "provenance_notice": "The fixed-template questions began as a deterministic rule-generated draft and were confirmed by the researcher through the review workflow. Reviewer and author identities and independence are self-declared; this record does not verify them."}
    for group in groups:
        group.test_suite_metadata = {**(group.test_suite_metadata or {}), "failure_inventory": inventory,
            "failure_inventory_fingerprint_sha256": fingerprint,
            "failure_inventory_release_id": payload.release_id,
            "failure_inventory_defect_count": len(payload.defects),
            "fixed_template_draft_generator_version": payload.fixed_template_draft_generator_version,
            "fixed_template_draft_fingerprint_sha256": payload.fixed_template_draft_fingerprint_sha256,
            "fixed_template_review_confirmed": payload.fixed_template_review_confirmed,
            "fixed_template_final_fingerprint_sha256": template_fingerprint,
            "fixed_template_reviewers": payload.fixed_template_reviewers}
    for run in runs:
        run.reproducibility_metadata = {**(run.reproducibility_metadata or {}),
            "failure_inventory_fingerprint_sha256": fingerprint,
            "fixed_template_release_id": payload.fixed_template_release_id,
            "fixed_template_draft_generator_version": payload.fixed_template_draft_generator_version,
            "fixed_template_draft_fingerprint_sha256": payload.fixed_template_draft_fingerprint_sha256,
            "fixed_template_review_confirmed": payload.fixed_template_review_confirmed,
            "fixed_template_fingerprint_sha256": template_fingerprint}
    db.commit()
    return {"comparison_id": payload.comparison_id, "inventory_fingerprint_sha256": fingerprint,
            "defect_count": len(payload.defects), "fixed_template_question_count": len(payload.fixed_template_questions),
            "fixed_template_release_id": payload.fixed_template_release_id,
            "fixed_template_draft_fingerprint_sha256": payload.fixed_template_draft_fingerprint_sha256,
            "fixed_template_final_fingerprint_sha256": template_fingerprint,
            "fixed_template_review_confirmed": payload.fixed_template_review_confirmed, "status": "frozen",
            "notice": "The rule-generated draft was reviewed, confirmed and frozen as the fixed-template release. Reviewer and author identities and independence are self-declared, not independently verified."}


@quality_router.post("/audits/{run_id}/method-comparison-discovery-mapping", status_code=201)
def freeze_method_comparison_discovery_mapping(
        run_id: str, payload: MethodComparisonDiscoveryMappingImport, db: Session = Depends(get_db)):
    """Freeze a human mapping from every saved response to zero or more known defects."""
    run = completed(run_id, db)
    group = db.get(ExperimentModel, run.experiment_id) if run.experiment_id else None
    metadata = (group.test_suite_metadata or {}) if group else {}
    if (not group or metadata.get("study_role") != "audit_method_comparison"
            or metadata.get("method_comparison_id") != payload.comparison_id
            or (run.reproducibility_metadata or {}).get("method_comparison_id") != payload.comparison_id):
        raise HTTPException(404, "This completed audit is not a condition in the requested Experiment A comparison.")
    groups = [row for row in db.scalars(select(ExperimentModel).where(
        ExperimentModel.conversation_id == run.conversation_id)).all()
        if (row.test_suite_metadata or {}).get("study_role") == "audit_method_comparison"
        and (row.test_suite_metadata or {}).get("diagnostic_source_run_id") == metadata.get("diagnostic_source_run_id")
        and (row.test_suite_metadata or {}).get("method_comparison_id") == payload.comparison_id]
    inventories = [(row.test_suite_metadata or {}).get("failure_inventory") for row in groups]
    inventory = (metadata.get("failure_inventory") or {})
    inventory_fingerprint = inventory.get("inventory_fingerprint_sha256")
    if (len(groups) != 3 or not inventory_fingerprint
            or payload.inventory_fingerprint_sha256 != inventory_fingerprint
            or any(not item or item.get("inventory_fingerprint_sha256") != inventory_fingerprint for item in inventories)):
        raise HTTPException(409, "The requested source-defect release is missing or inconsistent. Refresh the comparison results before mapping responses.")

    from app.models import TargetResponseModel
    responses = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)
                           .order_by(TargetResponseModel.id)).all()
    response_by_id = {response.id: response for response in responses}
    entry_by_response = {entry.response_id: entry for entry in payload.entries}
    if set(entry_by_response) != set(response_by_id):
        raise HTTPException(422, "Map every saved response exactly once, including responses with no matching known defect.")
    known_defect_ids = {item.get("defect_id") for item in inventory.get("defects", []) if item.get("defect_id")}
    for response_id, entry in entry_by_response.items():
        response = response_by_id[response_id]
        if entry.test_id != response.test_id:
            raise HTTPException(422, "A response-to-test link does not match the saved response record.")
        if not set(entry.defect_ids).issubset(known_defect_ids):
            raise HTTPException(422, "A response mapping cites a defect ID outside the frozen inventory release.")

    packed = payload.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(packed, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")).encode()).hexdigest()
    existing = (run.reproducibility_metadata or {}).get("failure_discovery_mapping")
    if existing:
        if existing.get("mapping_fingerprint_sha256") == fingerprint:
            return {"comparison_id": payload.comparison_id, "run_id": run_id,
                    "mapping_fingerprint_sha256": fingerprint, "status": "already_frozen",
                    "mapped_response_count": len(payload.entries)}
        raise HTTPException(409, "The response-to-defect mapping is frozen. Start a new comparison to replace this release.")
    record = {**packed,
        "run_id": run_id,
        "inventory_release_id": inventory.get("release_id"),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "mapping_fingerprint_sha256": fingerprint,
        "provenance_notice": "A researcher declared that every saved response was mapped to the frozen source-defect inventory. Reviewer identity and mapping quality are not independently verified."}
    run.reproducibility_metadata = {**(run.reproducibility_metadata or {}),
                                    "failure_discovery_mapping": record}
    db.commit()
    return {"comparison_id": payload.comparison_id, "run_id": run_id,
            "mapping_fingerprint_sha256": fingerprint, "status": "frozen",
            "mapped_response_count": len(payload.entries),
            "reviewer_pseudonym": payload.reviewer_pseudonym,
            "notice": record["provenance_notice"]}


@quality_router.get("/audits/{run_id}/method-comparison-results")
def method_comparison_results(run_id: str, comparison_id: str | None = None, db: Session = Depends(get_db)):
    """Experiment A metrics from saved tests, target replies and independent references."""
    source = completed(run_id, db)
    groups = [row for row in db.scalars(select(ExperimentModel).where(ExperimentModel.conversation_id == source.conversation_id)
        .order_by(ExperimentModel.created_at, ExperimentModel.id)).all()
        if (row.test_suite_metadata or {}).get("study_role") == "audit_method_comparison"
        and (row.test_suite_metadata or {}).get("diagnostic_source_run_id") == run_id
        and (comparison_id is None or (row.test_suite_metadata or {}).get("method_comparison_id") == comparison_id)]
    if not groups:
        raise HTTPException(404, "No saved Experiment A comparison was found for this audit.")
    comparison_ids = {row.test_suite_metadata.get("method_comparison_id") for row in groups}
    if comparison_id is None and len(comparison_ids) > 1:
        raise HTTPException(409, "More than one method comparison exists. Supply its comparison_id to inspect one saved result.")
    selected_comparison = next(iter(comparison_ids))
    groups = [row for row in groups if row.test_suite_metadata.get("method_comparison_id") == selected_comparison]
    inventory_records = [row.test_suite_metadata.get("failure_inventory") for row in groups if row.test_suite_metadata.get("failure_inventory")]
    inventory = inventory_records[0] if inventory_records else None
    inventory_consistent = bool(inventory_records) and all(
        item.get("inventory_fingerprint_sha256") == inventory.get("inventory_fingerprint_sha256") for item in inventory_records)
    defect_rows = inventory.get("defects", []) if inventory and inventory_consistent else []
    known_defect_ids = {item["defect_id"] for item in defect_rows if item.get("defect_id")}

    from app.models import TargetResponseModel
    dimensions = ("accuracy", "freshness", "conflict_resolution", "appropriate_use")
    rows = []
    setting_signatures = []
    budgets = set()
    actual_call_totals = []
    for group in groups:
        group_runs = db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == group.id).order_by(AuditRunModel.created_at, AuditRunModel.id)).all()
        for run in group_runs:
            tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
            responses = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run.id)).all()
            attempts = [(response.execution_metadata or {}).get("request_attempts") for response in responses]
            known_attempts = [value for value in attempts if type(value) is int and value >= 0]
            unknown_attempt_records = len(attempts) - len(known_attempts)
            calls = sum(known_attempts) if responses and not unknown_attempt_records else None
            if calls is not None:
                actual_call_totals.append(calls)
            budgets.add(run.test_budget)
            audit = audit_schema(run)
            profile = audit.target_memory_profile.model_dump(mode="json")
            profile.pop("label", None)
            settings = {"target_configuration": run.target_configuration, "provider": run.provider, "model": run.model,
                "temperature": run.temperature, "memory_strategy": run.memory_strategy,
                "memory_maintenance_policy": run.memory_maintenance_policy, "target_memory_capacity": run.target_memory_capacity,
                "target_memory_writer": run.target_memory_writer, "target_memory_profile": profile,
                "target_system_adapter": run.target_system_adapter, "retrieval_mode": run.retrieval_mode,
                "retrieval_provider": run.retrieval_provider, "retrieval_model": run.retrieval_model,
                "pipeline_provider": run.pipeline_provider, "pipeline_model": run.pipeline_model,
                "semantic_review_provider": run.semantic_review_provider, "semantic_review_model": run.semantic_review_model,
                "evaluator_provider": run.evaluator_provider, "evaluator_model": run.evaluator_model,
                "test_budget": run.test_budget, "random_seed": run.random_seed,
                "prompt_template_version": run.prompt_template_version}
            setting_signatures.append(json.dumps(settings, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            items = evaluation_review_items_for(run.id, db) if run.status == "COMPLETED" else []
            tp = fn = fp = tn = reviewed_responses = reference_only_responses = 0
            discovered_defects: set[str] = set()
            covered_categories: set[str] = set()
            confirmed_findings: set[tuple[str, tuple[str, ...]]] = set()
            responses_by_id = {response.id: response for response in responses}
            tests_by_id = {test.id: test for test in tests}
            saved_mapping = (run.reproducibility_metadata or {}).get("failure_discovery_mapping")
            mapping_fields = ("schema_version", "comparison_id", "inventory_fingerprint_sha256",
                              "mapping_release_id", "reviewer_pseudonym", "completed_by_human", "entries")
            signed_mapping = {key: saved_mapping.get(key) for key in mapping_fields} if isinstance(saved_mapping, dict) else None
            signed_mapping_hash = hashlib.sha256(json.dumps(signed_mapping, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode()).hexdigest() if signed_mapping else None
            saved_entries = saved_mapping.get("entries", []) if isinstance(saved_mapping, dict) else []
            saved_entries_well_formed = isinstance(saved_entries, list) and all(
                isinstance(entry, dict) and isinstance(entry.get("response_id"), str)
                and isinstance(entry.get("test_id"), str) and isinstance(entry.get("defect_ids"), list)
                and all(isinstance(defect_id, str) for defect_id in entry.get("defect_ids", []))
                for entry in saved_entries)
            mapping_by_response = ({entry["response_id"]: entry for entry in saved_entries}
                                   if saved_entries_well_formed else {})
            mapping_response_ids = set(mapping_by_response)
            actual_response_ids = set(responses_by_id)
            mapping_ids_valid = all(
                entry.get("test_id") == responses_by_id[response_id].test_id
                and set(entry.get("defect_ids", [] )).issubset(known_defect_ids)
                for response_id, entry in mapping_by_response.items() if response_id in responses_by_id
            ) and mapping_response_ids.issubset(actual_response_ids)
            mapping_consistent = bool(
                inventory_consistent and isinstance(saved_mapping, dict)
                and saved_mapping.get("schema_version") == "mha-experiment-a-discovery-map-v1"
                and saved_mapping.get("comparison_id") == selected_comparison
                and saved_mapping.get("run_id") == run.id
                and saved_mapping.get("inventory_fingerprint_sha256") == inventory.get("inventory_fingerprint_sha256")
                and saved_mapping.get("inventory_release_id") == inventory.get("release_id")
                and saved_mapping.get("completed_by_human") is True
                and isinstance(saved_mapping.get("reviewer_pseudonym"), str)
                and bool(saved_mapping.get("reviewer_pseudonym", "").strip())
                and isinstance(saved_mapping.get("mapping_release_id"), str)
                and bool(saved_mapping.get("mapping_release_id", "").strip())
                and signed_mapping_hash == saved_mapping.get("mapping_fingerprint_sha256")
                and saved_entries_well_formed
                and len(mapping_by_response) == len(saved_entries)
                and mapping_ids_valid
            )
            mapping_complete = mapping_consistent and mapping_response_ids == actual_response_ids
            mapping_status = ("frozen" if mapping_complete else "missing_or_inconsistent" if saved_mapping else "awaiting_researcher_mapping")
            resolved_labels: dict[str, bool] = {}
            for item in items:
                independent = [review for review in item.human_reviews if review.review_role == "independent"]
                final = item.human_review if item.human_review and item.human_review.review_role == "adjudication" and item.independent_reviewer_count >= 2 else None
                independent_verdicts = {review.human_passed for review in independent}
                if final:
                    human_passed = final.human_passed
                    human_category = final.human_failure_type.value if final.human_failure_type else None
                elif item.independent_reviewer_count >= 2 and len(independent_verdicts) == 1:
                    human_passed = next(iter(independent_verdicts))
                    categories = {review.human_failure_type.value if review.human_failure_type else None for review in independent}
                    human_category = next(iter(categories)) if len(categories) == 1 else None
                else:
                    reference_only_responses += int(item.human_review is not None or bool(item.human_reviews))
                    continue
                reviewed_responses += 1
                resolved_labels[item.response.response_id] = human_passed
                automated = item.automated.passed
                if human_passed:
                    if automated is False: fp += 1
                    else: tn += 1
                    continue
                if automated is False: tp += 1
                else: fn += 1
                if human_category:
                    covered_categories.add(human_category)
                    family = (human_category, tuple(sorted(item.test.supporting_memory_ids)))
                    confirmed_findings.add(family)
                if not human_passed and mapping_complete:
                    mapped = mapping_by_response.get(item.response.response_id, {})
                    discovered_defects.update(mapped.get("defect_ids", []))
            mapping_review_rows = [{
                "response_id": response.id,
                "test_id": response.test_id,
                "question": tests_by_id[response.test_id].prompt if response.test_id in tests_by_id else "",
                "response": response.response_text,
                "human_passed": resolved_labels.get(response.id),
                "defect_ids": mapping_by_response.get(response.id, {}).get("defect_ids", []),
            } for response in responses]
            human_validity_reviewed = [test for test in tests if test.human_validity_status in {
                HumanValidityStatus.ACCEPTED.value, HumanValidityStatus.REJECTED.value,
            }]
            human_validity_accepted = [test for test in tests
                if test.human_validity_status == HumanValidityStatus.ACCEPTED.value]
            validity_review_complete = bool(tests) and len(human_validity_reviewed) == len(tests)
            accepted_tests = [test for test in tests
                if test.quality_status == TestQualityStatus.ACCEPTED.value
                and test.grounding_status == GroundingStatus.GROUNDED.value
                and test.human_validity_status == HumanValidityStatus.ACCEPTED.value]
            valid_dimensions = sorted({test.dimension for test in accepted_tests})
            actual_discovery_numerator = len(discovered_defects) if mapping_complete and inventory_consistent else None
            defect_count = len(defect_rows) if inventory_consistent else None
            discovery_ready = bool(inventory_consistent and defect_count and run.status == "COMPLETED"
                and len(responses) > 0 and reviewed_responses == len(responses) and mapping_complete)
            if not inventory_consistent:
                discovery_status = "inventory_missing_or_inconsistent"
            elif defect_count == 0:
                discovery_status = "no_known_defects"
            elif run.status != "COMPLETED":
                discovery_status = "run_incomplete"
            elif reviewed_responses != len(responses):
                discovery_status = "awaiting_independent_labels"
            elif not mapping_complete:
                discovery_status = "awaiting_researcher_mapping" if not saved_mapping else "mapping_missing_or_inconsistent"
            else:
                discovery_status = "measured"
            rows.append({"run_id": run.id, "label": audit.target_memory_profile.label,
                "suite_mode": group.test_suite_configuration.get("suite_mode"), "status": run.status,
                "test_budget": run.test_budget, "planned_call_cap": run.test_budget,
                "actual_target_call_attempts": calls, "completed_answers": len(responses),
                "unknown_attempt_records": unknown_attempt_records, "test_count": len(tests),
                "valid_test_count": len(accepted_tests), "valid_test_dimensions": valid_dimensions,
                "human_validity_accepted_count": len(human_validity_accepted),
                "human_validity_reviewed_count": len(human_validity_reviewed),
                "human_validity_pending_count": len(tests) - len(human_validity_reviewed),
                "human_validity_acceptance_rate": (len(human_validity_accepted) / len(human_validity_reviewed)
                    if human_validity_reviewed else None),
                "human_confirmed_failure_categories": sorted(covered_categories),
                "category_coverage": {"covered_dimensions": len(valid_dimensions), "total_dimensions": len(dimensions),
                    "value": len(valid_dimensions) / len(dimensions) if validity_review_complete else None,
                    "status": ("not_generated" if not tests else
                        "measured" if validity_review_complete else "awaiting_human_validity_review")},
                "response_level": {"independently_labelled_responses": reviewed_responses,
                    "unresolved_or_single_reviewer_labels": reference_only_responses,
                    "true_positives": tp, "false_negatives": fn, "false_positives": fp, "true_negatives": tn,
                    "failure_detection_recall": tp / (tp + fn) if tp + fn else None,
                    "false_positive_rate": fp / (fp + tn) if fp + tn else None,
                    "status": ("run_incomplete" if run.status != "COMPLETED" or not responses else
                        "measured" if reviewed_responses == len(responses) else "partial_or_awaiting_independent_labels")},
                "failure_discovery_rate": {"discovered_distinct_failures": actual_discovery_numerator if discovery_ready else None,
                    "known_distinct_failures": defect_count,
                    "value": actual_discovery_numerator / defect_count if discovery_ready else None,
                    "undiscovered_failure_ids": sorted(known_defect_ids - discovered_defects) if discovery_ready else None,
                    "status": discovery_status},
                "discovery_mapping": {"status": mapping_status,
                    "release_id": saved_mapping.get("mapping_release_id") if mapping_consistent else None,
                    "reviewer_pseudonym": saved_mapping.get("reviewer_pseudonym") if mapping_consistent else None,
                    "fingerprint_sha256": saved_mapping.get("mapping_fingerprint_sha256") if mapping_consistent else None,
                    "mapped_response_count": len(mapping_by_response) if mapping_consistent else 0,
                    "total_response_count": len(responses),
                    "entries": mapping_review_rows},
                "human_confirmed_distinct_findings": len(confirmed_findings),
                "automated_failures": sum(item.automated.passed is False for item in items)})
    return {"comparison_id": selected_comparison, "source_run_id": run_id,
        "source_fingerprint_sha256": method_comparison_source_fingerprint(source, db),
        "inventory": {"status": "frozen" if inventory_consistent else "missing_or_inconsistent",
            "release_id": inventory.get("release_id") if inventory_consistent else None,
            "fingerprint_sha256": inventory.get("inventory_fingerprint_sha256") if inventory_consistent else None,
            "distinct_failure_count": len(defect_rows) if inventory_consistent else None,
            "reviewers": inventory.get("reviewers") if inventory_consistent else None,
            "authorship_verified": False,
            "fixed_template_release_id": inventory.get("fixed_template_release_id") if inventory_consistent else None,
            "fixed_template_reviewers": (inventory.get("fixed_template_reviewers") or inventory.get("fixed_template_authors")) if inventory_consistent else None,
            "fixed_template_question_count": len(inventory.get("fixed_template_questions", [])) if inventory_consistent else None,
            "fixed_template_draft_generator_version": inventory.get("fixed_template_draft_generator_version") if inventory_consistent else None,
            "fixed_template_draft_fingerprint_sha256": inventory.get("fixed_template_draft_fingerprint_sha256") if inventory_consistent else None,
            "fixed_template_final_fingerprint_sha256": inventory.get("fixed_template_final_fingerprint_sha256") if inventory_consistent else None,
            "fixed_template_review_confirmed": inventory.get("fixed_template_review_confirmed", False) if inventory_consistent else False,
            "fixed_template_review_identity_verified": False,
            "defects": [{"defect_id": item["defect_id"], "dimension": item["dimension"],
                         "explanation": item["explanation"]} for item in defect_rows] if inventory_consistent else []},
        "planned_test_budgets_equal": len(budgets) == 1 and len(groups) == 3 and len(rows) == 3,
        "target_and_evaluation_settings_match": len(set(setting_signatures)) == 1 and len(rows) == 3,
        "realised_call_attempts_equal": (len(set(actual_call_totals)) == 1 if len(actual_call_totals) == 3 else None),
        "conditions": rows,
        "notice": "Failure-detection recall uses only response labels agreed by two independent reviewers or resolved by an adjudication citing two independent reviews. Category coverage counts manually accepted grounded tests across the four dimensions. Failure discovery rate counts distinct frozen defect IDs explicitly mapped to human-confirmed failed responses by a researcher; every saved response must be mapped, including an explicit empty list when no known defect was found. Reviewer identity and mapping quality remain self-declared; missing inventory, labels or mappings are reported as unmeasured. Actual calls include recorded retries; calls without saved responses remain unknown."}
