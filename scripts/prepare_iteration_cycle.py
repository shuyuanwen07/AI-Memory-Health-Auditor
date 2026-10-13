"""Freeze one black-box Qwen repair cycle; never train or change model weights."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['extraction/rule_based.py', 'memory_agent/store.py', 'target_systems/controlled.py',
         'target_ai/providers.py', 'target_ai/rule_based.py', 'evaluator/rule_based.py',
         'services/memory_grounding.py', 'evaluator/llm_judge.py', 'test_generator/quality.py']
if (ROOT / 'backend/app/services/memory_entities.py').exists():
    FILES.append('services/memory_entities.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, required=True)
    parser.add_argument('--change', required=True)
    parser.add_argument('--kind', choices=['auditor', 'target', 'validation'], required=True)
    args = parser.parse_args()
    if not 1 <= args.cycle <= 14:
        parser.error('cycle must be 1..14; 11 is reserved-source validation, 12..14 are Auditor checks')
    base = json.loads((ROOT / 'datasets/studies/independent-repair-v1/study.json').read_text())
    count = 4 if args.cycle == 11 else 1
    scenes = []
    # Entire new histories are reserved per cycle. Categories/templates are
    # familiar; this is synthetic iterative validation, not independent human data.
    for i in range(count):
        scene = json.loads(json.dumps(base['scenarios'][(args.cycle - 1 + i) % 4]))
        original = ['Alder', 'Birch', 'Cedar', 'Delta'][(args.cycle - 1 + i) % 4]
        replacement = f'Cycle{args.cycle}Project{i+1}'
        raw = json.dumps(scene).replace(original, replacement).replace('Maple', f'Distractor{args.cycle}')
        scene = json.loads(raw)
        scene['conversation_id'] = f'CYCLE-{args.cycle}-{i+1}'
        scene['novelty']['used_for_policy_tuning'] = False
        scenes.append(scene)
    digest = hashlib.sha256(b''.join((ROOT / 'backend/app' / f).read_bytes() for f in FILES)).hexdigest()
    import sys
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    base.update(protocol_id=f'ten-cycle-{args.cycle:02d}', scenarios=scenes,
        strategies=['strong_rule_based', 'strong_score_based', 'scope_aware'],
        repetitions={'diagnostic': 0, 'held_out': 3 if args.cycle == 11 else 2},
        evaluator_model=RuleBasedBehaviourEvaluator.VERSION,
        expected_implementation_fingerprint_sha256=digest,
        iteration_change=args.change, iteration_kind=args.kind,
        notice='Synthetic black-box Qwen API iteration. Model weights unchanged. Known task templates with new source histories; evaluator changes are not target improvements. Each cycle is frozen before execution; final cycle uses reserved source histories. Human validation pending.')
    data = ROOT / f'datasets/studies/ten-cycle-{args.cycle:02d}'
    output = ROOT / f'output/ten-cycle-{args.cycle:02d}'
    if data.exists() or output.exists():
        raise SystemExit('Cycle already exists. Resume its frozen study instead of replacing it.')
    data.mkdir(parents=True)
    output.mkdir(parents=True)
    source = data / 'study.json'
    source.write_text(json.dumps(base, ensure_ascii=False, indent=2) + '\n')
    for f in FILES:
        destination = output / 'implementation' / f
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'backend/app' / f, destination)
    (output / 'freeze.json').write_text(json.dumps({
        'cycle': args.cycle, 'change': args.change, 'kind': args.kind,
        'dataset_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'implementation_sha256': digest, 'model': 'qwen3:1.7b',
        'training': False, 'calls_planned': count * 3 * base['repetitions']['held_out'] * 4,
    }, indent=2) + '\n')
    print(f'Frozen cycle {args.cycle}: {args.change}')


if __name__ == '__main__':
    main()
