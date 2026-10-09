"""Paired probes test recall versus task use without exposing answer values."""
import hashlib
import re
from app.schemas import AuditRun, Dimension, Memory, TestCase, TestType
from app.services.interfaces import TestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator


class PairedContextualTestGenerator(TestGenerator):
    VERSION = "paired-contextual-v5"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        # A complete pair needs two calls. Odd budgets intentionally leave one
        # call unused instead of overstating paired coverage.
        base = RuleBasedTestGenerator().generate(memories, audit.model_copy(update={"test_budget": audit.test_budget}))
        by_id = {memory.memory_id: memory for memory in memories}
        result = []
        seen = set()
        for case in base:
            family = tuple(sorted(case.supporting_memory_ids))
            if family in seen or len(result)+2 > audit.test_budget:
                continue
            seen.add(family)
            supporting = [by_id[key] for key in case.supporting_memory_ids if key in by_id]
            topic = RuleBasedTestGenerator._scoped_topic(*supporting)
            identity = hashlib.sha256((case.dimension.value + ":" + ":".join(case.supporting_memory_ids)).encode()).hexdigest()[:16]
            intent = "the current task requirement" if case.dimension == Dimension.APPROPRIATE_USE else "the current state"
            direct = case.prompt if case.dimension == Dimension.ACCURACY else f"For {intent}, what is the applicable {topic}? If the recorded constraints remain unresolved, identify them and say clarification is needed."
            task = f"You are preparing the user's next practical task involving {topic}. State the concrete setting or requirement you will use in the task. If the records are unresolved, pause and ask for clarification instead of selecting one."
            if case.dimension == Dimension.APPROPRIATE_USE:
                task = f"Prepare the user's current assignment or project task involving {topic}. State the concrete requirement that applies to this task, preserving task-specific requirements over general preferences. If constraints remain unresolved, ask for clarification."
            if case.dimension == Dimension.ACCURACY:
                preference = any(re.search(r"\b(?:prefer|preference|favour|favorite|favourite)\b", memory.canonical_value, re.I) for memory in supporting)
                task = f"Prepare a factual {'project summary' if 'project' in topic else 'user profile'}. Include the remembered {'general preference for ' if preference else ''}{topic} as a concrete fact."
            if case.dimension == Dimension.ACCURACY and any(re.search(r"\b(?:requires?|required|must|mandatory)\b", memory.canonical_value, re.I) for memory in supporting):
                task = f"Prepare the user's current task using the recorded requirement about {topic}. State the concrete requirement, without substituting a general preference."
            for variant, prompt, kind in (("direct", direct, TestType.DIRECT), ("task", task, TestType.INDIRECT)):
                if len(result) >= audit.test_budget:
                    break
                result.append(case.model_copy(update={"test_id": f"T{len(result)+1:03d}", "prompt": prompt,
                                                      "generator_version": self.VERSION, "test_type": kind,
                                                      "probe_group_id": identity, "probe_variant": variant,
                                                      "target_memory_context": []}))
        return result
