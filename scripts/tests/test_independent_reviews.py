import copy
import unittest

from scripts.analyse_independent_reviews import analyse


class IndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.reference = {'material_sha256': 'frozen', 'material': {
            'histories': [], 'ordinary_answers': [{'answer': 'recorded'}], 'official_answers': []}}
        self.review = {'schema': 'three-independent-review-worksheet-v1', 'reviewer': 'A',
            **copy.deepcopy(self.reference), 'provenance': {'human_confirmed': False},
            'labels': {'ordinary-correct-0': True, 'ordinary-valid-0': True,
                'ordinary-reference-0': True, 'ordinary-dimension-0': 'other', 'ordinary-note-0': 'Source evidence.'}}

    def test_ai_draft_keeps_provenance_and_cannot_become_human_gold(self):
        report = analyse(self.reference, [self.review])
        self.assertFalse(report['formal_human_validation_ready'])
        self.assertFalse(report['reviews'][0]['declared_provenance']['human_confirmed'])
        self.assertEqual(report['reviews'][0]['filled_fields'], 5)

    def test_material_tampering_is_rejected_even_when_declared_hash_matches(self):
        self.review['material']['ordinary_answers'][0]['answer'] = 'changed'
        with self.assertRaises(ValueError):
            analyse(self.reference, [self.review])

    def test_disagreement_is_retained_without_majority_gold(self):
        other = copy.deepcopy(self.review)
        other['reviewer'] = 'C'
        other['labels']['ordinary-correct-0'] = 'uncertain'
        report = analyse(self.reference, [self.review, other])
        self.assertEqual(report['disagreements'][0]['values'], {'A': True, 'C': 'uncertain'})
        self.assertFalse(report['formal_human_validation_ready'])

    def test_missing_fields_remain_missing(self):
        del self.review['labels']['ordinary-correct-0']
        report = analyse(self.reference, [self.review])
        self.assertIn('ordinary-correct-0', report['reviews'][0]['missing_fields'])

    def test_integer_is_not_a_boolean_label(self):
        self.review['labels']['ordinary-correct-0'] = 1
        with self.assertRaises(ValueError):
            analyse(self.reference, [self.review])

    def test_duplicate_reviewer_cannot_count_as_independent(self):
        with self.assertRaises(ValueError):
            analyse(self.reference, [self.review, copy.deepcopy(self.review)])

    def test_reviewer_spacing_and_case_cannot_create_another_person(self):
        other = copy.deepcopy(self.review)
        other['reviewer'] = ' a '
        with self.assertRaises(ValueError):
            analyse(self.reference, [self.review, other])

    def test_whitespace_note_is_missing_without_rewriting_original(self):
        self.review['labels']['ordinary-note-0'] = ' \n\t '
        report = analyse(self.reference, [self.review])
        self.assertEqual(report['reviews'][0]['filled_fields'], 4)
        self.assertIn('ordinary-note-0', report['reviews'][0]['missing_fields'])
        self.assertEqual(self.review['labels']['ordinary-note-0'], ' \n\t ')

    def test_no_returns_cannot_produce_a_review_report(self):
        with self.assertRaises(ValueError):
            analyse(self.reference, [])

    def test_blank_decision_is_missing_and_not_a_disagreement(self):
        other = copy.deepcopy(self.review)
        other['reviewer'] = 'C'
        other['labels']['ordinary-correct-0'] = '  '
        report = analyse(self.reference, [self.review, other])
        self.assertIn('ordinary-correct-0', report['reviews'][1]['missing_fields'])
        self.assertEqual(report['disagreements'], [])
