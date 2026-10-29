import json
from zipfile import ZIP_DEFLATED, ZipFile
import pytest
from scripts.check_ac2_wording_recheck_20261030 import FIELDS, validate


def build_blank(path):
    items = [{'blind_id': str(i), 'question': f'Question {i}',
              'review': {**{field: '' for field in FIELDS}, 'notes': ''}}
             for i in range(10)]
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for i in (1, 2):
            z.writestr(f'reviewer-{i}.json', json.dumps({'format': 'v1', 'source_sha256': 'sha', 'items': items}))


def build_return(packet, path, *, tamper=False):
    with ZipFile(packet) as source, ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for i in (1, 2):
            name = f'reviewer-{i}.json'
            data = json.loads(source.read(name))
            for item in data['items']:
                item['review'].update({**{field: 'valid' for field in FIELDS}, 'notes': 'Source reviewed.'})
            if tamper and i == 1:
                data['items'][0]['question'] = 'changed'
            z.writestr(name, json.dumps(data))


def test_accept_complete_and_reject_changed_content(tmp_path):
    packet, returned = tmp_path / 'blank.zip', tmp_path / 'returned.zip'
    build_blank(packet)
    build_return(packet, returned)
    assert validate(packet, returned)['agreement'] == 10
    build_return(packet, returned, tamper=True)
    with pytest.raises(ValueError, match='source or question changed'):
        validate(packet, returned)
