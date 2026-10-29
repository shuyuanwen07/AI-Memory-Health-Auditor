"""Describe adjudicated four-strategy results without treating uncertainty as truth."""
import hashlib
import json
from pathlib import Path


def analyze(raw):
    data = json.loads(raw)
    if (data.get('format') != 'four-strategy-adjudication-intake-v1'
            or data.get('publication_status') != 'user_confirmed_human_adjudication'):
        raise ValueError('A user-confirmed adjudication intake is required')
    expected = {'scope_aware', 'strong_rule_based', 'temporal_importance', 'weak_first_hit'}
    if set(data.get('by_strategy', {})) != expected:
        raise ValueError('Expected the four frozen strategies')
    rows = []
    for strategy, counts in sorted(data['by_strategy'].items()):
        if set(counts) != {'Pass', 'Fail', 'Uncertain'} or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError('Adjudication counts must be nonnegative integers')
        passed, failed, uncertain = counts['Pass'], counts['Fail'], counts['Uncertain']
        total = passed + failed + uncertain
        if total != 90:
            raise ValueError('Each strategy must contain the 90 recorded answers')
        decided = passed + failed
        rows.append({'strategy': strategy, 'pass': passed, 'fail': failed, 'uncertain': uncertain,
                     'total_answers': total, 'decided_pass_rate': passed / decided if decided else None,
                     'all_answer_lower_bound': passed / total,
                     'all_answer_upper_bound': (passed + uncertain) / total})
    if any(sum(row[k] for row in rows) != data['counts'][name]
           for k, name in [('pass', 'Pass'), ('fail', 'Fail'), ('uncertain', 'Uncertain')]):
        raise ValueError('Per-strategy counts do not match the adjudicated total')
    return {'format': 'four-strategy-adjudicated-bounds-v1',
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'strategies': rows,
            'limits_interpretation': 'Bounds place every uncertain answer at either extreme; they are not confidence intervals.',
            'sample_scope': '30 cases, four strategies, three repeated answers per case and strategy; answers sharing a case are dependent.',
            'provenance': 'User confirms human adjudication; original reviewer judgments are preserved separately.',
            'model_called': False}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = analyze(args.input.read_bytes())
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')


if __name__ == '__main__':
    main()
