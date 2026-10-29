import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.ac2_paired_retest_cli import execute, freeze


class PairedCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        contents = {'source': b'{"cases":[{"history_id":"fixture"}]}', 'plan': b'{}',
                    'review1': b'fixture-one', 'review2': b'fixture-two',
                    'archive': Path('/output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6/legacy-app-source-unlocked.zip').read_bytes(),
                    'candidate': Path('/app/app/test_generator/rule_based.py').read_bytes(),
                    'validator': Path('/app/app/test_generator/quality.py').read_bytes()}
        values = {}
        for name, content in contents.items():
            path = root / name
            path.write_bytes(content)
            values[name] = str(path)
        values.update(protocol=str(root/'protocol.json'), output=str(root/'output.json'), started=str(root/'started.json'))
        self.args = SimpleNamespace(**values)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    @patch('scripts.ac2_paired_retest_cli.source_code_sha', return_value='a'*64)
    def test_no_overwrite_and_started_marker_retained(self, _runtime, _review):
        self.args.output, destination = self.args.protocol, self.args.output
        freeze(self.args)
        self.args.output = destination
        with patch('scripts.ac2_paired_retest_cli.subprocess.run', return_value=SimpleNamespace(returncode=1, stderr='fixture')):
            with self.assertRaises(RuntimeError):
                execute(self.args)
        self.assertTrue(Path(self.args.started).exists())
        with self.assertRaises(FileExistsError):
            execute(self.args)
        self.assertFalse(Path(self.args.output).exists())

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    @patch('scripts.ac2_paired_retest_cli.source_code_sha', return_value='a'*64)
    def test_changed_review_is_rejected_before_start(self, _runtime, _review):
        self.args.output, destination = self.args.protocol, self.args.output
        freeze(self.args)
        self.args.output = destination
        Path(self.args.review1).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            execute(self.args)
        self.assertFalse(Path(self.args.started).exists())


if __name__ == '__main__':
    unittest.main()
