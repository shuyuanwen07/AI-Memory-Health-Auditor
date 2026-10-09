"""Auditor reliability, exploratory diagnosis and controlled repair workflows."""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models import AuditRunModel, ConversationModel, ExperimentModel, TestCaseModel, MemoryModel, MessageModel
from app.schemas import AuditCreate, AuditStatus, TestSuiteConfiguration, TestSuiteMode, TestCase, TestQualityStatus
from app.schemas.target_profile import RepairExperimentRequest, TargetMemoryProfile, FollowUpRequest
from app.api.routes import (audit_schema, build_audit, evaluation_review_items_for, target_memory_trace_payload,
                            ident, memory_schema, persist_generated_tests, public_test_schema)
from app.services.auditor_quality import reliability_summary, paired_probe_summary
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.services.evidence_correspondence import correspondence, evidence_units
from app.services.memory_availability import availability
from app.services.repair_recommendation import recommend_repair
from app.services.input_delivery import input_delivery

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
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.status == "COMPLETED")).all()
    items = [item for run in runs for item in evaluation_review_items_for(run.id, db)]
    report = reliability_summary(items)
    report["completed_runs"] = len(runs)
    report["scenario_count"] = len({run.conversation_id for run in runs})
    report["review_queue"] = [{"run_id": run.id, "model": run.model,
                                "created_at": run.created_at.isoformat(),
                                "unreviewed": sum(item.human_review is None for item in evaluation_review_items_for(run.id, db))}
                               for run in runs]
    return report


@quality_router.get("/audits/{run_id}/blind-review")
def blind_review(run_id: str, db: Session = Depends(get_db)):
    # Actual server-side withholding: no automated verdict, model, configuration,
    # judge reason or another reviewer's labels are returned.
    items = evaluation_review_items_for(run_id, db)
    run = db.get(AuditRunModel, run_id)
    references = {memory.id: memory.source_message_ids for memory in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == run.conversation_id)).all()}
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == run.conversation_id).order_by(MessageModel.sequence)).all()
    return [{"test": {"test_id": item.test.test_id, "prompt": item.test.prompt,
                       "expected_behavior": item.test.expected_behavior},
             "response": {"response_text": item.response.response_text},
             "automated": {"evaluation_id": item.automated.evaluation_id},
             "source_statements": [{"content": message.content, "timestamp": message.timestamp.isoformat()} for message in messages if message.source_message_id in {key for memory_id in item.test.supporting_memory_ids for key in references.get(memory_id, [])}],
             "human_reviews": [], "human_review": None}
            for item in items]


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


def fork_conditions(source: AuditRunModel, db: Session, profiles: list[TargetMemoryProfile], *, role: str, note: str, same_suite: bool = True, conversation_id: str | None = None, commit: bool = True, targeted_memory_strategy: str | None = None, targeted_memory_capacity: int | None = None) -> dict:
    original = audit_schema(source)
    experiment = db.get(ExperimentModel, source.experiment_id) if source.experiment_id else None
    configuration = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration) if experiment else TestSuiteConfiguration(
        test_budget=source.test_budget, random_seed=source.random_seed, pipeline_provider=source.pipeline_provider,
        pipeline_model=source.pipeline_model, evaluator_provider=source.evaluator_provider, evaluator_model=source.evaluator_model)
    group = ExperimentModel(id=ident("EXP"), conversation_id=conversation_id or source.conversation_id, label=f"{role.replace('_',' ').title()} · {datetime.now(timezone.utc).strftime('%d %b %H:%M')}",
                            status="CREATED", test_suite_configuration=configuration.model_dump(mode="json"), test_suite_metadata={})
    db.add(group); db.flush()
    runs = []
    local_canonical = {}
    for condition_index, profile in enumerate(profiles):
        candidate_strategy = targeted_memory_strategy if targeted_memory_strategy and condition_index == len(profiles)-1 else None
        target_configuration = ("weak" if candidate_strategy == "weak_first_hit" else "strong") if candidate_strategy and candidate_strategy!=original.memory_strategy else original.target_configuration
        candidate_capacity = targeted_memory_capacity if targeted_memory_capacity is not None and condition_index==len(profiles)-1 else original.target_memory_capacity
        run = build_audit(AuditCreate(conversation_id=conversation_id or source.conversation_id, experiment_id=group.id,
                          target_configuration=target_configuration, provider=original.provider,
                          model=original.model, temperature=original.temperature,
                          memory_strategy=candidate_strategy or original.memory_strategy, memory_maintenance_policy=original.memory_maintenance_policy,
                          target_memory_capacity=candidate_capacity, target_memory_writer=original.target_memory_writer,
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
    group.test_suite_metadata = {"test_count": len(tests), "generator_version": "adaptive-follow-up-v1", "study_role": "adaptive_follow_up"}
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
    package = fork_conditions(source, db, profiles, role="diagnostic_intervention", note="Exploratory intervention: repeated original, removed memory, and oracle source evidence. Excluded from generalisation claims.", commit=False)
    for item, intervention in zip(package["runs"], (None, "remove_memory", "supplement_source_evidence"), strict=True):
        row = db.get(AuditRunModel, item["run_id"])
        row.reproducibility_metadata = {**row.reproducibility_metadata, "intervention": intervention}
    db.commit()
    return {**package, "notice": "Exploratory causal probes only. Supplemental evidence comes from authorised source messages identified by the audit; this oracle intervention is not a production repair or a held-out performance score."}


@quality_router.post("/audits/{run_id}/method-comparison", status_code=201)
def create_method_comparison(run_id: str, db: Session = Depends(get_db)):
    """Fixed target configuration, equal maximum calls, separately frozen suites."""
    source = completed(run_id, db)
    base = audit_schema(source).target_memory_profile
    packages = []
    for mode, label in ((TestSuiteMode.DIRECT_GROUND_TRUTH, "Direct questions"),
                        (TestSuiteMode.FIXED_TEMPLATE, "Fixed templates"),
                        (TestSuiteMode.PAIRED_CONTEXTUAL, "Paired contextual probes")):
        package = fork_conditions(source, db, [base.model_copy(update={"label": label})], role="audit_method_comparison", note="Compare test construction methods at one target configuration and equal call caps.", same_suite=False, commit=False)
        group = db.get(ExperimentModel, package["experiment_id"])
        configuration = dict(group.test_suite_configuration)
        configuration["suite_mode"] = mode.value
        group.test_suite_configuration = configuration
        packages.append(package)
    db.commit()
    return {"experiment_id": packages[0]["experiment_id"], "runs": [run for package in packages for run in package["runs"]],
            "notice": "Different audit methods use different questions at the same maximum call budget. Review every suite. Compare human-confirmed distinct defects and actual call counts; target pass-rate differences alone do not establish auditor superiority."}


@quality_router.get("/audits/{run_id}/method-comparison-results")
def method_comparison_results(run_id: str, db: Session = Depends(get_db)):
    """Human-confirmed discoveries per source scenario, not raw failure totals."""
    source = completed(run_id, db)
    runs = [row for row in db.scalars(select(AuditRunModel).where(AuditRunModel.conversation_id == source.conversation_id)).all()
            if (row.reproducibility_metadata or {}).get("study_role") == "audit_method_comparison"
            and row.reproducibility_metadata.get("diagnostic_source_run_id") == run_id]
    rows = []
    for run in runs:
        tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
        from app.models import TargetResponseModel
        responses = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run.id)).all()
        attempts = [(response.execution_metadata or {}).get("request_attempts") for response in responses]
        known_attempts = [value for value in attempts if type(value) is int and value >= 0]
        unknown_attempt_records = len(attempts) - len(known_attempts)
        calls = sum(known_attempts) if not unknown_attempt_records else None
        items = evaluation_review_items_for(run.id, db) if run.status == "COMPLETED" else []
        confirmed = {tuple(sorted(item.test.supporting_memory_ids)) + (item.human_review.human_failure_type.value if item.human_review.human_failure_type else item.test.dimension.value,)
                     for item in items if item.human_review and not item.human_review.human_passed and item.automated.passed is False}
        rows.append({"run_id": run.id, "label": audit_schema(run).target_memory_profile.label,
                     "status": run.status, "planned_call_cap": run.test_budget, "actual_calls": calls,
                     "completed_answers": len(responses), "recorded_request_attempts": calls,
                     "known_request_attempts": sum(known_attempts), "unknown_attempt_records": unknown_attempt_records,
                     "test_count": len(tests), "resolved_labels": sum(item.human_review is not None for item in items),
                     "human_confirmed_distinct_findings": len(confirmed),
                     "automated_failures": sum(item.automated.passed is False for item in items)})
    return {"conditions": rows, "source_scenarios": 1 if rows else 0,
            "notice": "Request attempts include recorded retries for saved answers; missing attempt metadata stays unknown. Calls that never produced a saved answer are not covered, so these counts do not certify equal realised budgets. Discovery counts require explicit resolved human labels and deduplicate evidence-family plus failure class within each history. Recall requires an independently established defect inventory; these counts do not supply that inventory or prove novelty."}
