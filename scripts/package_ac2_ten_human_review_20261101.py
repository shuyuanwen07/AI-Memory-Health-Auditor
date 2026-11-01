"""Package the actual source-bound AI reviews for explicit human checking."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/proposal-delivery'
REVIEW = BASE / 'ac2-original-ten-effective-review-20261101-v1'
ANALYSIS = BASE / 'ac2-original-ten-effective-review-analysis-20261101-v1'
DEST = BASE / 'ac2-original-ten-human-review-20261101-v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    DEST.mkdir(exist_ok=False)
    summary = read(ANALYSIS / 'summary.json')
    first, second = [read(REVIEW / f'reviewer-{n}-completed.json') for n in (1, 2)]
    lookup = [{h['history_id']: h for h in review['histories']} for review in (first, second)]
    concerns = []
    for row in summary['rows']:
        if row['section'] != 'relationships' or row['outcome'] == 'valid':
            continue
        hid = row['history_id']
        judgments = []
        for index in range(2):
            history = lookup[index][hid]
            edge = next(e for e in history['relationships'] if
                        [e['source_memory_id'], e['type'], e['target_memory_id']] == row['identity'])
            facts = {f['memory_id']: f for f in history['facts']}
            judgments.append({'reviewer': index + 1, 'judgment': edge['relationship_validity'],
                              'note': edge.get('note'),
                              'source_fact': facts[edge['source_memory_id']],
                              'target_fact': facts[edge['target_memory_id']]})
        concerns.append({'history_id': hid, 'relationship_identity': row['identity'],
                         'source_messages': lookup[0][hid]['source_messages'],
                         'independent_ai_judgments': judgments,
                         'recommendation': '保留原始自动提取结果；此关系不计入已确认正确关系。保留两条有来源的事实，不推断它们互相覆盖。',
                         'human_decision': None, 'human_note': ''})
    assert len(concerns) == 6
    write(DEST / '06-关系疑点及建议处理.json', {'items': concerns, 'human_confirmation': 'pending'})
    for n in (1, 2):
        form = read(REVIEW / f'reviewer-{n}-completed.json')
        form['reviewer'] = f'human-reviewer-{n}'
        form['completed_by_human'] = False
        form['human_confirmation_status'] = 'pending'
        form['independent_of_other_human'] = None
        form['review_kind'] = 'Human verification form with AI suggestions visible; not a blind human review.'
        for h in form['histories']:
            h['ai_source_coverage_validity'] = h.pop('source_coverage_validity')
            h['source_coverage_validity'] = None
            for section, fields in [('facts', ['fact_validity']), ('relationships', ['relationship_validity']),
                                    ('questions', ['source_grounding', 'question_executability',
                                                   'reference_answer_validity', 'dimension_alignment'])]:
                for item in h[section]:
                    for field in fields:
                        item['ai_' + field] = item.pop(field)
                        item[field] = None
                    item['ai_note'] = item.pop('note', '')
                    item['human_note'] = ''
        write(DEST / f'0{n + 3}-人工审核者{n}.json', form)
    write(DEST / '07-确认表.json', {
        'user_statement': '', 'two_distinct_humans': None, 'independent': None,
        'completed_by_human': False, 'review_summary_sha256': sha(ANALYSIS / 'summary.json'),
        'scope': '10原始来源、60事实、40当前题目；另行确认6条关系不计入已确认正确关系。',
        'ai_suggestions_visible': True, 'relationship_concerns_handling': None,
        'note': '两位人工可各填一份审核表；也可逐项核对后向项目负责人明确确认。空白不等于通过。'
    })
    (DEST / '00-阅读说明.txt').write_text(
        '本包仅包含本次十场景复测，无需重审此前实验。\n\n'
        '原结果：计划40题，14有效、14无效、12缺失，完整保留。\n'
        '修复后实际生成40题：第一轮两位独立Astra high认定38有效、2存疑。\n'
        '再通过产品重新生成接口修订这2题；两位独立复核后当前40题均有效。\n'
        '这不是一次全自动生成40/40有效，也不是独立留出集：十段来源曾用于开发，结构相关。\n\n'
        '审核范围：10段原文完整性、60条提取事实、40道题的来源/可执行性/答案/维度。\n'
        '32条关系中26条获两位一致认可；另外6条见06文件。建议保留原记录，\n'
        '但不把这6条当作确认正确的覆盖关系，不据此改写原始事实。\n'
        '其中包括不同对象的饮品偏好、可同时成立的学习/饮食安排、每日频率与周周期等。\n\n'
        '01/02是两份AI审核，03是汇总；04/05为人工填写表，AI建议保留为ai_字段。\n'
        '审核者各自独立填写；本包可见AI意见，因此记录为AI辅助人工复核，不称人工盲审。\n'
        '06填写6条关系处理；07填最终确认。valid=有效，invalid=无效，uncertain=存疑。\n'
        '请勿为了达到百分比强行判有效；不同意见可直接改表并备注。\n'
        '确认后才运行冻结题组的真实回答/评分技术检查，并完成正式展示、报告、PPT及main CI。\n', encoding='utf-8')
    files = {'01-Astra-high审核者1.json': REVIEW / 'reviewer-1-completed.json',
             '02-Astra-high审核者2.json': REVIEW / 'reviewer-2-completed.json',
             '03-结果与证据绑定.json': ANALYSIS / 'summary.json',
             '证据/审核协议.json': REVIEW / 'protocol.json',
             '证据/当前题组协议.json': BASE / 'ac2-original-ten-effective-cohort-20261101-v1/protocol.json',
             '证据/两题重新生成.json': BASE / 'ac2-original-ten-question-revisions-20261101-v1/summary.json'}
    for name, source in files.items():
        target = DEST / name
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(source.read_bytes())
    manifest = {str(p.relative_to(DEST)): sha(p) for p in sorted(DEST.rglob('*')) if p.is_file()}
    write(DEST / 'SHA256.json', manifest)
    archive = DEST / 'AC2-十场景40题-双Astra-high审核-待人工确认.zip'
    with ZipFile(archive, 'x', ZIP_DEFLATED) as bundle:
        for relative in [*manifest, 'SHA256.json']:
            bundle.write(DEST / relative, relative)
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(json.dumps({'archive': str(archive), 'sha256': sha(archive), 'questions': 40,
                      'relationship_concerns': len(concerns)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
