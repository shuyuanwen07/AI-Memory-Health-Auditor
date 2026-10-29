import unittest
from scripts.relative_date_review_prototype import relative_date_advice

class RelativeDateReviewTest(unittest.TestCase):
    def test_relative_source_requires_review_even_with_plain_question(self):
        self.assertIn('real-world anchor', relative_date_advice('When is the meeting?', 'At 3 pm.', ['We meet today at 3 pm.']))
    def test_relative_question_or_chinese_source_requires_review(self):
        self.assertIsNotNone(relative_date_advice('What is the plan for tomorrow?', 'A walk.', ['A walk is planned.']))
        self.assertIsNotNone(relative_date_advice('什么时候开会？', '下午三点', ['今天下午三点开会。']))
    def test_absolute_date_does_not_trigger_this_specific_warning(self):
        self.assertIsNone(relative_date_advice('When?', '1 July 2026.', ['The meeting is on 1 July 2026.']))

if __name__ == '__main__':
    unittest.main()
