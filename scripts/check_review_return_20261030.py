"""Check returned review JSON against the frozen three-part blank packet.

This only checks contents and counts. Human participation, independence and
exposure are not inferred from JSON fields and require user confirmation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/full-project-backup-20261029/blind-review-packet-20261030.zip'
GROUPS = {'01-AC2题目': (24, ('source_support', 'question_clarity', 'reference_answer_correctness', 'overall'), ('valid', 'invalid', 'uncertain'), 'notes'),
          '02-B已有案例回答': (18, ('verdict',), ('pass', 'fail', 'uncertain'), 'note'),
          '03-B新案例回答': (16, ('verdict',), ('pass', 'fail', 'uncertain'), 'note')}


def read_object(z, name):
    value = json.loads(z.read(name))
    if not isinstance(value, dict):
        raise ValueError(f'{name}: expected a JSON object')
    return value


def validate(packet_path, returned_path):
    rows = {}
    with ZipFile(packet_path) as original, ZipFile(returned_path) as returned:
        names = returned.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Returned ZIP contains duplicate paths')
        for group, (count, fields, choices, note) in GROUPS.items():
            reviewed = []
            for slot in (1, 2):
                suffix = f'{group}/reviewer-{slot}.json'
                matches = [name for name in names if name == suffix or name.endswith('/' + suffix)]
                if len(matches) != 1:
                    raise ValueError(f'{suffix}: expected exactly one file, found {len(matches)}')
                blank, actual = read_object(original, suffix), read_object(returned, matches[0])
                if blank.get('format') != actual.get('format'):
                    raise ValueError(f'{suffix}: format changed')
                for binding in ('source_ledger_sha256', 'ledger_sha256', 'reviewer_id'):
                    if binding in blank and actual.get(binding) != blank[binding]:
                        raise ValueError(f'{suffix}: {binding} changed')
                frozen = {item['review_item_id']: item for item in blank['items']}
                actual_items = actual.get('items', [])
                ids = [item.get('review_item_id') for item in actual_items]
                if len(frozen) != count or len(ids) != count or len(set(ids)) != count or set(ids) != set(frozen):
                    raise ValueError(f'{suffix}: incomplete, duplicate, or unexpected item IDs')
                for item in actual_items:
                    before = frozen[item['review_item_id']]
                    if {k: v for k, v in item.items() if k != 'review'} != {k: v for k, v in before.items() if k != 'review'}:
                        raise ValueError(f"{suffix}: source or answer changed for {item['review_item_id']}")
                    review = item.get('review', {})
                    if any(review.get(field) not in choices for field in fields):
                        raise ValueError(f"{suffix}: missing or invalid judgment for {item['review_item_id']}")
                    if not isinstance(review.get(note), str) or not review[note].strip():
                        raise ValueError(f"{suffix}: missing explanation for {item['review_item_id']}")
                reviewed.append({item['review_item_id']: item['review'] for item in actual_items})
            field = 'overall' if group == '01-AC2题目' else 'verdict'
            counts = {'agreement': 0, 'disagreement': 0, 'uncertain': 0}
            for ident in reviewed[0]:
                left, right = reviewed[0][ident][field], reviewed[1][ident][field]
                if left == 'uncertain' or right == 'uncertain':
                    counts['uncertain'] += 1
                elif left == right:
                    counts['agreement'] += 1
                else:
                    counts['disagreement'] += 1
            rows[group] = {'items': count, **counts}
    return {'packet_sha256': hashlib.sha256(packet_path.read_bytes()).hexdigest(),
            'returned_zip_sha256': hashlib.sha256(returned_path.read_bytes()).hexdigest(),
            'groups': rows, 'review_provenance': 'Not inferred; record user confirmation separately.',
            'limitations': 'This verifies packet content and overall verdict counts, not semantic correctness or reviewer independence.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('returned_zip', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(PACKET, args.returned_zip), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
