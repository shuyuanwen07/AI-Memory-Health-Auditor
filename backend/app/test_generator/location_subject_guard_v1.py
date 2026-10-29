"""Advisory guard for questions that assert a user's residential location."""
import re

from app.schemas import GroundingStatus, TestQualityAssessment, TestQualityStatus
from app.services.location_subject_v1 import classify_location_subject

VERSION = 'location-subject-guard-v1'
_USER_LOCATION = re.compile(
    r'\bwhere\s+(?:does|did|is|was|has|have)\s+the user\s+(?:(?:currently|now|previously|recently|ever)\s+)*(?:live|living|lived|move|moving|moved|relocate|relocated|based|located)\b'
    r'|\bthe user(?:[\'’]s)?\s+(?:current\s+|recorded\s+|home\s+|residential\s+)*(?:city|location|residence)\b'
    r'|\b(?:what|which)\s+(?:city|place|location)\b[^?!.]{0,60}\bthe user\b'
    r'|\b(?:city|location|residence)\s+of\s+the\s+user\b', re.I)


def location_subject_advice(test, memories):
    """Return an additional quality assessment or None.

    Only the referenced confirmed memories can support a user's location.
    A missing subject is pending, not a finding that the question is false.
    """
    if not _USER_LOCATION.search(test.prompt):
        return None
    by_id = {memory.memory_id: memory for memory in memories}
    support = [by_id.get(mid) for mid in test.supporting_memory_ids]
    if not support or any(memory is None for memory in support):
        return None  # The existing quality validator rejects missing evidence.
    subjects = [classify_location_subject(memory.canonical_value) for memory in support]
    if all(subject in {'other', 'user_work'} for subject in subjects):
        return TestQualityAssessment(quality_status=TestQualityStatus.REJECTED,
            grounding_status=GroundingStatus.GROUNDED,
            reason='The cited evidence describes another actor or a work location, not the user\'s residence.',
            validator_version=VERSION)
    if any(subject != 'user_residence' for subject in subjects):
        return TestQualityAssessment(quality_status=TestQualityStatus.PENDING,
            grounding_status=GroundingStatus.GROUNDED,
            reason='The location subject or scope needs source review before the question is accepted.',
            validator_version=VERSION)
    return None
