from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.schemas import Memory, MemoryStatus, TestCase as Case, TestQualityStatus


def test_relationship_agent_accepts_both_endpoints_from_same_message():
    from datetime import datetime, timezone
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage
    now = datetime.now(timezone.utc)
    source = 'I generally use paper notes, but this project requires encrypted notes.'
    conversation = Conversation(conversation_id='C', created_at=now, authorised=True,
        messages=[ConversationMessage(message_id='S001', role='user', content=source, timestamp=now)])
    memories = [Memory(memory_id='M001',conversation_id='C',status=MemoryStatus.CANDIDATE,
                       canonical_value='I generally use paper notes.',source_message_ids=['S001']),
                Memory(memory_id='M002',conversation_id='C',status=MemoryStatus.CANDIDATE,
                       canonical_value='This project requires encrypted notes.',source_message_ids=['S001'])]
    class ReplyClient:
        provider = 'fixture'
        model = 'fixture'
        last_execution = None
        def complete_json(self, **request):
            assert request['prompt_template_version']=='relationship-analysis-agent-v7'
            assert 'same message ID may appear in both lists' in request['instructions']
            return {'relationships':[{'current_memory_id':'M002','prior_memory_id':'M001',
                'type':'CONTEXTUAL_OVERRIDE','current_evidence_message_ids':['S001'],
                'prior_evidence_message_ids':['S001'],'confidence':0.9,
                'rationale':'The project requirement is explicitly scoped.'}]}
    result=RelationshipAnalysisAgent(ReplyClient()).analyze(conversation,memories)
    assert result['relationships'][0]['evidence_message_ids']==['S001']
    assert memories[1].relationships[0].target_memory_id=='M001'


def test_project_prefix_facts_are_retained_and_isolated():
    from app.services.memory_entities import named_projects
    extractor = RuleBasedMemoryExtractor()
    assert extractor._is_memory_statement("Project Cedar uses PostgreSQL.")
    assert named_projects("Project Cedar uses PostgreSQL.") == {"cedar"}
    assert named_projects("Project Maple now uses SQLite.") == {"maple"}
    old = Memory(memory_id="C", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="Project Cedar uses PostgreSQL.")
    new = Memory(memory_id="M", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="Project Maple now uses SQLite.")
    assert not extractor._relationships(new, [old])


def test_lowercase_project_prefix_keeps_the_name_and_never_treats_for_as_a_name():
    from app.services.memory_entities import named_projects
    from app.test_generator.rule_based import RuleBasedTestGenerator
    cedar=Memory(memory_id='CEDAR',conversation_id='C',status=MemoryStatus.CONFIRMED,
                 canonical_value='For project Cedar, Java is required.')
    maple=cedar.model_copy(update={'memory_id':'MAPLE','canonical_value':'For project Maple, Rust is required.'})
    assert named_projects(cedar.canonical_value)=={'cedar'}
    assert named_projects('For project Cedar meetings, only Zoom is allowed.')=={'cedar'}
    assert named_projects('For project work, I generally prefer Python.')==set()
    assert not RuleBasedMemoryExtractor()._relationships(maple,[cedar])
    topic=RuleBasedTestGenerator._scoped_topic(cedar)
    assert topic=='programming-language choice for the Cedar project'


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
    assert len(questions) == 6
    assert len({test.prompt for test in questions}) == 6
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
        assert {q.dimension for q in questions} == {Dimension.ACCURACY, Dimension.FRESHNESS, Dimension.CONFLICT_RESOLUTION}
        freshness = next(question for question in questions if question.dimension == Dimension.FRESHNESS)
        assert "Where is the user based now?" in freshness.prompt
        for question in (item for item in questions if item.dimension != Dimension.ACCURACY):
            assert update.rstrip(".") in question.expected_behavior
            assert "Canberra" not in question.prompt and "Launceston" not in question.prompt and "Macquarie" not in question.prompt
            assert RuleBasedTestQualityValidator().validate(question, memories).quality_status == TestQualityStatus.ACCEPTED
        leaked = questions[0].model_copy(update={"prompt": "Is the user based in " + update.split("to ")[1]})
        assert RuleBasedTestQualityValidator().validate(leaked, memories).quality_status == TestQualityStatus.REJECTED
        assert RuleBasedBehaviourEvaluator._required_terms("Use the later record: I relocated to Port Macquarie.") == ["port", "macquarie"]


def test_named_review_scopes_keep_independent_project_platforms_separate():
    from app.services.memory_entities import named_projects
    assert named_projects('The Willow review must use Zoom only.') == {'willow'}
    assert named_projects('The review must use Zoom only.') == set()
    extractor = RuleBasedMemoryExtractor()
    first = Memory(memory_id='W',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Willow review must use Zoom only')
    other = first.model_copy(update={'memory_id':'B','canonical_value':'Birch review must use Teams only'})
    same = other.model_copy(update={'memory_id':'W2','canonical_value':'Willow review must use Teams only'})
    assert not extractor._relationships(other,[first])
    assert extractor._relationships(same,[first])


def test_project_requirement_does_not_retire_general_preference_even_when_worded_instead_of():
    from app.schemas import RelationshipType
    extractor = RuleBasedMemoryExtractor()
    preference = Memory(memory_id='GO',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='I generally prefer Go for personal tools.')
    requirement = preference.model_copy(update={'memory_id':'TS','canonical_value':'For the Willow project, I must use TypeScript instead of my usual Go preference.'})
    assert [(r.type,r.target_memory_id) for r in extractor._relationships(requirement,[preference])] == [(RelationshipType.CONTEXTUAL_OVERRIDE,'GO')]
    changed = preference.model_copy(update={'memory_id':'RUST','canonical_value':'I now prefer Rust instead of Go for personal tools.'})
    assert any(r.type == RelationshipType.UPDATE for r in extractor._relationships(changed,[preference]))


def test_plural_project_meeting_policies_keep_project_identity_and_are_retained():
    from app.services.memory_entities import named_projects
    extractor=RuleBasedMemoryExtractor()
    for statement in ['All Kestrel meetings must use Zoom only.','All Kestrel meeting reviews must use Zoom only.','The Kestrel deployments must use Zoom only.']:
        assert named_projects(statement)=={'kestrel'}
        assert extractor._is_memory_statement(statement)
    assert named_projects('Project All Labs uses PostgreSQL.')=={'all labs'}
    assert named_projects('All meetings must use Zoom only.')==set()
    assert named_projects('The meetings must use Zoom only.')==set()


def test_plural_meeting_requirements_do_not_create_cross_project_conflicts():
    extractor=RuleBasedMemoryExtractor()
    first=Memory(memory_id='K',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='All Kestrel meetings must use Zoom only.')
    other=first.model_copy(update={'memory_id':'O','canonical_value':'All Oriole meetings must use Teams only.'})
    assert not extractor._relationships(other,[first])


def test_relationship_agent_applies_links_atomically_when_a_later_edge_is_invalid():
    from datetime import datetime, timezone
    import pytest
    from app.extraction.llm import PipelineRequestError
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **_kwargs):
            return {"relationships": [
                {
                    "current_memory_id": "M002", "prior_memory_id": "M001", "type": "UPDATE",
                    "current_evidence_message_ids": ["PILOT002"],
                    "prior_evidence_message_ids": ["PILOT001"], "confidence": 0.9,
                    "rationale": "The second statement supersedes the first.",
                },
                {
                    "current_memory_id": "M004", "prior_memory_id": "M003", "type": "CONTEXTUAL_OVERRIDE",
                    "current_evidence_message_ids": ["PILOT004"],
                    "prior_evidence_message_ids": ["PILOT001"], "confidence": 0.9,
                    "rationale": "This proposed link cites an unrelated source.",
                },
            ]}

    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id=f"PILOT00{index}", role="user", content=f"Source {index}", timestamp=now)
        for index in range(1, 5)
    ])
    memories = [
        Memory(memory_id=f"M00{index}", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value=f"Fact {index}", source_message_ids=[f"PILOT00{index}"])
        for index in range(1, 5)
    ]
    agent = RelationshipAnalysisAgent(ReplyClient())

    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)

    assert agent.last_observation["status"] == "failed"
    assert all(memory.relationships == [] for memory in memories)


def test_relationship_agent_requires_evidence_from_both_endpoints():
    from datetime import datetime, timezone
    import pytest
    from app.extraction.llm import PipelineRequestError
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **_kwargs):
            return {"relationships": [{
                "current_memory_id": "M002", "prior_memory_id": "M001", "type": "UPDATE",
                "current_evidence_message_ids": ["PILOT002"],
                "prior_evidence_message_ids": ["PILOT002"], "confidence": 0.9,
                "rationale": "Only the new fact is cited.",
            }]}

    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id="PILOT001", role="user", content="Old fact", timestamp=now),
        ConversationMessage(message_id="PILOT002", role="user", content="New fact", timestamp=now),
    ])
    memories = [
        Memory(memory_id="M001", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="Old fact", source_message_ids=["PILOT001"]),
        Memory(memory_id="M002", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="New fact", source_message_ids=["PILOT002"]),
    ]

    agent = RelationshipAnalysisAgent(ReplyClient())
    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)
    assert all(memory.relationships == [] for memory in memories)
    assert agent.last_observation["error_code"] == "endpoint_evidence_mismatch"
    assert agent.last_observation['error_diagnostics'] == {
        'validation_errors': [{'field': 'relationships.0.prior_evidence_message_ids',
                               'type': 'endpoint_evidence_mismatch', 'invalid_reference_count': 1}],
        'error_count': 1,
    }
    assert 'PILOT002' not in str(agent.last_observation['error_diagnostics'])


def test_relationship_agent_accepts_separate_evidence_from_both_endpoints():
    from datetime import datetime, timezone, timedelta
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **_kwargs):
            return {"relationships": [{
                "current_memory_id": "M002", "prior_memory_id": "M001", "type": "UPDATE",
                "current_evidence_message_ids": ["PILOT002"],
                "prior_evidence_message_ids": ["PILOT001"], "confidence": 0.9,
                "rationale": "The later database fact replaces the earlier one.",
            }]}

    now = datetime.now(timezone.utc)
    prior_time = now
    current_time = now + timedelta(minutes=1)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id="PILOT001", role="user", content="Old database fact", timestamp=prior_time),
        ConversationMessage(message_id="PILOT002", role="user", content="New database fact", timestamp=current_time),
    ])
    memories = [
        Memory(memory_id="M001", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="The database used an earlier system.", source_message_ids=["PILOT001"], timestamp=prior_time),
        Memory(memory_id="M002", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="The database now uses a replacement system.", source_message_ids=["PILOT002"], timestamp=current_time),
    ]

    result = RelationshipAnalysisAgent(ReplyClient()).analyze(conversation, memories)

    assert result["relationships"][0]["evidence_message_ids"] == ["PILOT001", "PILOT002"]
    assert memories[1].relationships[0].target_memory_id == "M001"
    assert memories[1].relationships[0].evidence_message_ids == ["PILOT001", "PILOT002"]


def test_relationship_agent_prompt_requires_exhaustive_pairs_and_defines_direction():
    from datetime import datetime, timezone
    import json
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **kwargs):
            self.kwargs = kwargs
            return {"relationships": []}

    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id=f"PAIR00{index}", role="user", content=f"Evidence {index}", timestamp=now)
        for index in range(1, 4)
    ])
    memories = [
        Memory(memory_id=f"M00{index}", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value=f"Fact {index}", source_message_ids=[f"PAIR00{index}"])
        for index in range(1, 4)
    ]
    client = ReplyClient()

    result = RelationshipAnalysisAgent(client).analyze(conversation, memories)

    payload = json.loads(client.kwargs["prompt"].split("\n\n", 1)[1])
    assert payload["candidate_pairs_to_assess"] == [
        {"memory_id_a": "M001", "memory_id_b": "M002"},
        {"memory_id_a": "M001", "memory_id_b": "M003"},
        {"memory_id_a": "M002", "memory_id_b": "M003"},
    ]
    assert "Assess every unordered pair" in client.kwargs["instructions"]
    assert "current_memory_id is the newer/current fact" in client.kwargs["instructions"]
    assert "current_memory_id is the narrow, scoped requirement" in client.kwargs["instructions"]
    assert "without repeating or restating that preference" in client.kwargs["instructions"]
    assert "this field order does not imply priority or supersession" in client.kwargs["instructions"]
    assert "every unordered pair in candidate_pairs_to_assess" in client.kwargs["prompt"]
    assert client.kwargs["prompt_template_version"] == "relationship-analysis-agent-v7"
    assert client.kwargs["max_output_tokens"] == 896
    assert result == {"relationships": []}


def test_relationship_output_budget_scales_with_pairs_and_has_a_hard_cap():
    from app.extraction.relationship_agent import _relationship_output_token_budget

    assert _relationship_output_token_budget(0) == 512
    assert _relationship_output_token_budget(2) == 640
    # Eight candidates produce 28 possible relationships; the former
    # memory-count budget allowed only 768 tokens for that full edge list.
    assert _relationship_output_token_budget(8) == 4096
    assert _relationship_output_token_budget(30) == 4096


def test_relationship_agent_rejects_edges_between_different_recognized_topics_atomically():
    from datetime import datetime, timezone
    import pytest
    from app.extraction.llm import PipelineRequestError
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **_kwargs):
            return {"relationships": [{
                "current_memory_id": "M002", "prior_memory_id": "M001", "type": "CONFLICT",
                "current_evidence_message_ids": ["TOPIC002"],
                "prior_evidence_message_ids": ["TOPIC001"], "confidence": 1.0,
                "rationale": "These claims have unrelated memory topics.",
            }]}

    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id="TOPIC001", role="user", content="I live in Adelaide.", timestamp=now),
        ConversationMessage(message_id="TOPIC002", role="user", content="The Maple backend uses PostgreSQL.", timestamp=now),
    ])
    memories = [
        Memory(memory_id="M001", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="I live in Adelaide.", source_message_ids=["TOPIC001"], timestamp=now),
        Memory(memory_id="M002", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="The Maple backend uses PostgreSQL.", source_message_ids=["TOPIC002"], timestamp=now),
    ]
    agent = RelationshipAnalysisAgent(ReplyClient())

    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)

    assert agent.last_observation["error_code"] == "topic_mismatch"
    diagnostics=agent.last_observation['error_diagnostics']
    assert diagnostics['validation_errors'][0]['field']=='relationships.0'
    assert diagnostics['validation_errors'][0]['current_topic']=='database'
    assert diagnostics['validation_errors'][0]['prior_topic']=='location'
    assert 'Adelaide' not in str(diagnostics) and 'PostgreSQL' not in str(diagnostics)
    assert all(memory.relationships == [] for memory in memories)


def test_relationship_agent_rejects_current_endpoint_earlier_than_prior_atomically():
    from datetime import datetime, timezone, timedelta
    import pytest
    from app.extraction.llm import PipelineRequestError
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation, ConversationMessage

    class ReplyClient:
        provider = "ollama"
        model = "qwen3:1.7b"
        last_execution = None

        def complete_json(self, **_kwargs):
            return {"relationships": [{
                "current_memory_id": "M001", "prior_memory_id": "M002", "type": "UPDATE",
                "current_evidence_message_ids": ["ORDER001"],
                "prior_evidence_message_ids": ["ORDER002"], "confidence": 1.0,
                "rationale": "The alleged current fact is earlier in source time.",
            }]}

    prior_time = datetime.now(timezone.utc)
    current_time = prior_time + timedelta(minutes=1)
    conversation = Conversation(conversation_id="C", created_at=prior_time, authorised=True, messages=[
        ConversationMessage(message_id="ORDER001", role="user", content="The database used MySQL.", timestamp=prior_time),
        ConversationMessage(message_id="ORDER002", role="user", content="The database now uses PostgreSQL.", timestamp=current_time),
    ])
    memories = [
        Memory(memory_id="M001", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="The database used MySQL.", source_message_ids=["ORDER001"], timestamp=prior_time),
        Memory(memory_id="M002", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="The database now uses PostgreSQL.", source_message_ids=["ORDER002"], timestamp=current_time),
    ]
    agent = RelationshipAnalysisAgent(ReplyClient())

    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)

    assert agent.last_observation["error_code"] == "temporal_direction_mismatch"
    assert all(memory.relationships == [] for memory in memories)


def test_relationship_agent_timestamp_gate_skips_incomparable_naive_and_aware_times():
    from datetime import datetime, timezone
    from app.extraction.relationship_agent import _timestamp_precedes

    assert _timestamp_precedes(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2)) is False
    assert _timestamp_precedes(datetime(2026, 1, 1), datetime(2026, 1, 2)) is True
