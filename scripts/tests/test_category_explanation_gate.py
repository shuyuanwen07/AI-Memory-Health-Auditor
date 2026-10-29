import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'backend/app/evaluator/category_explanation_gate.py'
spec = importlib.util.spec_from_file_location('category_explanation_gate', path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class CategoryExplanationGateTest(unittest.TestCase):
    def test_retains_explanations_that_support_the_proposed_type(self):
        self.assertEqual(gate.supported_category('accuracy', 'The response makes an unsupported factual claim.'), 'accuracy')
        self.assertEqual(gate.supported_category('freshness', 'It used an outdated source after a newer update.'), 'freshness')
        self.assertEqual(gate.supported_category('conflict_resolution', 'Two active records conflict and the answer picks one.'), 'conflict_resolution')
        self.assertEqual(gate.supported_category('appropriate_use', 'A task-specific requirement overrides the general preference.'), 'appropriate_use')

    def test_withholds_vague_or_multi_category_explanations_without_changing_label(self):
        self.assertIsNone(gate.supported_category('appropriate_use', 'The response failed to use relevant confirmed memory.'))
        self.assertIsNone(gate.supported_category('accuracy', 'The response invents a different issue while missing the unresolved conflict.'))
        self.assertIsNone(gate.supported_category('freshness', 'The response omitted information.'))
        self.assertIsNone(gate.supported_category(None, 'unsupported claim'))
        self.assertIsNone(gate.supported_category('accuracy', ''))


if __name__ == '__main__':
    unittest.main()
