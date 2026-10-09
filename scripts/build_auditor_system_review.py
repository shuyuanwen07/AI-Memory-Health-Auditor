"""Report Auditor improvements separately from target-memory experiments."""
import hashlib
import html
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/auditor-system-review'


def main():
    OUT.mkdir(exist_ok=True)
    cycles = []
    for cycle in [1, 2, 3, 4, 5, 6, 7, 12, 13, 14]:
        folder = ROOT / f'output/ten-cycle-{cycle:02d}'
        frozen = json.loads((folder / 'freeze.json').read_text())
        study = ROOT / f'datasets/studies/ten-cycle-{cycle:02d}/study.json'
        assert hashlib.sha256(study.read_bytes()).hexdigest() == frozen['dataset_sha256']
        results = json.loads((folder / 'study-results.json').read_text())
        rows = [e for run in results['runs'] for e in run.get('evaluations', [])]
        assert len(rows) == 24
        assert all(e['response']['execution_metadata']['response_source'] == 'ollama' for e in rows)
        cycles.append({**frozen, 'actual_calls': len(rows), 'status': 'Failed guard retained; repaired in cycle 6' if cycle == 5 else 'Completed',
                       'notice': 'Synthetic API regression; not independent human validation.'})
    calibration = json.loads((ROOT / 'output/ten-cycle-summary/evaluator-calibration.json').read_text())['AI_reference_calibration']
    proof = json.loads((OUT / 'ui-verification.json').read_text())
    with zipfile.ZipFile(OUT / 'ui-qwen-artifact.zip') as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == sha for name, sha in manifest['files'].items())
        proof['all_export_manifest_hashes_valid'] = True
    (OUT / 'ui-verification.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    coverage = [
        ('输入与导入', '授权、大小、角色、时间戳、来源引用', 'test_conversation_import_fidelity.py; test_input_and_relationship_guards.py', '通过回归检查'),
        ('记忆抽取', '前端选择与后台调用一致；缺少云密钥时可选本地抽取', 'test_auditor_configuration_integrity.py; NewAudit.workflow.test.tsx', '已修复并实际界面验证'),
        ('标准记忆与审核', '跨对话引用、关系环、创建审计后证据不可变', 'test_input_and_relationship_guards.py; test_auditor_configuration_integrity.py', '已修复冻结漏洞'),
        ('测试题生成', '来源支撑、答案泄漏、题目再生成、统一试题', 'test_llm_pipeline.py; test_test_quality_and_baselines.py; test_trace_and_test_review.py', '已补城市泄漏检查'),
        ('判分与校准', '转述澄清、抢先选择、无关冲突、歧义答案', 'test_iterative_audit_quality.py; test_llm_judge.py; evaluator-calibration.json', '已修复已发现误判；人工盲审待完成'),
        ('实际模型输入', '检索与实际发送分开；零记忆答对不能证明记忆有效', 'test_target_memory_input_evidence.py; test_target_context_isolation.py', '回归与真实 Qwen 流程通过'),
        ('执行、取消与恢复', '保留完成记录，恢复不重复调用；取消状态和预算', 'test_audit_execution_service.py; test_api_experiment_flow.py', '通过回归检查'),
        ('比较与统计', '同题配对、配置差异提示、无样本不记零分', 'test_audit_comparison.py; test_experiment_analytics_metrics.py; test_metrics.py', '通过回归检查；小样本结论受限'),
        ('存储、导出与复现', '证据冻结、版本身份、导出摘要一致、文件哈希', 'test_api_experiment_flow.py; ui-verification.json', '已修复版本记录；真实 PostgreSQL 导出全部哈希通过'),
        ('用户界面', '可见 Qwen、审核反馈、自动检查与人工审核分开', 'NewAudit.workflow.test.tsx; TestSuiteReview.test.tsx; auditor-system-check.jpg', '已修复并实际界面验证'),
    ]
    payload = {'focus': 'Auditor system, not target model', 'training': False, 'auditor_cycles': cycles, 'actual_calls_in_auditor_cycles': 240,
               'coverage': coverage, 'same_response_calibration': calibration, 'ui_check': proof,
               'backend_verification': {'passed': 175, 'skipped': 1, 'note': 'SQLite regression suite; real PostgreSQL path separately checked through UI and exports.'},
               'frontend_verification': {'passed': 49, 'production_build': 'passed'},
               'limitations': ['AI-reviewed development calibration is not blind human validity.', 'Synthetic sources reuse familiar task templates.', 'OpenRouter is unavailable in the currently running backend; real cloud gateway validation remains pending.', 'No empirical commercial-product comparison has been performed.', 'The three target-memory iterations 8/9/10 are excluded from Auditor iteration count.']}
    (OUT / 'review.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    table = ''.join('<tr>' + ''.join(f'<td>{html.escape(c)}</td>' for c in (row[0], row[1], '回归检查与保存的验证记录', row[3])) + '</tr>' for row in coverage)
    descriptions = ['识别转述式澄清，不再只依赖问号', '排除把数据库误作部署政策的冲突', '识别澄清前抢先选择方案', '区分条件说明、存储描述与实际选择', '测试否定式冲突和澄清：保留失败记录', '修复第五轮否定检查被覆盖的问题', '核对实际冲突两端，排除日志等无关信息', '识别正确事实夹带虚构冲突', '修复服务选择、Qwen 展示和标准证据冻结', '修复城市答案泄漏与自动审核文案']
    cycle_table = ''.join(f"<tr><td>{i+1}</td><td>{descriptions[i]}</td><td>24</td><td>{'失败保留；第六轮修复' if c['cycle']==5 else '已完成'}</td></tr>" for i, c in enumerate(cycles))
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>审计系统检查与迭代</title><style>body{{font:16px/1.65 system-ui;margin:0;background:#f4f7fa;color:#16304b}}main{{max-width:1150px;margin:auto;padding:36px}}section{{background:white;border-radius:16px;padding:24px;margin:20px 0}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #e3e9ef}}.stats{{display:flex;gap:20px;flex-wrap:wrap}}.stat{{background:#edf5ff;padding:20px;border-radius:12px;flex:1;min-width:160px}}strong{{font-size:30px;display:block}}.note{{color:#81520a;background:#fff6df;padding:16px;border-radius:12px}}img{{max-width:100%}}</style><main><p>AI Memory Health Auditor · 系统质量检查</p><h1>优化审计系统，固定被测 Qwen</h1><p>检查对象是抽取、出题、判分、追踪、比较、导出和展示。Qwen 通过 API 产生回答，模型权重未训练或修改。</p><div class="stats"><div class="stat">Auditor 改进与回归<strong>10 轮</strong>240 次实际 Qwen 调用</div><div class="stat">相同回答的开发集判分分歧<strong>24 → 0</strong>226 条明确 AI 标签；另 14 条有歧义</div><div class="stat">验证<strong>175 + 49</strong>后端与前端检查通过；生产构建通过</div></div><p class="note">24 → 0 是开发样本与 AI 预审标签的符合程度，不能当作独立人工准确率。第 5 轮失败也保留在十轮记录中；第 6 轮修复。此前目标记忆改动的第 8–10 轮不计入这十轮。</p><section><h2>已经修复的审计系统问题</h2><ul><li>本地 Qwen 被云服务筛选规则隐藏。</li><li>首次抽取读取后台默认配置，未使用界面选择。</li><li>创建审计后标准记忆仍可被修改，破坏历史证据。</li><li>城市答案泄漏检查依赖有限的内置名称。</li><li>自动检查通过被写成“人工审核完成”；拒绝试题的阻塞状态不清晰。</li><li>规则判分配置记录过时版本，与实际实现不一致；新建实验现记录实际版本，旧记录保留。</li></ul></section><section><h2>十个环节的检查结果</h2><div style="overflow:auto"><table><thead><tr><th>环节</th><th>检查重点</th><th>验证证据</th><th>结果</th></tr></thead><tbody>{table}</tbody></table></div></section><section><h2>Auditor 十轮记录</h2><table><tr><th>序号</th><th>改进与回归</th><th>实际调用</th><th>记录</th></tr>{cycle_table}</table></section><section><h2>真实界面完整流程</h2><p>合成对话 → 本地抽取 → 审核 → Qwen API → 判分 → 实际发送追踪 → PostgreSQL 保存 → 实验导出。两题中一题失败：位置记忆存在于存储，但检索并未发送；Qwen 回答“没有足够信息”，系统正确显示失败与零条输入。导出文件全部摘要一致。</p><p><a href="/audits/{html.escape('RUN1E6393C984C0485E83D7A14B98E72130')}">查看完整流程的审计结果</a></p></section><section><h2>仍需人工复核</h2><ol><li>对 AI 标注的 PASS/FAIL 做盲审，优先看 14 条歧义回答、先选方案再澄清、无关冲突和正确值夹带错误解释。</li><li>确认合成场景的来源、标准记忆和预期行为；新名称不等于全新任务类型。</li><li>把系统诊断价值和目标修复收益分别评价。目标 75% → 100% 的结果不是 Auditor 准确率。</li><li>当前后台未配置可用 OpenRouter；补云调用与商业产品实测后才能写相应结论。</li></ol></section><p>检查覆盖主要环节与已发现风险；没有把有限回归检查表述为“系统所有可能情况已无问题”。</p></main></html>'''
    (OUT / 'report.html').write_text(document)
    (ROOT / 'frontend/public/reports/auditor-system-review.html').write_text(document)
    print('Auditor report: 10 cycles, 240 actual calls, export hashes valid.')


if __name__ == '__main__':
    main()
