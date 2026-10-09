from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.services.memory_topics import is_language_topic
from app.schemas import Memory
import pytest


@pytest.mark.parametrize('text', ['I prefer Ruby.', 'The Lantern assignment requires Go.', 'I favour using Go.', 'Our task requires Scala.', 'I use PHP.', 'For the current assignment, Go is required.'])
def test_language_topic_is_shared_between_relationships_and_questions(text):
    assert RuleBasedMemoryExtractor._category(text) == 'programming-language'
    assert RuleBasedTestGenerator._topic(Memory(memory_id='M',conversation_id='C',status='confirmed',canonical_value=text)) == 'programming-language choice'


@pytest.mark.parametrize('text', ['I prefer to go to the office.', 'We need to go to Townsville.', 'The Go project uses SQLite.', 'Permission to go is required.'])
def test_go_travel_and_project_names_are_not_languages(text):
    assert not is_language_topic(text)


def test_target_store_uses_language_and_movement_topics_without_gold_answers():
    from app.memory_agent.store import _category
    assert _category('The Lantern assignment requires Go.') == 'programming-language'
    assert _category('I prefer Ruby.') == 'programming-language'
    assert _category('I moved to Townsville.') == 'location'
    assert _category('I relocated to Port Lincoln.') == 'location'


def test_hyphenated_target_question_topic_still_filters_other_requirements():
    assert is_language_topic('For the current programming-language choice, which requirement applies now?')


def test_moved_location_is_profile_and_location_prompts_match_without_city_leakage():
    from app.memory_agent.store import _category, infer_target_memory_scope
    from app.schemas import TargetMemoryScope
    assert infer_target_memory_scope('I moved to Port Lincoln.') == TargetMemoryScope.PROFILE
    assert _category('Where is the user based now?') == 'location'
    assert _category('The earlier and later memories about location conflict.') == 'location'
