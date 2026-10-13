from app.services.location_facts import location_value
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.memory_agent.store import infer_target_memory_scope
from app.schemas import Memory, MemoryStatus, TargetMemoryScope


def test_personal_city_has_explicit_topic_required_value_and_leakage_guard():
    for city in ["Warrnambool", "Port Lincoln"]:
        fact = f"{city} is my current city."
        assert location_value(fact) == city
        assert RuleBasedMemoryExtractor._category(fact) == "location"
        assert RuleBasedTestGenerator._topic(Memory(memory_id="M", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value=fact)) == "location"
        assert infer_target_memory_scope(fact) == TargetMemoryScope.PROFILE
        assert RuleBasedBehaviourEvaluator._required_terms(f"State the recorded fact: {fact}") == city.lower().split()
        assert RuleBasedTestQualityValidator._answer_leaked(fact, f"Does the user live in {city}?")
        assert not RuleBasedTestQualityValidator._answer_leaked(fact, "Where is the user based now?")
    assert location_value("The city project uses MongoDB.") is None
    assert location_value("My current city is unknown.") is None


def test_explicit_current_city_updates_prior_personal_location():
    from app.schemas import RelationshipType
    old = Memory(memory_id="OLD", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="I live in Tamworth.")
    new = Memory(memory_id="NEW", conversation_id="C", status=MemoryStatus.CONFIRMED, canonical_value="Port Lincoln is my current city.")
    relationships = RuleBasedMemoryExtractor()._relationships(new, [old])
    assert [(r.type, r.target_memory_id) for r in relationships] == [(RelationshipType.UPDATE, "OLD")]
