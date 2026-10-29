"""Prepare human review copies of revised AC2 questions, retaining old uncertain labels."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / 'output/proposal-delivery/ac1-ac2-ai-review-intake-2026-10-28'
OUT = ROOT / 'output/proposal-delivery/ac2-revised-question-review-2026-10-28'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    source = INTAKE / 'received-ai-suggestions.json'
    confirmation = INTAKE / 'human-confirmation-record.json'
    direction = INTAKE / 'uncertain-direction-confirmation.json'
    d, c, u = (json.loads(p.read_text()) for p in (source, confirmation, direction))
    assert digest(source) == c['applies_to_file_sha256'] == u['source_sha256']
    assert c['user_statement'] == '已逐项人工核对并认可'
    assert u['user_statement'] == '保留 uncertain，按意见修改题目（推荐）'
    rows = [i for i in d['待裁定项目'] if i['criterion'] == 'AC2']
    assert len(rows) == 13 and len({i['item_id'] for i in rows}) == 13
    revised = []
    for item in rows:
        old = item['source']['task']; decision = item['human_final_decision']; h = old['history']
        assert decision['valid'] == 'uncertain'
        sources = {x['message_id']: x for x in item['source']['source_history_zh']}
        ids = decision['source_message_ids']
        assert all(i in sources for i in ids)
        ref = old['proposed_reference']
        if 'database technology' in old['question']:
            project = 'Linden' if h == 'P4-H2' else 'Meridian' if h == 'P4-H3' else None
            assert project and len(ids) == 2 and 'PostgreSQL' in sources[ids[1]]['content'] and project in sources[ids[1]]['content']
            q = f'What is the current database technology for the {project} capstone backend after the recorded migration? State the current technology.'
            behavior = f'State that the {project} capstone backend currently uses PostgreSQL; MySQL was used previously and is no longer used there. An answer identifying PostgreSQL as current is sufficient; historical detail is optional.'
            basis = '限定为迁移后的当前后端数据库，允许只回答 PostgreSQL；历史信息不是通过的必要条件。'
        elif 'programming-language choice' in old['question'] and h == 'P4-H1' and 'concise profile' in old['question']:
            assert len(ids) == 2 and 'Python' in sources[ids[0]]['content']
            q = 'What is the user’s general programming-language preference for backend projects? State its general scope.'
            behavior = 'State that the user generally prefers Python for backend projects; do not present it as a requirement that overrides project-specific rules.'
            basis = '明确询问一般后端偏好，避免与项目后端的专门要求混淆。'
        elif 'programming-language choice' in old['question']:
            project = {'P4-H1': 'Cobalt', 'P4-H2': 'Linden', 'P4-H3': 'Meridian'}[h]
            assert len(ids) == 2 and 'Java' in sources[ids[1]]['content'] and project in sources[ids[1]]['content']
            q = f'For {project} capstone backend work, which language does the course require, and what remains the user’s general backend preference in other contexts?'
            behavior = f'State that {project} capstone backend work is subject to the Java-only course requirement, and that the user generally prefers Python for backend projects. Keep the Java requirement within the stated project/backend scope.'
            basis = '明确任务仅为该项目后端，保留一般偏好且不扩大 Java-only 的适用范围。'
        else:
            raise ValueError(f'Unknown task: {item["item_id"]}')
        revised.append({'original_item_id':item['item_id'], 'revised_item_id':'REV-'+hashlib.sha256((item['item_id']+'-v1').encode()).hexdigest()[:16],
                        'history':h,'original_question':old['question'],'original_reference':ref,'original_judgment':'uncertain',
                        'adjudication_reason':decision['reason'],'revised_question':q,'revised_expected_behavior':behavior,
                        'revision_rationale':basis,'supporting_source_message_ids':ids,'source_history':item['source']['source_history_zh'],
                        'review':{'question_validity':None,'expected_behavior_supported':None,'source_ids_sufficient':None,'rationale':''}})
    assert len({i['revised_item_id'] for i in revised}) == 13
    OUT.mkdir(parents=True, exist_ok=False)
    template={'format':'ac2-revised-question-human-review-v1','instructions_zh':['原题依旧 uncertain，本文件是未验证的修订建议，不改变原实验。','独立核对问题、预期行为和来源；三个判断字段填写 valid、invalid 或 uncertain，并在 rationale 写理由。','提交前填写审核者声明；不得预先把本次审核称为已完成。'],
              'provenance':{'suggestions_sha256':digest(source),'human_confirmation_sha256':digest(confirmation),'direction_confirmation_sha256':digest(direction)},
              'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'has_seen_other_review':None,'used_ai_assistance':None,'completed_at':None,'note':''},'items':revised}
    for n in (1,2):
        obj={**template,'reviewer_slot':n}
        with (OUT/f'reviewer-{n}.json').open('x',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
    print(f'Prepared two blank review copies with {len(revised)} linked revised questions: {OUT}')

if __name__ == '__main__':
    main()
