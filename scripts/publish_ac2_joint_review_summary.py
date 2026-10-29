"""Publish aggregate-only, user-confirmed joint AC2 review results."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / 'output/proposal-delivery/ac1-ac2-ai-review-intake-2026-10-28'
intake_path = base / 'new-submitted-drafts-intake.json'
confirmation_path = base / 'new-submitted-human-confirmation.json'
original_update_path = base / 'original-label-update-user-confirmation.json'
intake, confirmation = (json.loads(path.read_text()) for path in (intake_path, confirmation_path))
assert intake['format'] == 'submitted-ac1-ac2-draft-intake-v1'
assert confirmation['format'] == 'ac1-ac2-new-review-human-confirmation-v1'
assert confirmation['user_statement'] == '两份均已人工核对 审核者1和2都参与了'
assert set(confirmation['file_sha256'].values()) == set(intake['attachment_sha256'])
assert intake['matching_revised_ids_and_source_material'] == 13
assert intake['reported_second_file_counts'] == {'revised_questions': 13, 'valid_field_judgments': 39}
original_update = json.loads(original_update_path.read_text())
assert original_update['user_statement'] == '采用新判断：6 valid、7 invalid'
assert original_update['attachment_sha256'] in intake['attachment_sha256']
assert intake['reported_first_file_counts']['question_valid'] == 6 and intake['reported_first_file_counts']['question_invalid'] == 7
result = {'format': 'ac2-joint-review-summary-v1', 'revised_questions': 13, 'valid_judgments': 39,
          'judgments_per_question': 3, 'user_confirmed_human_review': True, 'both_reviewers_participated': True,
          'independent_separate_label_sets_established': False, 'ai_assisted': True,
          'original_question_adjudication': {'valid': 6, 'invalid': 7, 'previous_judgment': 'uncertain', 'retrospective': True},
          'historical_original_data_modified': False,
          'source_sha256': {'intake': hashlib.sha256(intake_path.read_bytes()).hexdigest(),
                            'confirmation': hashlib.sha256(confirmation_path.read_bytes()).hexdigest(),
                            'original_update_confirmation': hashlib.sha256(original_update_path.read_bytes()).hexdigest()}}
(root / 'frontend/public/reports/ac2-joint-review-summary-v1.json').write_text(json.dumps(result, indent=2) + '\n')
print('Published source-bound joint review summary')
