"""Create blank review material for proposed AC3 source-to-memory mappings.

No application records, model calls, memory confirmations or labels are created.
The mappings mirror the current strict structural verifier and must not be
interpreted as complete or semantically correct memory representations.
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3/candidate-inputs.json'
CONFIRMATION = ROOT / 'output/proposal-delivery/ac3-grounding-human-confirmed-2026-10-28/confirmation-record.json'
DEST = ROOT / 'output/proposal-delivery/ac3-memory-preparation-review-2026-10-28.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(source, confirmation):
    payload, record = json.loads(source), json.loads(confirmation)
    if payload.get('format') != 'ac3-prospective-synthetic-inputs-v1' or record.get('format') != 'ac3-human-grounding-user-confirmation-v1':
        raise ValueError('Unexpected source or confirmation format')
    cases = payload['cases']
    if len(cases) != 8 or sum(len(c['source_messages']) for c in cases) != 40:
        raise ValueError('Unexpected source histories')
    all_ids = set()
    output = []
    for case in cases:
        history, messages, tests = case['history_id'], case['source_messages'], case['tests']
        ids = {m['message_id'] for m in messages}
        if len(ids) != len(messages) or all_ids & ids or not all(set(t['supporting_source_message_ids']) <= ids for t in tests):
            raise ValueError('Duplicate source IDs or unsupported question mapping')
        all_ids |= ids
        memories = []
        for message in messages:
            mid = message['message_id']
            memories.append({'source_message_id': mid, 'source_order': message['order'],
                'source_text': message['text'], 'proposed_verbatim_memory': message['text'],
                'used_by_question_ids': [t['test_id'] for t in tests if mid in t['supporting_source_message_ids']],
                'review': {'decision': None, 'note': ''}})
        output.append({'history_id': history, 'synthetic_source': True, 'proposed_memories': memories,
            'relationship_and_context_review': {'update_between_messages_2_and_3': None,
                'conflicting_venue_facts_in_message_4_representable': None,
                'general_preference_and_exception_in_message_5_representable': None,
                'note': ''}, 'app_mapping': {'conversation_id': None, 'memory_ids_by_source': None}})
    return {'format': 'ac3-memory-preparation-human-review-template-v1',
        'status': 'BLANK TEMPLATE; NO HUMAN REVIEW OR APPLICATION IMPORT YET',
        'source_input_sha256': sha(source), 'question_grounding_confirmation_sha256': sha(confirmation),
        'source_file': str(SOURCE.relative_to(ROOT)),
        'explanation': 'This is a proposed one-verbatim-memory-per-source mapping for the current structural verifier, not an assertion that extraction, update, conflict and scope semantics are correct. Human review must not be inferred from the existing question grounding review.',
        'instructions': ['Review each proposed memory against its exact source. decision: valid, invalid, or uncertain; give reasons for invalid/uncertain.',
            'For each history, assess whether the update, conflict and contextual exception can be represented correctly by the existing memory/relation structure; choose valid, invalid, or uncertain and explain. In particular, message 4 contains two conflicting facts within a single proposed memory and message 5 combines a general preference with a scoped exception.',
            'Keep source IDs and text unchanged. If a different memory representation is needed, record it in the note; the current verifier requires verbatim one-to-one mappings and must be revised and retested before use.',
            'Blank app_mapping fields are for recording verified saved records later, not fictitious IDs. Do not mark memories confirmed in this template.'],
        'reviewer': {'label': None, 'completed_by_human': None, 'note': ''}, 'histories': output}


def main():
    source, confirmation = SOURCE.read_bytes(), CONFIRMATION.read_bytes()
    result = prepare(source, confirmation)
    if SOURCE.read_bytes() != source or CONFIRMATION.read_bytes() != confirmation:
        raise ValueError('Source changed during preparation')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(DEST, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'file': str(DEST), 'histories': len(result['histories']),
        'proposed_memories': sum(len(h['proposed_memories']) for h in result['histories']),
        'reviewed': False, 'imported': False}))


if __name__ == '__main__': main()
