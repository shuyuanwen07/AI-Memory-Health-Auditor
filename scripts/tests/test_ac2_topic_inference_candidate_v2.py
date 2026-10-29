from types import SimpleNamespace
from scripts.ac2_topic_inference_candidate_v2_20261030 import TopicInferenceCandidateV2


def test_explicit_work_location_pair_retains_scope():
    memories = [SimpleNamespace(canonical_value=value) for value in (
        'My regular work location is home instead of the office.',
        'My regular work location is exclusively the office, not home.')]
    assert TopicInferenceCandidateV2._topic(*memories) == 'working arrangement'


def test_office_in_unrelated_statement_is_not_a_work_arrangement():
    memory = SimpleNamespace(canonical_value='The library is near my office.')
    assert TopicInferenceCandidateV2._topic(memory) == 'stored information'
