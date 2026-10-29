import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.check_review_return_20261030 import GROUPS, validate


def completed_packet(packet, destination, *, tamper=False, omit=False, wrong_binding=False):
    with ZipFile(packet) as source, ZipFile(destination, 'w', ZIP_DEFLATED) as out:
        for group, (_, fields, choices, note) in GROUPS.items():
            for slot in (1, 2):
                name = f'{group}/reviewer-{slot}.json'
                value = json.loads(source.read(name))
                for item in value['items']:
                    for field in fields:
                        item['review'][field] = choices[0]
                    item['review'][note] = 'Checked against the cited source.'
                if tamper and group == '01-AC2题目' and slot == 1:
                    value['items'][0]['question'] = 'Altered question'
                if omit and group == '03-B新案例回答' and slot == 2:
                    value['items'].pop()
                if wrong_binding and group == '01-AC2题目' and slot == 1:
                    value['source_ledger_sha256'] = 'wrong-ledger'
                out.writestr(name, json.dumps(value, ensure_ascii=False))


def test_complete_return_and_tamper_detection(tmp_path):
    packet = tmp_path / 'blank.zip'
    with ZipFile(packet, 'w', ZIP_DEFLATED) as out:
        for group, (count, fields, _, note) in GROUPS.items():
            for slot in (1, 2):
                items = [{'review_item_id': str(i), 'question': f'Question {i}',
                          'review': {**{field: '' for field in fields}, note: ''}}
                         for i in range(count)]
                out.writestr(f'{group}/reviewer-{slot}.json', json.dumps({'format': 'test-packet', 'source_ledger_sha256': 'frozen-ledger', 'items': items}))
    returned = tmp_path / 'return.zip'
    completed_packet(packet, returned)
    result = validate(packet, returned)
    assert [value['agreement'] for value in result['groups'].values()] == [24, 18, 16]
    completed_packet(packet, returned, tamper=True)
    with pytest.raises(ValueError, match='source or answer changed'):
        validate(packet, returned)
    completed_packet(packet, returned, omit=True)
    with pytest.raises(ValueError, match='incomplete'):
        validate(packet, returned)
    completed_packet(packet, returned, wrong_binding=True)
    with pytest.raises(ValueError, match='source_ledger_sha256 changed'):
        validate(packet, returned)
