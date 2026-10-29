"""Current generator with location-subject protection; v38 remains frozen."""
from app.services.location_subject_v1 import classify_location_subject
from app.test_generator.quality_filtered import QualityFilteredRuleBasedTestGenerator as V38Generator


class LocationScopedRuleBasedTestGenerator(V38Generator):
    VERSION = 'rule-based-v39'

    @staticmethod
    def _topic(*memories):
        topic = V38Generator._topic(*memories)
        if topic != 'location':
            return topic
        subjects = [classify_location_subject(memory.canonical_value) for memory in memories]
        if subjects and all(subject == 'user_residence' for subject in subjects):
            return 'location'
        if subjects and all(subject == 'user_work' for subject in subjects):
            return 'working arrangement'
        if subjects and all(subject in {'other', 'user_work'} for subject in subjects):
            return 'stored information'
        # Keep an ambiguous location probe available for explicit source
        # review. The API guard marks it pending before it can be executed.
        return 'location'
