"""Freeze and prepare exploratory A prompts, without human claims or model calls."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AuditRun, Memory, MemoryRelationship
from app.test_generator.baselines import DirectGroundTruthTestGenerator, FixedTemplateTestGenerator, ContextualIndirectTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/experiment-a-diverse-candidate-20261029-v1'
SOURCE = ROOT / 'output/proposal-delivery/ac1-ac2-source-only-2026-10-28-v3/reviewed-source.json'
FILES = ['backend/app/test_generator/baselines.py', 'backend/app/test_generator/rule_based.py',
         'backend/app/test_generator/quality.py', 'backend/app/schemas/domain.py']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def save_new(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')

def freeze():
    source = json.loads(SOURCE.read_bytes())
    histories = source['histories']
    if len(histories) != 30 or len({h['history_id'] for h in histories}) != 30:
        raise ValueError('Expected the complete reviewed source release')
    OUT.mkdir(parents=True, exist_ok=False)
    save_new(OUT / 'protocol.json', {
        'format': 'exploratory-a-diverse-candidate-v1', 'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sha(SOURCE), 'history_ids': [h['history_id'] for h in histories],
        'source_qualifications': source.get('reference_qualifications', []),
        'source_selection': 'All 30 previously reviewed synthetic histories in release order; no outcome selection.',
        'source_prior_exposure': 'Previously used in AC1/AC2 and scorer development; not an independent holdout.',
        'methods': ['direct_ground_truth', 'fixed_template', 'contextual_indirect'],
        'methods_impl': {'direct_ground_truth': DirectGroundTruthTestGenerator.VERSION,
            'fixed_template': FixedTemplateTestGenerator.VERSION, 'contextual_indirect': ContextualIndirectTestGenerator.VERSION},
        'maximum_questions_per_method_history': 4,
        'fairness': 'Same source, target, settings, and maximum budget; preserve unequal counts and reject unfair comparisons.',
        'review': 'Two independent AI reviewers before execution; label as AI, followed by future human review. No simulated human approval.',
        'target': {'provider': 'openrouter', 'model': 'openai/gpt-6-luna', 'temperature': 0,
                   'policy': 'identical target memory configuration across arms; source-grounded memory only'},
        'metrics': 'Question validity and coverage first; later response failure recall and distinct defect discovery only with independently reviewed defect inventory.',
        'defect_inventory': 'Not yet independently reviewed; do not infer known defects or calculate formal failure discovery from potential failure types.',
        'source_hashes': {p: sha(ROOT / p) for p in FILES}, 'preparation_script_sha256': sha(Path(__file__)),
        'status': 'pre-outcome frozen preparation, no target or evaluator calls',
    })

def prepare():
    protocol_path = OUT / 'protocol.json'; protocol = json.loads(protocol_path.read_bytes())
    if sha(SOURCE) != protocol['source_sha256'] or sha(Path(__file__)) != protocol['preparation_script_sha256']:
        raise ValueError('Frozen source or preparation code changed')
    if any(sha(ROOT / p) != value for p, value in protocol['source_hashes'].items()):
        raise ValueError('Generator or validation source changed')
    source = json.loads(SOURCE.read_bytes())
    if [h['history_id'] for h in source['histories']] != protocol['history_ids']:
        raise ValueError('Frozen history selection changed')
    excluded = {(q['history_id'], q.get('fact_id')) for q in protocol['source_qualifications'] if q.get('status') == 'unresolved' and q.get('fact_id')}
    excluded_rel = {(q['history_id'], q.get('memory_id'), q.get('target_memory_id'), q.get('relationship_type'))
                    for q in protocol['source_qualifications'] if q.get('status') == 'unresolved' and q.get('relationship_type')}
    generations = []
    for history in source['histories']:
        hid = history['history_id']; ref = history['reviewed_reference']
        facts = [f for f in ref['facts'] if (hid, f['memory_id']) not in excluded]
        ids = {f['memory_id'] for f in facts}; memories = []
        for fact in facts:
            edges = [MemoryRelationship(type=e['relationship_type'], target_memory_id=e['target_memory_id'],
                       evidence_message_ids=e.get('evidence_message_ids', []))
                     for e in ref['relationships'] if e['memory_id'] == fact['memory_id']
                     and e['target_memory_id'] in ids
                     and (hid, e['memory_id'], e['target_memory_id'], e['relationship_type']) not in excluded_rel]
            memories.append(Memory(memory_id=fact['memory_id'], conversation_id=hid,
                canonical_value=fact['canonical_value'], status='confirmed',
                source_message_ids=[fact['source_message_id']], relationships=edges))
        audit = AuditRun(run_id='A-' + hid, conversation_id=hid, status='CREATED', target_configuration='strong',
                         provider='rule_based', model='rule-based-v2', temperature=0, random_seed=42,
                         test_budget=4, prompt_template_version='rule-based-v4',
                         created_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        arms = {}
        for label, cls in [('direct_ground_truth', DirectGroundTruthTestGenerator),
                           ('fixed_template', FixedTemplateTestGenerator),
                           ('contextual_indirect', ContextualIndirectTestGenerator)]:
            try:
                tests = cls().generate(memories, audit)
                validator = RuleBasedTestQualityValidator()
                items = []
                for test in tests:
                    try: quality = validator.validate(test, memories).model_dump(mode='json')
                    except Exception as exc: quality = {'quality_status': 'pending', 'error_type': type(exc).__name__}
                    items.append({'test': test.model_dump(mode='json'), 'quality': quality})
                arms[label] = {'status': 'generated', 'tests': items, 'unused_capacity': 4 - len(items)}
            except Exception as exc:
                arms[label] = {'status': 'error', 'error_type': type(exc).__name__, 'tests': [], 'unused_capacity': 4}
        generations.append({'history_id': hid, 'source_messages': history['source_messages'], 'reference': ref, 'arms': arms})
    save_new(OUT / 'generated-draft.json', {'format': 'a-diverse-unreviewed-suites-v1',
        'protocol_sha256': sha(protocol_path), 'status': 'AI review needed; zero target or evaluator calls', 'histories': generations})

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'prepare']); a = p.parse_args()
    {'freeze': freeze, 'prepare': prepare}[a.stage]()
