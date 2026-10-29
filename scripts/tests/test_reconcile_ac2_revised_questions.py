import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.reconcile_ac2_revised_questions import reconcile


class RevisedReviewTest(unittest.TestCase):
    def test_blank_and_divergent_reviews_are_not_adjudicated(self):
        directory = Path(__file__).resolve().parents[2] / 'output/proposal-delivery/ac2-revised-question-review-2026-10-28/templates'
        templates = [directory / f'reviewer-{n}.json' for n in (1, 2)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            returns = [root / f'return-{n}.json' for n in (1, 2)]
            first = json.loads(templates[0].read_text())
            second = json.loads(templates[1].read_text())
            first['items'][0]['review']['question_validity'] = 'valid'
            second['items'][0]['review']['question_validity'] = 'invalid'
            returns[0].write_text(json.dumps(first))
            returns[1].write_text(json.dumps(second))
            result = reconcile(templates, returns, root / 'result.json')
            self.assertEqual(result['items'][0]['fields']['question_validity']['status'], 'disagree')
            self.assertEqual(result['items'][0]['fields']['expected_behavior_supported']['status'], 'unresolved')
            self.assertIsNone(result['items'][0]['adjudicated_decision'])
            with self.assertRaises(FileExistsError):
                reconcile(templates, returns, root / 'result.json')

    def test_source_tampering_rejected(self):
        directory = Path(__file__).resolve().parents[2] / 'output/proposal-delivery/ac2-revised-question-review-2026-10-28/templates'
        templates = [directory / f'reviewer-{n}.json' for n in (1, 2)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            returns = [root / f'return-{n}.json' for n in (1, 2)]
            for source, dest in zip(templates, returns):
                dest.write_bytes(source.read_bytes())
            altered = json.loads(returns[0].read_text())
            altered['items'][0]['revised_question'] += ' changed'
            returns[0].write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                reconcile(templates, returns, root / 'result.json')
            self.assertFalse((root / 'result.json').exists())

    def test_template_tampering_rejected_by_manifest(self):
        directory = Path(__file__).resolve().parents[2] / 'output/proposal-delivery/ac2-revised-question-review-2026-10-28'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates = [root / f'reviewer-{n}.json' for n in (1, 2)]
            returns = [root / f'return-{n}.json' for n in (1, 2)]
            for number in (1, 2):
                source = directory / f'templates/reviewer-{number}.json'
                templates[number - 1].write_bytes(source.read_bytes())
                returns[number - 1].write_bytes(source.read_bytes())
            altered = json.loads(templates[0].read_text())
            altered['items'][0]['revised_question'] += ' changed'
            templates[0].write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'manifest'):
                reconcile(templates, returns, root / 'result.json', directory / 'template-manifest.json')
            self.assertFalse((root / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
