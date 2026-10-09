from datetime import datetime, timezone
import pytest
from app.schemas import TargetResponse, TestCase as Case
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator

@pytest.mark.parametrize('expected,answer,passed', [
 ('PostgreSQL.', 'PostgreSQL is not MySQL.', True),
 ('PostgreSQL.', 'PostgreSQL is not wrong.', True),
 ('PostgreSQL.', 'PostgreSQL is not the correct answer.', False),
 ('PostgreSQL.', 'Do not use PostgreSQL.', False),
 ('PostgreSQL.', 'Use PostgreSQL, not MySQL.', True),
 ('PostgreSQL.', 'PostgreSQL is not required.', False),
 ('PostgreSQL.', 'PostgreSQL is wrong.', False),
 ('PostgreSQL.', 'PostgreSQL is not incorrect.', True),
 ('I generally prefer Go.', 'Go is not Python.', True),
 ('I generally prefer Go.', 'Go is incorrect.', False),
 ('I generally prefer Go.', 'I do not prefer Go.', False),
 ('Acknowledge the conflict and request clarification.', 'There is no contradiction. Ask for clarification.', False),
 ('Acknowledge the conflict and request clarification.', 'The policies conflict. No clarification is needed.', False),
 ('Acknowledge the conflict and request clarification.', 'There is no disagreement. Request clarification.', False),
 ('Acknowledge the conflict and request clarification.', 'The policies conflict, but clarification is not required.', False),
 ('Acknowledge the conflict and request clarification.', 'The policies conflict. There is no need to clarify.', False),
 ('Acknowledge the conflict and request clarification.', 'The policies disagree. Please clarify which policy applies.', True),
 ('Acknowledge the conflict and request clarification.', 'The policies conflict; do not choose either. Request clarification.', True),
])
def test_known_language_variants(expected, answer, passed):
    case = Case(test_id='TV', run_id='RUN', dimension='accuracy', prompt='Which answer?', expected_behavior=expected,
        supporting_memory_ids=[], generator_version='language-variants')
    response = TargetResponse(response_id='RV', test_id='TV', run_id='RUN', response_text=answer,
        model='fixed-fixture', temperature=0, created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, [])
    assert result.passed is passed, result.reason
