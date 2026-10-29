"""Validate returned wording rechecks while preserving original judgments."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/full-project-backup-20261029/ac2-wording-recheck-packet-20261030.zip'
FIELDS = ('source_support', 'question_clarity', 'reference_answer_correctness', 'overall')


def validate(packet, returned):
    results = []
    with ZipFile(packet) as blank_zip, ZipFile(returned) as returned_zip:
        names = returned_zip.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP paths')
        for i in (1, 2):
            name = f'reviewer-{i}.json'
            matches = [n for n in names if n == name or n.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError(f'Expected exactly one {name}')
            blank = json.loads(blank_zip.read(name))
            actual = json.loads(returned_zip.read(matches[0]))
            if actual.get('format') != blank['format'] or actual.get('source_sha256') != blank['source_sha256']:
                raise ValueError(f'{name}: source binding changed')
            expected = {row['blind_id']: row for row in blank['items']}
            actual_items = actual.get('items', [])
            ids = [row.get('blind_id') for row in actual_items]
            if len(ids) != 10 or len(set(ids)) != 10 or set(ids) != set(expected):
                raise ValueError(f'{name}: missing or duplicate item')
            for row in actual_items:
                before = expected[row['blind_id']]
                if {k: v for k, v in row.items() if k != 'review'} != {k: v for k, v in before.items() if k != 'review'}:
                    raise ValueError(f"{name}: source or question changed: {row['blind_id']}")
                review = row.get('review', {})
                if any(review.get(field) not in ('valid', 'invalid', 'uncertain') for field in FIELDS):
                    raise ValueError(f"{name}: incomplete judgment: {row['blind_id']}")
                if not isinstance(review.get('notes'), str) or not review['notes'].strip():
                    raise ValueError(f"{name}: missing notes: {row['blind_id']}")
            results.append({row['blind_id']: row['review']['overall'] for row in actual_items})
    counts = {'agreement': 0, 'disagreement': 0, 'uncertain': 0}
    for ident in results[0]:
        a, b = results[0][ident], results[1][ident]
        counts['uncertain' if 'uncertain' in (a, b) else 'agreement' if a == b else 'disagreement'] += 1
    return {'packet_sha256': hashlib.sha256(packet.read_bytes()).hexdigest(),
            'returned_sha256': hashlib.sha256(returned.read_bytes()).hexdigest(),
            'items': 10, **counts,
            'review_provenance': 'Do not infer human participation, independence, or exposure from this check.',
            'limitations': 'Content and counts only; original human judgments are not changed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('returned_zip', type=Path)
    print(json.dumps(validate(PACKET, parser.parse_args().returned_zip), indent=2))
