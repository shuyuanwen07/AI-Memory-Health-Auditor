"""Reproduce post-outcome topic mappings on three previously reviewed cases.

Does not generate questions or change the application or historical studies.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/ac2-topic-inference-diagnostic-20261030.json'


def main():
    sources = [ROOT / f'backend/app/test_generator/{name}.py' for name in
               ('rule_based', 'quality_filtered', 'location_scoped', 'conflict_aware')]
    values = ['I watch films on a laptop.', 'The library is near my office.',
              'For the architecture assignment only, use the 35 mm lens.']
    rows = [{'memory': value, 'inferred_topic': ConflictAwareRuleBasedTestGenerator._topic(SimpleNamespace(canonical_value=value))} for value in values]
    result = {'source_sha256': {str(source.relative_to(ROOT)): hashlib.sha256(source.read_bytes()).hexdigest() for source in sources},
              'generator_version': ConflictAwareRuleBasedTestGenerator.VERSION, 'cases': rows,
              'limitations': 'These cases were selected after inspecting review results. Topic labels are only one part of generation; the diagnostic does not generate questions, estimate prevalence, or establish independent validity.'}
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
