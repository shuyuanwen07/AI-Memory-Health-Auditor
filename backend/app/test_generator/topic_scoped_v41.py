"""Conservative source-subject and topic improvements over the frozen v40 rules."""
import re
from app.schemas import Dimension, TestType
from app.services.location_subject_v1 import classify_location_subject
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator


class TopicScopedRuleBasedTestGenerator(ConflictAwareRuleBasedTestGenerator):
    VERSION = 'rule-based-v41'

    @staticmethod
    def _topic(*memories):
        topic = ConflictAwareRuleBasedTestGenerator._topic(*memories)
        text = ' '.join(m.canonical_value for m in memories)
        # A delivery window is a time interval, not a Windows operating system.
        if re.search(r'\bdeliver(?:y|ies)\b',text,re.I) and re.search(r'\b(?:window|am|pm)\b',text,re.I):
            return 'delivery window'
        if topic not in {'stored information', 'preference', 'current task'}:
            return topic
        # Broad categories only: never place an answer value into the prompt.
        categories = [
            (r'\b(?:participants?|attendees?|enrollees?)\b', 'participant count'),
            (r'\b(?:scheduled|schedule|scheduling|rescheduled|timetable)\b', 'schedule'),
            (r'\b(?:watering|irrigation)\b', 'watering schedule'),
            (r'\b(?:meeting|meetings)\b', 'meeting arrangement'),
            (r'\b(?:notifications?|notify|notified)\b', 'notification method'),
            (r'\b(?:allocations?|allocated|assigns?|assigned)\b', 'resource allocation'),
            (r'\b(?:deliver(?:y|ies)|shipping)\b', 'delivery arrangement'),
            (r'\b(?:handouts?|leaflets?|brochures?)\b', 'handout format'),
            (r'\b(?:volunteers?|volunteering)\b', 'volunteer arrangement'),
        ]
        return next((label for pattern,label in categories if re.search(pattern,text,re.I)), topic)

    @staticmethod
    def third_party_location_subject(memory):
        fact=memory.canonical_value.strip()
        # Recognise only a bounded, affirmative third-person subject. Unknown,
        # reported, negated, compound or first-person subjects retain the
        # existing guard and are never guessed to be the user.
        match=re.fullmatch(r'(the\s+[A-Za-z][A-Za-z -]{0,55}?)\s+is\s+based\s+in\s+([A-Za-z][A-Za-z .\'-]{0,60})[.!?]?',fact,re.I)
        if match and classify_location_subject(fact) != 'user_residence':
            subject=match.group(1)
            location=match.group(2).strip().rstrip('.!?')
            if (len(subject.split()) <= 7 and not re.search(r'\b(?:and|or|not|only|current|former)\b',subject,re.I)
                    and not re.search(r'(?<!\w)'+re.escape(location)+r'(?!\w)',subject,re.I)):
                return subject.lower()
        return None

    @classmethod
    def _accuracy(cls, memory):
        subject=cls.third_party_location_subject(memory)
        if subject:
            return (Dimension.ACCURACY, f'Where is {subject} based?',
                    f'State the recorded fact: {memory.canonical_value.strip().rstrip(".!?")}.', [memory.memory_id], TestType.DIRECT)
        return super()._accuracy(memory)
