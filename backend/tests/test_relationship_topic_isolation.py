from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.schemas import Memory, MemoryStatus, TestCase as Case, TestQualityStatus


def test_project_prefix_facts_are_retained_and_isolated():
    from app.services.memory_entities import named_projects
    extractor = RuleBasedMemoryExtractor()
    assert extractor._is_memory_statement("Project Cedar uses PostgreSQL.")
    assert named_projects("Project Cedar uses PostgreSQL.") == {"cedar"}
    assert named_projects("Project Maple now uses SQLite.") == {"maple"}
    old = Memory(memory_id="C", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="Project Cedar uses PostgreSQL.")
    new = Memory(memory_id="M", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="Project Maple now uses SQLite.")
    assert not extractor._relationships(new, [old])


def test_shared_project_name_does_not_link_database_to_updated_logs():
    extractor = RuleBasedMemoryExtractor()
    old = Memory(
        memory_id="M1",
        conversation_id="C1",
        status=MemoryStatus.CONFIRMED,
        canonical_value="The Beacon backend previously used MySQL.",
    )
    new = Memory(
        memory_id="M2",
        conversation_id="C1",
        status=MemoryStatus.CONFIRMED,
        canonical_value="The Beacon logs now remain in object storage.",
    )
    assert not extractor._relationships(new, [old])


def test_other_project_update_does_not_supersede_an_active_database():
    extractor = RuleBasedMemoryExtractor()
    old = Memory(memory_id='M1', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                 canonical_value='The Alpha River backend now uses PostgreSQL.')
    new = Memory(memory_id='M2', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                 canonical_value='The Beta River backend now uses SQLite.')
    assert not extractor._relationships(new, [old])
    from app.services.memory_entities import named_projects
    assert named_projects('Which database does the Alpha River backend use now?') == {'alpha river'}
    assert named_projects('The Beta River deployment policy requires secrets.') == {'beta river'}
    assert not named_projects('Where should deployment secrets be kept?')


def test_question_answer_topic_mismatch_is_rejected():
    memory = Memory(
        memory_id="M1",
        conversation_id="C1",
        status=MemoryStatus.CONFIRMED,
        canonical_value="The Beacon logs now remain in object storage.",
    )
    test = Case(
        test_id="T1",
        run_id="RUN1",
        dimension="freshness",
        prompt="Which database technology applies now?",
        expected_behavior="Use the later record: The Beacon logs now remain in object storage.",
        supporting_memory_ids=["M1"],
        generator_version="test",
    )
    assert (
        RuleBasedTestQualityValidator().validate(test, [memory]).quality_status
        == TestQualityStatus.REJECTED
    )


def test_go_language_preference_gets_contextual_override_without_linking_travel():
    from app.schemas import RelationshipType
    extractor = RuleBasedMemoryExtractor()
    preference = Memory(memory_id="GO", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="I generally prefer Go.")
    requirement = Memory(memory_id="JAVA", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="For the current ELEC5623 assignment, Java is required.")
    relationships = extractor._relationships(requirement, [preference])
    assert [(relation.type, relation.target_memory_id) for relation in relationships] == [(RelationshipType.CONTEXTUAL_OVERRIDE, "GO")]
    travel = preference.model_copy(update={"canonical_value": "I prefer go hiking."})
    assert not extractor._relationships(requirement, [travel])
    assert extractor._category("I generally prefer Golang.") == "programming-language"


def test_generated_questions_disambiguate_named_projects_without_answer_leakage():
    from datetime import datetime, timezone
    from app.schemas import AuditRun, AuditStatus, RelationshipType, MemoryRelationship, TargetConfiguration, TargetProvider
    from app.test_generator.rule_based import RuleBasedTestGenerator
    memories = [
        Memory(memory_id="A1", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="The Alpha River backend previously used MySQL."),
        Memory(memory_id="A2", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="The Alpha River backend now uses PostgreSQL.", relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="A1")]),
        Memory(memory_id="B1", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="The Beta River backend previously used SQLite."),
        Memory(memory_id="B2", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="The Beta River backend now uses MySQL.", relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="B1")]),
    ]
    run = AuditRun(run_id="RUN_SCOPE", conversation_id="C", status=AuditStatus.CREATED, target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.OLLAMA, model="qwen3:1.7b", temperature=0, random_seed=42, test_budget=8, prompt_template_version=RuleBasedTestGenerator.VERSION, created_at=datetime.now(timezone.utc))
    questions = RuleBasedTestGenerator().generate(memories, run)
    assert len(questions) == 4
    assert len({test.prompt for test in questions}) == 4
    for question in questions:
        expected_project = "alpha river" if "A2" in question.supporting_memory_ids else "beta river"
        from app.services.memory_entities import named_projects
        assert named_projects(question.prompt) == {expected_project}
        assert not any(value in question.prompt.lower() for value in ("postgresql", "mysql", "sqlite"))
        assert RuleBasedTestQualityValidator().validate(question, memories).quality_status == TestQualityStatus.ACCEPTED


def test_move_to_a_new_city_generates_current_location_probes_and_blocks_answer_leakage():
    from datetime import datetime, timezone, timedelta
    from app.schemas import AuditRun, AuditStatus, Conversation, ConversationMessage, Dimension, RelationshipType, TargetConfiguration, TargetProvider
    from app.test_generator.rule_based import RuleBasedTestGenerator
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    for update in ("I moved to Launceston.", "I relocated to Port Macquarie."):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        conversation = Conversation(conversation_id="C", created_at=base, authorised=True, messages=[
            ConversationMessage(message_id="N", role="user", content=update, timestamp=base + timedelta(days=1)),
            ConversationMessage(message_id="O", role="user", content="I live in Canberra.", timestamp=base),
        ])
        memories = RuleBasedMemoryExtractor().extract(conversation)
        for memory in memories:
            memory.status = MemoryStatus.CONFIRMED
        assert [(r.type, r.target_memory_id) for r in memories[1].relationships] == [(RelationshipType.UPDATE, memories[0].memory_id)]
        run = AuditRun(run_id="R", conversation_id="C", status=AuditStatus.CREATED, target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.OLLAMA, model="qwen3:1.7b", temperature=0, random_seed=42, test_budget=4, prompt_template_version=RuleBasedTestGenerator.VERSION, created_at=base)
        questions = RuleBasedTestGenerator().generate(memories, run)
        assert {q.dimension for q in questions} == {Dimension.FRESHNESS, Dimension.CONFLICT_RESOLUTION}
        assert "Where is the user based now?" in questions[0].prompt
        for question in questions:
            assert update.rstrip(".") in question.expected_behavior
            assert "Canberra" not in question.prompt and "Launceston" not in question.prompt and "Macquarie" not in question.prompt
            assert RuleBasedTestQualityValidator().validate(question, memories).quality_status == TestQualityStatus.ACCEPTED
        leaked = questions[0].model_copy(update={"prompt": "Is the user based in " + update.split("to ")[1]})
        assert RuleBasedTestQualityValidator().validate(leaked, memories).quality_status == TestQualityStatus.REJECTED
        assert RuleBasedBehaviourEvaluator._required_terms("Use the later record: I relocated to Port Macquarie.") == ["port", "macquarie"]
