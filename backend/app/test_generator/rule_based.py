"""Deterministic behavioural test generation from confirmed ground truth."""
from __future__ import annotations

import re
from app.services.location_facts import location_value
from app.services.deployment_facts import deployment_region_value
from app.services.meeting_facts import is_meeting_platform_topic, equivalent_exclusive_platform_rules

from app.schemas import AuditRun, Dimension, Memory, RelationshipType, TestCase, TestType
from app.services.memory_topics import is_language_topic
from app.services.interfaces import TestGenerator
from app.services.memory_entities import named_projects
from app.test_generator.quality import RuleBasedTestQualityValidator


class RuleBasedTestGenerator(TestGenerator):
    """Generate traceable tests without leaking a canonical value into prompts.

    The evaluator-facing ``expected_behavior`` keeps the canonical value. The
    target-facing prompt asks only about an abstract topic, so a passing model
    must rely on its controlled memory rather than copy an answer from a prompt.
    """

    # Changed prompt wording is a protocol change; retain a distinct version
    # so pre-change and post-change runs are never compared as one template.
    VERSION = "rule-based-v36"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        by_id = {memory.memory_id: memory for memory in memories}
        candidates: list[tuple[Dimension, str, str, list[str], TestType]] = []
        for memory in memories:
            for relationship in memory.relationships:
                prior = by_id.get(relationship.target_memory_id)
                if prior is None:
                    continue
                if relationship.type == RelationshipType.UPDATE:
                    candidates.extend((self._freshness(memory, prior), self._update_conflict_resolution(memory, prior)))
                elif relationship.type == RelationshipType.CONFLICT:
                    candidates.append(self._explicit_conflict_resolution(memory, prior))
                elif relationship.type == RelationshipType.CONTEXTUAL_OVERRIDE:
                    disputed = [other for other in memories if any(
                        r.type == RelationshipType.CONFLICT and (r.target_memory_id == memory.memory_id or
                        (other.memory_id == memory.memory_id and r.target_memory_id in by_id)) for r in other.relationships)]
                    candidate = self._appropriate_use(memory, prior)
                    if disputed:
                        dimension, prompt, _, evidence, kind = candidate
                        candidate = (dimension, prompt + " If the task requirements themselves remain contradictory, identify both and request clarification instead of selecting one.",
                            "Identify both conflicting recorded constraints, acknowledge the conflict and request clarification before relying on either record.",
                            list(dict.fromkeys(evidence + [other.memory_id for other in disputed])), kind)
                    candidates.append(candidate)

        superseded = {relationship.target_memory_id for memory in memories for relationship in memory.relationships if relationship.type == RelationshipType.UPDATE}
        unresolved = {memory.memory_id for memory in memories if any(r.type == RelationshipType.CONFLICT for r in memory.relationships)}
        unresolved.update(r.target_memory_id for memory in memories for r in memory.relationships if r.type == RelationshipType.CONFLICT)
        for memory in memories:
            if memory.memory_id not in unresolved and memory.memory_id not in superseded:
                # An unresolved-reference status is context for a conflict,
                # not a standalone scalar answer for an accuracy probe.
                if re.search(r"\bnot established which\b", memory.canonical_value, re.I):
                    continue
                candidates.append(self._accuracy(memory))

        # An actual unresolved contradiction is the primary conflict probe;
        # a resolved update is a useful secondary probe only after coverage.
        candidates.sort(key=lambda candidate: 0 if candidate[0] == Dimension.CONFLICT_RESOLUTION
                        and any(r.type == RelationshipType.CONFLICT for mid in candidate[3] for r in by_id[mid].relationships) else 1)
        unique = self._deduplicate(self._balanced_order(candidates), by_id)
        # Several distinct memories can map to the same broad topic prompt.
        # Drop duplicate wording before applying the budget so a repeated
        # candidate never blocks the whole suite at the final quality gate.
        distinct: list[tuple[Dimension, str, str, list[str], TestType]] = []
        seen_prompts: set[str] = set()
        for candidate in unique:
            prompt_key = RuleBasedTestQualityValidator.normalize_prompt(candidate[1])
            if not prompt_key or prompt_key in seen_prompts:
                continue
            seen_prompts.add(prompt_key)
            distinct.append(candidate)
        return [TestCase(test_id=f"T{index:03d}", run_id=audit.run_id, dimension=dimension,
                         prompt=prompt, expected_behavior=expected, supporting_memory_ids=memory_ids,
                         generator_version=self.VERSION, test_type=test_type,
                         target_memory_context=[by_id[memory_id].canonical_value for memory_id in memory_ids])
                for index, (dimension, prompt, expected, memory_ids, test_type) in enumerate(distinct[:audit.test_budget], start=1)]

    @classmethod
    def _accuracy(cls, memory: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        topic = cls._topic(memory)
        scheduled = re.fullmatch(r"(?P<event>[A-Za-z][A-Za-z0-9 '\-]{0,100}?)\s+(?:is|was)\s+scheduled\s+for\s+\d{4}-\d{2}-\d{2}", memory.canonical_value.rstrip('.!?'), re.I)
        if scheduled:
            # The event identifies what to recall; its date stays private in
            # expected_behavior. Do not substitute receipt-time metadata.
            event = re.sub(r"^the\s+", "", scheduled.group('event'), flags=re.I)
            prompt = f"What date is recorded for the {event}? State the recorded date only."
        elif re.fullmatch(r"I met .+? on .+", memory.canonical_value.rstrip('.!?'), re.I):
            prompt = "Who did the user meet, and when? State the person and recorded date."
        elif topic == "programming-language choice" and re.search(r"\b(?:prefers?|preferences?|favours?|favorite|favourite)\b", memory.canonical_value, re.I):
            prompt = "What programming language does the user generally prefer? State the language only."
        elif topic == "database technology" and any(r.type == RelationshipType.UPDATE for r in memory.relationships):
            prompt = f"What is the user's current {cls._scoped_topic(memory)} now? State the current value only."
        elif re.search(r"\b(?:requires?|required|must|mandatory)\b", memory.canonical_value, re.I):
            prompt = f"For the current task, what is the recorded requirement about {cls._scoped_topic(memory)}? State the relevant requirement only."
        elif topic == "unadopted project recommendation":
            prompt = "Which project recommendation has the user not adopted? State that it remains a suggestion, not an accepted requirement."
        elif topic == "suggestion handling rule":
            prompt = "How should the assistant treat a project suggestion the user has not adopted? State the recorded rule."
        elif topic == "stored information" and cls._source_subject(memory):
            prompt = f"What is recorded about {cls._source_subject(memory)}? State the relevant fact only."
        else:
            prompt = f"What is the user's recorded {cls._scoped_topic(memory)}? State the relevant fact only."
        return (Dimension.ACCURACY, prompt,
                f"State the recorded fact: {memory.canonical_value.rstrip('.!?')}.", [memory.memory_id], TestType.DIRECT)

    @classmethod
    def _freshness(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.FRESHNESS,
                ("Where is the user based now? State the location first, then explain in one short sentence how the recorded current state replaces the historical state. Use only the stated evidence; do not invent a reason for the change." if cls._topic(current, prior) == "location" else f"Which {cls._scoped_topic(current, prior)} should the user use now? State the concrete value first, then explain in one short sentence how the recorded current state replaces the historical state. Use only the stated evidence; do not invent a reason for the change."),
                f"Use the recorded current value and explain the replacement of the historical fact ({prior.canonical_value.rstrip('.!?')}); do not invent a cause: {current.canonical_value.rstrip('.!?')}.", [prior.memory_id, current.memory_id], TestType.CONTEXTUAL)

    @classmethod
    def _update_conflict_resolution(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.CONFLICT_RESOLUTION,
                f"The recorded {cls._scoped_topic(current, prior)} has an explicit update. Which concrete value applies now? State it first, then explain how the stated update replaces the historical value. Do not assume separate source messages or invent a reason for the change.",
                f"Explain the explicit update of the historical fact ({prior.canonical_value.rstrip('.!?')}) to the stated current value; this is resolved replacement, not an unresolved conflict: {current.canonical_value.rstrip('.!?')}.", [prior.memory_id, current.memory_id], TestType.INDIRECT)

    @classmethod
    def _explicit_conflict_resolution(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.CONFLICT_RESOLUTION,
                f"Two recorded constraints about the user's {cls._scoped_topic(current, prior)} conflict. What should be clarified before acting?",
                (f"Keep both records visible: {prior.canonical_value.rstrip('.!?')}; {current.canonical_value.rstrip('.!?')}. "
                 "The conflict relation does not establish which one controls, so ask the user for clarification before acting."),
                [prior.memory_id, current.memory_id], TestType.INDIRECT)

    @classmethod
    def _appropriate_use(cls, contextual: Memory, preference: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.APPROPRIATE_USE,
                f"For {cls._scoped_topic(contextual, preference)}, how should its task-specific requirement relate to the user's general preference?",
                (f"Within this scope, follow the task-specific requirement ({contextual.canonical_value.rstrip('.!?')}); "
                 f"elsewhere, retain the general preference ({preference.canonical_value.rstrip('.!?')}). "
                 "Do not treat the scoped override as replacing the general preference."),
                [preference.memory_id, contextual.memory_id], TestType.PARAPHRASED)

    @staticmethod
    def _deduplicate(candidates: list[tuple[Dimension, str, str, list[str], TestType]], memories: dict[str, Memory] | None = None) -> list[tuple[Dimension, str, str, list[str], TestType]]:
        unique: list[tuple[Dimension, str, str, list[str], TestType]] = []
        seen: set[tuple[Dimension, tuple[str, ...]]] = set()
        for candidate in candidates:
            if memories and candidate[0] == Dimension.ACCURACY and len(candidate[3]) == 1:
                fact = memories[candidate[3][0]].canonical_value
                equivalent = next((index for index, prior in enumerate(unique)
                    if prior[0] == Dimension.ACCURACY and prior[1] == candidate[1]
                    and all(equivalent_exclusive_platform_rules(fact, memories[mid].canonical_value) for mid in prior[3])), None)
                if equivalent is not None:
                    prior = unique[equivalent]
                    unique[equivalent] = (prior[0], prior[1], prior[2], list(dict.fromkeys(prior[3]+candidate[3])), prior[4])
                    continue
            # Relationship rows can be recorded from either endpoint. Their
            # order does not create a second evidence slot for the same pair.
            key = (candidate[0], tuple(sorted(candidate[3])))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique

    @staticmethod
    def _balanced_order(candidates: list[tuple[Dimension, str, str, list[str], TestType]]) -> list[tuple[Dimension, str, str, list[str], TestType]]:
        """Round-robin dimensions, preserving coverage whenever the budget allows."""
        groups = {dimension: [item for item in candidates if item[0] == dimension] for dimension in Dimension}
        result: list[tuple[Dimension, str, str, list[str], TestType]] = []
        while any(groups.values()):
            for dimension in Dimension:
                if groups[dimension]:
                    result.append(groups[dimension].pop(0))
        return result

    @staticmethod
    def _source_subject(memory: Memory) -> str | None:
        # Use only a bounded noun subject preceding a finite predicate. Do not
        # copy the predicate, whose content may contain the answer. Unknown
        # structures retain the original quality-gated generic fallback.
        match = re.match(r"^\s*(the [A-Za-z][A-Za-z -]{0,60}?)\s+(?:is|was|has|have|uses|contains)\b", memory.canonical_value, re.I)
        if not match:
            return None
        subject = match.group(1).strip()
        if len(subject.split()) > 7 or re.search(r"\b(?:and|or|because|but|not|only|approved|permitted|prohibited|required|preferred|final|current)\b", subject, re.I):
            return None
        # A repeated subject token in the predicate may itself be the answer.
        predicate = memory.canonical_value[match.end():].lower()
        words = [word.lower() for word in re.findall(r"[A-Za-z]+", subject) if len(word) >= 4]
        if any(re.search(r"\b" + re.escape(word) + r"\b", predicate) for word in words):
            return None
        return subject

    @staticmethod
    def _anchor_safe(anchor: str, memories: tuple[Memory, ...], pattern: str) -> bool:
        # Remove each explicit scope phrase; a repeated anchor elsewhere may be
        # the value to recall. Abstain instead of putting it in the prompt.
        for memory in memories:
            residual = re.sub(pattern, " ", memory.canonical_value, flags=re.I)
            terms = [part for part in re.findall(r"[A-Za-z0-9-]+", anchor)
                     if part.lower() not in {"the", "and", "of", "for"}]
            if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", residual, re.I) for term in terms):
                return False
        return True

    @classmethod
    def _scoped_topic(cls, *memories: Memory) -> str:
        topic = cls._topic(*memories)
        projects_by_memory = [{name.lower() for name in named_projects(memory.canonical_value)} for memory in memories]
        projects = set.intersection(*projects_by_memory) if projects_by_memory and all(projects_by_memory) else set()
        if len(projects) == 1:
            name = next(iter(projects))
            project_phrase = (r"\b(?:the\s+)?" + re.escape(name) +
                              r"\s+(?:projects?|reviews?|meetings?|backends?|frontends?|deployments?|logs|logging|services?)\b")
            if cls._anchor_safe(name, memories, project_phrase):
                return f"{topic} for the {name.title()} project"
        # Require the exact same explicit label in every evidence endpoint.
        scenarios = [re.match(r"^In the ([A-Za-z][A-Za-z -]{0,55}) scenario:", memory.canonical_value, re.I) for memory in memories]
        if len(scenarios) > 1 and all(scenarios):
            labels = {m.group(1).strip().lower() for m in scenarios}
            if len(labels) == 1 and len(next(iter(labels)).split()) <= 6 and topic == "stored information":
                label = next(iter(labels))
                pattern = r"^In the " + re.escape(label) + r" scenario:"
                if cls._anchor_safe(label, memories, pattern):
                    return f"records for the {label} scenario"
        event_matches = [list(re.finditer(r"\bfor the ([A-Za-z][A-Za-z0-9-]*) event\b", memory.canonical_value, re.I)) for memory in memories]
        if topic == "event venue" and all(len(matches) == 1 for matches in event_matches):
            labels = {matches[0].group(1).lower() for matches in event_matches}
            if len(labels) == 1:
                event = next(iter(labels))
                pattern = r"\bfor the " + re.escape(event) + r" event\b"
                if cls._anchor_safe(event, memories, pattern):
                    return f"event venue for the {event.title()} event"
        return topic

    @staticmethod
    def _topic(*memories: Memory) -> str:
        text = " ".join(memory.canonical_value.lower() for memory in memories)
        # Name the subject before falling back to broad requirement wording.
        # In particular, API keys may be an authentication method rather than
        # a secret-storage requirement, and dates may describe a delivery
        # deadline rather than generic stored information.
        if re.search(r"\b(?:client[- ]facing|client)\s+(?:integration\s+)?(?:authentication|auth)\b|\b(?:oauth|api keys?)\b", text): return "client authentication method"
        if re.search(r"\bcourse coordinator\b", text) and re.search(r"\b(?:hear from|waiting for|expect(?:ing)? an update)\b", text): return "course-coordinator follow-up"
        if re.search(r"\b(?:review session|interface review|usability review)\b", text): return "interface review plan"
        if re.search(r"\b(?:separate software projects|project names? attached|requirements are not interchangeable)\b", text): return "project separation rule"
        if re.search(r"\bnot adopted\b.*\bsuggestion\b", text): return "unadopted project recommendation"
        if re.search(r"\bdo not treat\b.*\bsuggestion\b.*\bimplementation plan\b", text): return "suggestion handling rule"
        if re.search(r"\b(?:secret|secrets|credential|credentials?)\s+(?:storage|handling|management)\b|\b(?:store|stores|storing)\s+(?:the\s+)?(?:secret|credential)", text): return "credential storage"
        if re.search(r"\b(?:secrets?|credentials?)\b", text) and re.search(r"\b(?:environment variables?|configuration files?|config files?)\b", text): return "deployment secret storage"
        if re.search(r"\b(?:secrets?|credential|credentials)\b", text): return "deployment credential handling"
        if deployment_region_value(" ".join(memory.canonical_value for memory in memories)): return "deployment region"
        if re.search(r"\bdeployment\b", text): return "deployment configuration"
        if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|redis|mariadb|cassandra|dynamodb|database|sql)\b", text): return "database technology"
        if is_language_topic(text): return "programming-language choice"
        if re.search(r"\bstorage location\b", text): return "storage location"
        if re.search(r"\b(?:venue|site plan|signed booking)\b", text): return "event venue"
        if location_value(text) or re.search(r"\b(?:sydney|melbourne|london)\b", text): return "location"
        if re.search(r"\bcoordinating projects\b", text): return "project coordination method"
        if is_meeting_platform_topic(text): return "meeting platform"
        if re.search(r"\b(?:deadline|due date|delivery date|submission date)\b", text): return "delivery deadline"
        if re.search(r"\b(?:diet|dietary|vegetarian|vegan|gluten[- ]free|food restriction)\b", text): return "dietary preference"
        if re.search(r"\b(?:accessibility|accessible|keyboard[- ]only|keyboard navigation|screen reader|wcag)\b", text): return "accessibility requirement"
        if re.search(r"\b(?:project name|renamed|previously named|current name)\b", text): return "project name"
        if re.search(r"\b(?:meeting|appointment|stand-?up)\b", text) and re.search(r"\b(?:start|begin|schedule|time|at)\b", text): return "meeting schedule"
        if re.search(r"\b(?:report|reports)\b", text) and re.search(r"\b(?:sent|send|deliver|schedule|day|monday|tuesday|wednesday|thursday|friday)\b", text): return "report schedule"
        if re.search(r"\b(?:operating system|laptop|ubuntu|fedora|windows|macos|linux)\b", text): return "operating system"
        if re.search(r"\b(?:communication|summaries|summary)\b", text): return "communication style"
        if re.search(r"\b(?:remote|from home|office|hybrid)\b", text): return "working arrangement"
        if re.search(r"\b(?:assignment|project|task|require|must|need|mandatory)\b", text): return "current task"
        if re.search(r"\b(?:prefers?|preferences?|favours?|favorite|favourite)\b", text): return "preference"
        return "stored information"
