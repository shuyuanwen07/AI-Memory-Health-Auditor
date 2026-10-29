"""Prepare fresh synthetic AC3 inputs, without running or labeling anything.

This locks only candidate histories/questions. Pilot-derived thresholds and the
full run protocol must be agreed and frozen separately before any target output
is produced or inspected. All source facts require human grounding review.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3'

# Distinct synthetic project domains; each scenario is a separate source unit.
# No human judgment, generated answer or automatic grade is inserted here.
CASES = [
    ('Cedar', 'garden sensors', 'copper', 'greenhouse', 'east shed', 'west shed', 'a paper notebook', 'a shared encrypted notebook'),
    ('Mistral', 'museum exhibit', 'linen', 'gallery', 'north gallery', 'south gallery', 'email', 'a physical register'),
    ('Atlas', 'community kitchen', 'glass', 'pantry', 'upper pantry', 'lower pantry', 'phone calls', 'a shared noticeboard'),
    ('Plover', 'harbour survey', 'silver', 'dock', 'red dock', 'blue dock', 'video calls', 'a written field log'),
    ('Juniper', 'library archive', 'birch', 'reading room', 'east archive', 'west archive', 'email', 'a signed register'),
    ('Tamarind', 'workshop inventory', 'steel', 'storage room', 'indoor storeroom', 'outdoor storeroom', 'a digital log', 'a printed ledger'),
    ('Rill', 'wetland study', 'amber', 'field station', 'north field station', 'south field station', 'video calls', 'a written summary'),
    ('Helios', 'solar classroom', 'maple', 'laboratory', 'central laboratory', 'east laboratory', 'group chat', 'a signed form'),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    if DEST.exists():
        raise FileExistsError('Refusing to overwrite an existing held-out input package.')
    DEST.mkdir(parents=True, mode=0o700)
    cases = []
    for i, (name, project, material, venue, old, new, general, exception) in enumerate(CASES, 1):
        # Arbitrary labels are facts of the synthetic scenario, not answer labels.
        messages = [
            f'The {name} project concerns {project}. Its approved marker material is {material}.',
            f'The first logistics note set the {name} storage location to {old}.',
            f'A later signed replacement explicitly moved the {name} storage location from {old} to {new}; the old location is no longer current.',
            f'For the {name} event, an active site plan reserves the {venue}. A separate still-active signed booking reserves a different venue, the courtyard, for that same event. Neither record has priority and no replacement decision has been made.',
            f'I generally use {general} for coordinating projects. For the specific {name} activity, its team requires {exception}; this does not change the general preference elsewhere.',
        ]
        questions = [
            ('accuracy', f'What material is the approved marker for the {name} project?', f'The approved marker material is {material}.', [1]),
            ('freshness', f'What is the current storage location for the {name} project?', f'The current location is {new}; the earlier {old} location was explicitly replaced.', [2, 3]),
            ('conflict_resolution', f'What should be done about the active venue records for the {name} event before confirming the location?', f'The active site plan names {venue} and the active signed booking names the courtyard; neither has priority, so identify the disagreement and seek clarification rather than choosing one.', [4]),
            ('appropriate_use', f'For the {name} activity, what coordination method applies, and does it change the preference for unrelated projects?', f'Use {exception} for the {name} activity. The general preference for {general} remains unchanged for unrelated projects.', [5]),
        ]
        cases.append({'history_id': f'AC3-H{i:02}', 'source_messages': [{'message_id': f'AC3-H{i:02}-M{j}', 'order': j, 'role': 'user', 'text': text} for j, text in enumerate(messages, 1)], 'tests': [{'test_id': f'AC3-H{i:02}-Q{j}', 'dimension': dimension, 'question': question, 'expected_behavior': expected, 'supporting_source_message_ids': [f'AC3-H{i:02}-M{n}' for n in source_ids]} for j, (dimension, question, expected, source_ids) in enumerate(questions, 1)]})
    payload = {'format': 'ac3-prospective-synthetic-inputs-v1', 'status': 'candidate inputs only; human grounding and prospective protocol freeze required', 'cases': cases}
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode()
    (DEST / 'candidate-inputs.json').write_bytes(encoded)
    protocol = {'format': 'ac3-prospective-readiness-v1', 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'NOT READY FOR HELD-OUT RUN', 'input_sha256': sha(encoded), 'candidate_histories': len(cases), 'candidate_questions': sum(len(c['tests']) for c in cases), 'human_grounding_complete': False, 'pilot_review_complete': False, 'frozen_thresholds': None, 'target_outputs_exist': False, 'automatic_evaluation_results_exist': False, 'requirements': ['Two independent reviewers verify source facts and question validity before running; disagreements require adjudication.', 'Use only eligible development/pilot evidence to set and freeze Failure Detection Recall, Failure Classification Accuracy, Test Validity and False-Positive Rate thresholds and the complete protocol before running or inspecting held-out outcomes.', 'Freeze model/provider, target strategy, audit configuration, test budget, versions, randomization, cost ceiling, exclusions and abstention handling. Respect the existing user-authorized spending limit.', 'Collect target outputs and automated classifications only after the preregistration. Do not change thresholds after seeing outcomes.', 'Prepare two separately randomized reviewer files containing only source, question and target answer; hide strategy, automated verdict, failure class and other reviewer judgments. Collect independent labels with uncertainty and adjudicate differences.', 'Analyze by independent histories as well as answer counts. Preserve abstentions, model failures, category misclassifications and all denominators.'], 'note': 'These are newly authored synthetic inputs, not proof of independent validation or a completed run. The gate was developed using different historical examples.'}
    (DEST / 'readiness.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    for slot in (1, 2):
        reviewer = {'format': 'ac3-prospective-grounding-review-v1', 'reviewer_slot': slot, 'input_sha256': sha(encoded), '说明': '本文件用于运行前核对题目、预期行为和标注的来源是否清楚且得到支持；没有目标回答或自动评分。每项 question_validity 填 valid、invalid 或 uncertain，rationale 写明依据。请独立判断，不确定就填 uncertain。', 'reviewer_declaration': {'reviewer_label': None, 'completed_by_human': None, 'completed_independently': None, 'used_ai_assistance': None, 'note': None}, 'cases': []}
        for case in cases:
            reviewer['cases'].append({'history_id': case['history_id'], 'source_messages': case['source_messages'], 'questions': [{**question, 'review': {'question_validity': None, 'rationale': ''}} for question in case['tests']]})
        (DEST / f'grounding-reviewer-{slot}.json').write_text(json.dumps(reviewer, ensure_ascii=False, indent=2) + '\n')
        os.chmod(DEST / f'grounding-reviewer-{slot}.json', 0o600)
    (DEST / '审核说明.md').write_text('# AC3 新候选输入\n\n`candidate-inputs.json` 有 8 段互不关联的合成历史、每段 4 道候选测试。**尚未运行，也没有答案和评分。** 将 `grounding-reviewer-1.json` 和 `grounding-reviewer-2.json` 分别交给两人，先独立核对来源与题目是否清楚、无不支持的前提；`question_validity` 填 `valid`、`invalid` 或 `uncertain`，`rationale` 写明依据。`readiness.json` 列出运行前所需条件。\n\n完成有资格的 pilot 审核并依据 pilot 冻结四项阈值及完整协议后，才可采集本包的被测回答和自动评分。之后另为两位审核者分别生成随机顺序的来源、问题、回答文件，不展示自动评分、策略或对方判断。请勿事后根据这些结果修改阈值。\n', encoding='utf-8')
    os.chmod(DEST / 'candidate-inputs.json', 0o600)
    print(json.dumps({'output': str(DEST), 'input_sha256': sha(encoded), 'histories': len(cases), 'questions': sum(len(c['tests']) for c in cases), 'status': protocol['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
