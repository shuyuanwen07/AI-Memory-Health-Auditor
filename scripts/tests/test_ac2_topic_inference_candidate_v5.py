from scripts.ac2_topic_inference_candidate_v5_20261030 import TopicInferenceCandidateV5
from scripts.tests.test_ac2_topic_inference_candidate_v4 import audit, memory


def test_distinct_lens_references_are_not_silently_collapsed():
    g = TopicInferenceCandidateV5()
    tests = g.generate([memory('1','For the architecture assignment only, use the 35 mm lens.'),
                        memory('2','For the architecture assignment only, use the 50 mm lens.')], audit())
    assert not any('Which lens is specified' in t.prompt for t in tests)
    assert g._ambiguous_accuracy_count == 2


def test_single_question_retains_scope_and_clears_run_state():
    g = TopicInferenceCandidateV5()
    tests = g.generate([memory('1','For the architecture assignment only, use the 35 mm lens.')], audit())
    assert any('Which lens is specified' in t.prompt for t in tests)
    assert g._validation_memories is None and g._ambiguous_accuracy_count == 0
