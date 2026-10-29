import hashlib
import io
import json
import unittest
import zipfile
from scripts.ac3_retest_snapshot_verify import formal_signature,verify_snapshot


def archive(suffix=''):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('app/evaluator/rule_based.py','synthetic evaluator'+suffix)
        z.writestr('app/schemas/domain.py','synthetic schema')
        z.writestr('requirements.txt','synthetic==1')
        z.writestr('dependencies.lock.json',json.dumps({'python_version':'3.12','distributions':[{'name':'synthetic','version':'1','installed_files_sha256':'a'*64}]}))
    return buf.getvalue()


class SnapshotTests(unittest.TestCase):
    def test_isolated_app_hash_and_tampering(self):
        a=archive(); info=formal_signature(a)
        self.assertFalse(info['lock_installation_verified'])
        verify_snapshot(a,info['app_source_sha256'],info['archive_sha256'],info['dependencies_lock_sha256'])
        with self.assertRaises(ValueError):
            verify_snapshot(archive(' modified'),info['app_source_sha256'],info['archive_sha256'],info['dependencies_lock_sha256'])

    def test_reject_invalid_lock(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('app/evaluator/rule_based.py','x');z.writestr('requirements.txt','x');z.writestr('dependencies.lock.json','{}')
        with self.assertRaises(ValueError):formal_signature(buf.getvalue())
