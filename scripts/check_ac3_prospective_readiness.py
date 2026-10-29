"""Check AC3 input grounding returns offline; never run a model or freeze a protocol."""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-1', type=Path, required=True)
    parser.add_argument('--review-2', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=PACKET / 'candidate-inputs.json')
    parser.add_argument('--composite-manifest', type=Path)
    parser.add_argument('--expanded-manifest', type=Path, help='Source-bound old-eight plus independently reviewed new-22 evidence.')
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        raise ValueError('Source must be a regular non-symlink file.')
    raw = args.source.read_bytes()
    if args.composite_manifest and args.expanded_manifest:
        raise ValueError('Use exactly one source-review manifest format.')
    if raw != (PACKET / 'candidate-inputs.json').read_bytes() and args.composite_manifest is None and args.expanded_manifest is None:
        raise ValueError('Revised-source composite evidence is required.')
    if args.composite_manifest is not None:
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_conflict_delta_reviews import verify_manifest
        verify_manifest(args.composite_manifest, raw, [args.review_1.read_bytes(), args.review_2.read_bytes()])
    if args.expanded_manifest is not None:
        sys.path.insert(0, str(ROOT))
        from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
        verify_expanded_manifest(args.expanded_manifest, raw, [args.review_1.read_bytes(), args.review_2.read_bytes()])
    source = json.loads(raw)
    expected = {q['test_id']: (c, q) for c in source['cases'] for q in c['tests']}
    required_histories, required_questions = (30, 120) if args.expanded_manifest else (8, 32)
    if len(expected) != required_questions or len(source['cases']) != required_histories:
        raise ValueError('Unexpected candidate input set.')
    results = []
    for slot, path in enumerate((args.review_1, args.review_2), 1):
        data = json.loads(path.read_text())
        if data['format'] != 'ac3-prospective-grounding-review-v1' or data['input_sha256'] != digest(raw) or data['reviewer_slot'] != slot:
            raise ValueError(f'Reviewer {slot} does not match this packet.')
        seen = {}
        for case in data['cases']:
            for question in case['questions']:
                test_id = question['test_id']
                if test_id not in expected or test_id in seen:
                    raise ValueError('Review includes an unknown or duplicate question.')
                original_case, original_question = expected[test_id]
                copy = {key: value for key, value in question.items() if key != 'review'}
                if copy != original_question or case['history_id'] != original_case['history_id'] or case['source_messages'] != original_case['source_messages']:
                    raise ValueError('Question or source material changed in the review file.')
                label = question['review']['question_validity']
                if label not in {'valid', 'invalid', 'uncertain', None}:
                    raise ValueError('Allowed labels are valid, invalid, uncertain or null.')
                if label is not None and (not isinstance(question['review'].get('rationale'), str) or not question['review']['rationale'].strip()):
                    raise ValueError('A completed grounding judgment requires a source-based rationale.')
                seen[test_id] = label
        if set(seen) != set(expected):
            raise ValueError('Review is missing questions.')
        declaration = data['reviewer_declaration']
        label = declaration.get('reviewer_label')
        normalized = unicodedata.normalize('NFKC', label).strip().casefold() if isinstance(label, str) else ''
        declared = bool(normalized) and declaration.get('completed_by_human') is True and declaration.get('completed_independently') is True and isinstance(declaration.get('used_ai_assistance'), bool)
        results.append({'labels': seen, 'declaration_complete': declared, 'reviewer_label': normalized})
    agreement = sum(results[0]['labels'][key] == results[1]['labels'][key] == 'valid' for key in expected)
    disagreement = sum(a != b and a is not None and b is not None for a, b in ((results[0]['labels'][key], results[1]['labels'][key]) for key in expected))
    incomplete = sum(None in (results[0]['labels'][key], results[1]['labels'][key]) or 'uncertain' in (results[0]['labels'][key], results[1]['labels'][key]) for key in expected)
    distinct_labels = bool(results[0]['reviewer_label'] and results[1]['reviewer_label'] and results[0]['reviewer_label'] != results[1]['reviewer_label'])
    print(json.dumps({'format': 'ac3-grounding-readiness-check-v1', 'input_sha256': digest(raw), 'histories': len(source['cases']), 'questions': len(expected), 'both_valid': agreement, 'disagreed': disagreement, 'missing_or_uncertain': incomplete, 'declarations_complete': [r['declaration_complete'] for r in results], 'reviewer_labels_distinct': distinct_labels, 'identity_independently_authenticated': False, 'grounding_ready_for_adjudication': all(r['declaration_complete'] for r in results) and distinct_labels and not disagreement and not incomplete, 'protocol_frozen': False, 'run_authorised': False, 'next': 'Check invalid items and adjudicate; freeze eligible pilot thresholds and complete protocol before any held-out output. This check does not freeze or run anything.'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
