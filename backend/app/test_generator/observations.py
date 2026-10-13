"""Record local checks without equating them with independent test validity."""
from app.test_generator.quality import RuleBasedTestQualityValidator


def observe_candidates(tests, memories):
    validator=RuleBasedTestQualityValidator()
    checks=[validator.validate(test,memories) for test in tests]
    return {'schema_valid':True,'candidate_count':len(tests),
        'local_accepted':sum(check.quality_status.value=='accepted' for check in checks),
        'leaked_candidates':sum(any(validator._answer_leaked(memory.canonical_value,test.prompt) for memory in memories) for test in tests),
        'validator_version':validator.VERSION}
