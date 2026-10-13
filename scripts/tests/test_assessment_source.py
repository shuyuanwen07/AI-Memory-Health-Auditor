import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.package_assessment_source import allowed, package


class AssessmentSourceTests(unittest.TestCase):
    def test_missing_git_still_packages_with_unknown_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('Source distribution\n')
            with patch('scripts.package_assessment_source.subprocess.run', side_effect=FileNotFoundError):
                result = package(root, root / 'output/release')
            self.assertIsNone(result['base_revision'])
            self.assertEqual(result['working_tree_status'], 'unknown')
            self.assertEqual(result['file_count'], 1)

    def test_secret_database_outputs_and_caches_are_excluded(self):
        for name in ('.env', 'backend/.env', 'backend/.env.secret.json', 'output/reviewer.json', 'frontend/public/reports/private.json',
                     'backend/local.db', 'backend/node_modules/demo.py', 'datasets/annotation/private/reviews.json',
                     '../backend/app.py'):
            self.assertFalse(allowed(Path(name)), name)
        self.assertTrue(allowed(Path('.env.example')))
        self.assertTrue(allowed(Path('backend/app/main.py')))

    def test_archive_hashes_contents_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'backend/app').mkdir(parents=True)
            (root/'backend/app/main.py').write_text('print("hello")\n')
            (root/'.env').write_text('PRIVATE=not-for-delivery')
            (root/'backend/app/private.py').symlink_to(root/'.env')
            (root/'backend/app/main.py').chmod(0o755)
            result=package(root,root/'output/release')
            with zipfile.ZipFile(root/'output/release/AI-Memory-Health-Auditor-source.zip') as archive:
                self.assertEqual(set(archive.namelist()),{'backend/app/main.py','ASSESSMENT_SOURCE_MANIFEST.json'})
                self.assertEqual((archive.getinfo('backend/app/main.py').external_attr >> 16) & 0o777,0o755)
                manifest=json.loads(archive.read('ASSESSMENT_SOURCE_MANIFEST.json'))
                self.assertEqual(manifest['files'],result['files'])
            self.assertEqual(package(root,root/'output/release')['archive_sha256'],result['archive_sha256'])
