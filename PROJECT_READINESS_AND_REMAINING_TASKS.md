# AI Memory Health Auditor：最终报告准备度与剩余任务

## 当前证据校正 — 2026-10-28

本节优先于下方 2026-10-27 早期快照。远程 `main` 已同步到 `40876e47e44f2af18187766a46976fe3bb15c3a5`；本地 `HEAD` 与 `origin/main` 相同，但工作树仍有未提交/未推送改动。远程提交包含版本化的 A/B/C 证据 ZIP 与哈希清单；解压后的 `artifacts/local/...` 按设计被 `.gitignore` 忽略，不是逐个提交的文件。证据包 SHA-256 为 `9eb48374b22834370d3c283d531cd66686c8aae9cf1e255610940116f9fb89b4`；清单列出的 360 个文件、逐文件 SHA-256、ZIP CRC 和 85,083,014 展开字节均已独立核验。详见 `research/evidence-20261027/README.md` 和 `manifest.json`。

- **实验原件现在可复核。** A 有 36 个目标回答；B 纳入 72 个回答，另将 4 个非规范恢复回答单独排除；归档主 C 有 84 个目标回答及 84 个有效评分。A/B/C 执行、条件、失败、请求与恢复材料位于 `artifacts/local/phase4-20261027/`。此前“最新 A/B 文件缺失”的说法只反映 2026-10-27 早期盘点，现已被远程 main 上的新包取代。
- **本轮用户反馈已逐项对上。** 上传的三个文件 SHA-256 分别为 `387b1915742690c1c0d4b11732e79e330c848ed3532b6cf7bb2edde1852aeabd`、`377c5a23db2b38f5f4c3cf7d42b031a60324cac3febe50d273f398ea3ea170bf`、`06ed0785e36deda11e6e41aa38c05e7ecbb9f7cb99565824f9b507c3f4716e39`。聊天中这 40 项的 ID 与 `shuyuan-recheck-transcription.json` 对应项 40/40 相同，关键判定亦相同，包括 `R-23b35e11a5783061` 为 accuracy failure / critical。第一轮 JSON 自报信息与用户后续更正冲突；两者都留存。由于这属于争议复核而非盲态首轮，且另一份复核把该严重错误判为不确定，不能把该条记作双方确认的严重错误。
- **2026-10-28 再次收到的附件与已登记原件完全一致。** 两份 JSON 与 40 项 ZIP 的 SHA-256 均匹配现有本地副本；没有产生第二份重复原件。ZIP 自带结构校验为 307 项通过，但其 provenance 明确注明 AI 辅助、已看过双方首轮结论、不是人工盲审。用户本轮给出的 40 项意见继续作为单独的争议后复核输入保留；其中 `R-23b35e11a5783061` 被用户标为 Accuracy / 严重，但首轮返回和 AI 辅助复核间仍有冲突，因此不改写两份原始返回或正式双评一致统计。
- **当前本地服务已完成合成数据三方法冒烟运行。** 2026-10-28 浏览器中的 `/new-audit` 流程从会话、ground truth、配置、题目生成走到结果页；后端 `/api/v1/health` 返回 `ok` / `database ready`。比较 ID `EXP1FBCD4858ABC48B69E296BC41BFB170A` 已完成：规则题 + 规则评审 `RUN6A74A303F5024F7B8FFA6F889F4BA07C` 为 6/8、75%；Agent 题 + 规则评审 `RUN0EB30D66B66742AB825FD9A30A380DDA` 为 3/7 个已判结果通过、另 1 个待复核；Agent 题 + AI 混合评审 `RUN461847267D604C40A88598C4C008D63A` 为 2/5 个已判结果通过、另 3 个待复核。规则题生成器 v29 接受 8/8 题。它是使用虚构 Harbour/Orchard 对话的本地产品冒烟，不是 proposal A/B/C，也不是人工验证；20/24 个结果已有自动判定，4 个仍待人工复核。完整记录见 `docs/proposal-delivery/CLEAN_START_VERIFICATION.md`。
- **本轮完成 tutor 闭环的系统内三组复测。** Diagnosis Agent 针对基线 `RUNA3DF5BE780A549538D706F50E82327ED` 要求核查答题时实际送入的记忆；检索回执确认只送入旧 MySQL、漏掉当前 PostgreSQL。随后同一合成历史与同一四题在三组中对照原始弱策略、通用提示控制和目标检索策略。弱策略与通用控制各为 3/12；目标策略 9/9 个已判答案通过，另 3/12 仍待人工判定；候选 Freshness 回执均显示 MySQL 历史和 PostgreSQL 当前项已送入。三个完整 app 导出及 SHA-256、36 条不含自动标签的盲审表见 `output/proposal-delivery/live-repair-loop-2026-10-28/`；系统 `/experiments` 可直接查看。它是单一历史上的探索性闭环，不是独立可靠性证明，也不替代 proposal A/B/C。
- **当前源码演示与提取修复已复核。** `/experiments` 中新增六次 GPT‑6 Luna 对照 run，共 48 个目标答案/自动评估并核对了 JSON/CSV 的全部 48 个评估 ID；Strong 在三组均高于 Weak，另有 14/48 未决。首次 intake 提取因 1,800-token 上限失败，离线校验保留失败。已将短历史提取预算最低值提高到 2,400 并保留 4,096 上限；全后端套件 2,749 passed、8 skipped。随后在一段 28 条消息（含 14 条用户来源消息）的独立合成对话中完成 extraction、relationship analysis、second-source check，生成 14 个候选和 2 条 AI advisory flags；14 条仍在 `/new-audit` 待人工审阅，因此尚无本对话的目标测试，也不冒称完整 end-to-end pass。角色执行回执在 `output/proposal-delivery/live-extraction-retest-2026-10-28/`。
- **人工交接已具体化。** `docs/proposal-delivery/MANUAL_REVIEW_HANDOFF.md` 列出系统内 3 条不确定答案、36 条无自动 verdict 的复核包、proposal A 的 13/48 uncertain validity / 6/36 unresolved responses / 2 disputed defect mappings、proposal B 的 72 条 source check 与 held-out gate、C 的 84-answer grader review 包；C 的 B/C 排序比较已按现有运行计算为 3/3。每位组员的 contribution/permission 确认也列明。团队已看过汇总结果，所以其复核不能称为未暴露的独立盲审；正式独立结论需要未接触评分的 reviewer 和另一位独立 reviewer 完成裁决。
- **可报告的回顾性结果有明确分母。** A：36 条回答中 30 条判定一致（27 失败、3 通过），6 条未决；自动检测在已决定 A 失败上为 27/27，但正式 A 缺陷发现率为空。B：72 条中 71 条判定一致（27 TP、1 FP、8 FN、34 TN），另有 1 条未决；已决定项召回率 27/35=77.14%，把自动不确定但人工失败计入分母为 27/36=75%。自动分类在 51 条已分类且一致类型的失败中为 51/51；联合检测/分类召回为 51/61=83.61%。这些是小样本、用户报告更正后的回顾性数据，不代表独立认证或总体性能。
- **其他人审结果保留不确定性。** 题目有效性 35/48 确认为有效、13/48 不确定；候选记忆 21/27 已判有效，6 条在无效/不确定间未决；24 个来源参考单元的 3 个“完整覆盖”依赖未确认候选，来源单元 recall 仍为空；关系分类为 6/9。101 条双方对 pass/fail 和严重性均一致的回答中，确认严重错误为 0；另 7 条严重性未决，含一条 reviewer 间分歧。报告见 `research/evidence-20261027/reports/PHASE_4_REVIEW_METRICS_2026-10-27.md`。
- **Proposal 完成度。** FR1–FR12 / NFR1–NFR5 已有代码实现和多轮工程/回归证据；当前工作树仍未冻结成发布提交。AC1、AC3 未正式达成：来源标注与审阅资格冲突、若干题目/答案/缺陷映射未决、独立盲审资格无法从原件证明。AC2 部分支持，不能声称所有生成题均无未支持内容。AC4 的合成演示结果、JSON/CSV 和 artifact ZIP 已做同一运行核对；本轮 diagnosis→repair→retest 的 3 组导出也已保存。AC5 的重复条件和 B/C 排序比较有实测证据；仍要披露外部模型使用默认采样和 C 仅覆盖 14 个兼容个案。归档 C 与本地单独保存的 C v5 是不同运行，不合并样本或指标。
- **本轮工程复核。** 修改后的正式评审分析器与证据清单测试已纳入 `python3 -m unittest discover -s scripts/tests -v`，本轮 73 项通过；新增 C 盲审表生成器通过 `py_compile` 与 84 行/条件隐去/哈希核对。源码 ZIP 已在全部本轮代码与文档改动后重新生成，共 887 个源文件；最终 SHA-256 为 `1d53441db53302e42e85fec2df43fe4c72d266488a836da9c4b8a874e4e7fa76`。ZIP CRC、嵌入清单、887 个逐文件哈希均核对通过；只允许 `scripts/phase4_review_form.js` 这一必要 JS 文件，未包含盲审私钥、用户审阅返回、数据库或本地运行目录。`git diff --check` 最终通过。
- **源码包前后端干净检查。** 此前 884 文件源码 ZIP 在全新临时目录 `npm ci` 成功；Node 24.6.0 / npm 11.5.1 下 `npm run build` 通过，62 个测试文件中 581 项通过、1 项跳过。Vite 报现有大 bundle 提示。该完整前端套件记录绑定旧 ZIP SHA-256 `995f3909c03d184d609a1b19295d061d7abd59df5bc7364fb53261c5cc6553de`；最新 ZIP 的前端代码未变。源码包 SHA-256 为 `326031ac…` 的版本已在全新临时目录解压并通过完整后端测试（2,749 passed，8 skipped）；其后只有五份报告文档修改，逐文件清单确认 backend 与 Python 脚本哈希均未变。最新 ZIP SHA-256 为 `1d53441d…`。未对最新 887 文件归档重跑 npm 全前端套件。工程测试不表示独立人工评审或 proposal A/B/C 正式达标。
- Docker 应用先前确认前端 `/new-audit` 可访问、后端 health 为 `ok` 且数据库 ready；这是服务存活检查，不等于 FR/NFR 全量验收，也不会把归档运行记录导入新数据库。

### 2026-10-27 早期检查快照（由上方当前状态覆盖）

检查日期：2026-10-27（Australia/Sydney）。范围：当前工作区源码、运行容器、Proposal、课程 A2、旧审计与之后的保存证据。本轮只读核查并运行隔离定向测试，没有修改业务代码、依赖锁、`.env`、正式数据或 Final Report，没有执行付费模型调用。

**历史状态，已被 2026-10-28 证据包更新：** 早期本地核查时 A/B/C 原始文件未找到；之后远程 `main` 新增 `research/evidence-20261027/experiment-evidence.zip` 与清单。按 README 解压后，归档 A/B/C 原始运行和 Phase 4 metrics 可在 Git 忽略的 `artifacts/local/...` 路径复核。因此“仍缺 A/B 原始运行”的说法只属于早期快照，不是当前状态。另有独立保存的 C v5 探索性运行及可复算分析，见 `docs/proposal-experiment-audit.md`；它与归档 C 是不同运行，不能合并样本，也不等于独立人工验证或正式通过 Proposal C。

### 2026-10-27 后续状态补充

- 当前本地分支和 `origin/main` 均指向 `f9f777ee11813642e280ec1885ab8d867011ebdd`；本工作树在该提交上有未提交修改，尚未推送。此前页面中两题/每维的硬门槛已改为每维至少一题，额外题数按已确认的不同证据尽量均匀分配。8 题、维度证据容量 6/2/1/2 时预览为 3/2/1/2；40 项前端工作流测试、71 项目标后端测试通过。
- 新增用户提供的 Phase 4 包含一份对应全部 216 项的评审返回，材料指纹匹配。返回自报 `completed_independently=false`、`used_ai_assistance=true`、`has_seen_automated_results=true`，正式验证器据此拒绝其作为独立盲评。原文件保留在本机 `reviewer-1(1)/`，未放入源代码包；哈希及局部文件状态记在 evidence inventory。
- 当前生成的本地源代码包包含 883 个文件；归档 SHA-256 记在相邻的 `source-manifest.json`，逐文件哈希与嵌入清单匹配，并排除原始评审返回和运行数据。本轮 `scripts/tests` 共 71 项通过，包含打包与证据清单检查。包来自有未提交修改的工作树，不是远程 main 上的提交。
- 用户已授权使用 OpenRouter `openai/gpt-6-luna` 重跑模型请求且不设预算上限。授权后完成的 C v5 结果和原始运行回执已另存；A/B 原始运行包、Phase 4 condition map 和 Phase 4 metrics 仍缺失，不能据旧 readiness 摘要宣称这些实验已核实。正式 AC1/AC3 仍需要符合盲评要求的真实人工证据。
- **C v5 更新：** 已实际完成 84 条目标回答及 84 条 GPT-6 Luna 自动评分；每轮均为 14 题。Weak 为 4/14、4/14、4/14，累计 12/42（28.6%）；Strong 为 12/14、11/14、12/14，累计 35/42（83.3%），Strong 在配对三轮均较高。运行器本地词面匹配为 Weak 2/14、Strong 7/14 每轮，和适配的 LongMemEval 风格评分同为 Strong 3/3 轮较高；该词面分不是 Auditor 四维 Memory Health 分数，所以只作为事后代理一致性，不称正式 Proposal C 排名一致性。此为重用同一 14 题的本地兼容子集；grader 与 target 是同一模型家族，没有人类参考标签。另有两次目标请求 503，成功请求与失败请求收据均保留；费用估算约 US$0.07894，不包含可能对失败调用计费，非账单金额。

## 判断：B — 基本具备，冻结和最终定稿前有少量明确阻塞

可以准备最终报告草稿和源码交付。干净源码 ZIP 已按锁文件成功安装、构建，并通过完整前端测试；提交版定稿前仍需冻结并提交最终源码/运行环境、更新最终包、核对团队贡献与第三方归属，并决定报告引用哪些已绑定原件的结果。当前尚无绑定最终冻结提交的真实 Upload→Export 完整运行记录；若报告要声称最终版端到端已验证，需补一次受控实跑，或明确使用旧版本实证并标出版本差异。正式独立可靠性和完整 A 缺陷发现率仍不能宣称完成，但课程 A2 并不要求删除失败或证明研究假设成立；将未完成项和限制讲清即可据实交付原型。

课程材料：`/Users/yichaowang/Downloads/ELEC5623_A2.pdf`（5 页；开发 20 分，截止 11 月 3 日 23:59；演示和 Q&A 10 分，11 月 4 日，现场禁用 AI）。Project Development 分项为功能与实现 4、GenAI 与架构 4、评价与分析 4、相关工作与创新 3、Track 对齐 2、产品体验 2、文档与团队 1。提交源码和报告两项，源码应可检查、含设置与占位符、无秘密，报告建议 8–12 页不含参考及附录。批准 Proposal：`../ELEC5623_Group2_Proposal.pdf`，Track B，FR1–12 / NFR1–5 / AC1–5、三组实验和四维指标。课程要求诚实论证、基线与局限，不规定 Release20 自设 75% 为课程及格线，也不要求复现全部历史原件。旧基线：`output/evidence-audit/FINAL_REPORT_EVIDENCE_AUDIT_2026-10-27.md`；其 A/B/C 缺失和前端启动失败结论已被之后证据部分更新，不能当作现状。

证据等级：**实现**＝代码可定位；**实测**＝有绑定版本的执行/测试证据；**历史**＝真实但属于旧快照；**摘要**＝缺原始记录；**未验证**＝不证明有 Bug；**人工待确认**＝不能由软件或 AI 自行证明。下面不以存在测试源码代替测试通过，也不把规则模式说成 LLM 模式。

## 1. 当前版本、配置与检查结果

- 分支 `codex/owner-c-validation`；HEAD `b44ced90ea39eb569eaa6ea01dee4c3df5712085`。检查时 20 个 tracked 修改、42 个未跟踪文件；包括业务源码、测试、锁文件、Compose 和研究脚本。HEAD 不等于完整被测工作树；尚无此次最终干净提交或正式 tag。`git diff --check` 通过。
- Docker Compose 的 backend/frontend 正在运行，PostgreSQL healthy；容器内 `GET /api/v1/health` 返回 200 且 database ready。后端/前端 bind mount 分别映射当前源码目录；后端采用 Uvicorn reload。后端容器磁盘上的 `rule_based.py` 哈希与本地和 Phase 4 follow-up manifest 一致，但仅凭 bind mount/文件哈希不能证明运行进程每个模块都已重载，冻结时仍需实际进程/版本收据。`AUDITOR_CODE_REVISION=development`，并非发布版本。
- 容器环境当前 `PIPELINE_PROVIDER=rule_based`、`EVALUATOR_PROVIDER=rule_based`，`OPENROUTER_DEFAULT_MODEL` 和 `PIPELINE_MAX_OUTPUT_TOKENS` 环境变量未设置；代码 OpenRouter 模型回退为 `openai/gpt-6-luna`，实际 target provider/model 由每次运行配置决定，不能仅由该默认值断言本次运行目标。按当前代码：rule evaluator v65、rule generator v28、extractor v27、target controlled-memory-v35、policy v43。A/B 历史运行的配置按各自收据核对；C v5 target 和 grader 均为 OpenRouter `openai/gpt-6-luna`，grader 使用 `reasoning_effort=none`。默认规则流水线不证明 LLM extraction/generation/judging 的当前实际执行。
- 当前运行容器的 Node 22.22.2 / npm 10.9.7 与其实际 Vite 8.3.0、Vitest 5.0.1 仍旧于 package manifest/lock 中的 8.3.5 / 5.0.5（TypeScript 均 5.7.3）；容器内 26 项前端定向测试使用该现有安装。另已在全新临时目录从 assessed-source ZIP 按锁文件完成 `npm ci`，并在 Node 24.6.0 / npm 11.5.1 下通过构建及完整前端套件（581 passed、1 skipped）。这证明交付源码包可按锁文件安装，不表示正在运行的 Docker 依赖卷已重建；详见 `docs/proposal-delivery/CLEAN_START_VERIFICATION.md`。
- 较早完整测试：Phase 4 follow-up 后端日志 **2738 passed、8 skipped、1 warning**；8 个 PostgreSQL 项在隔离迁移测试库 **8 passed**。对 follow-up manifest 的 137 个后端源码文件，本轮逐一核验 **137/137 哈希一致**，说明该后端测试证据对应当前这些源码，具体日志 `artifacts/local/phase4-followup-20261027/backend-full.log`、`postgres.log`。不说明当前容器依赖或整棵工作树与测试机完全相同。Phase1/2 前端日志也有 **581 passed/62 files**，`artifacts/local/phase12-20261027/frontend-full.log`；这与本次从当前源码 ZIP 进行的全量前端测试是两个独立快照。
- 本轮隔离检查：`scripts/run_offline_backend_tests.py` 对 blind judge cap、Phase3 和 Phase4 follow-up **75 passed**（SQLite 临时库，外部 socket blocked attempts 0；证据 `/private/tmp/mha-readiness-20261027/isolated-suite-vvswoji5/isolation-evidence.json`）；`python3 -m unittest discover -s scripts/tests -q` **57 passed**；当前容器两个前端文件 **26 passed**。真实 provider 未被调用。这个定向结果不是重新运行的后端/前端全套。
- 来源版本：Phase1/2 端到端 source manifest 20 个受记录文件中 15 同哈希、5 已变化：`backend/app/api/routes.py`、`evaluator/rule_based.py`、`extraction/rule_based.py`、`test_generator/rule_based.py` 和一个测试文件。Phase4 冻结 app source 136 文件中 132 一致、4 已变化（evaluator、baselines、rule generator、domain schema）；现有后续同答案重评 v65 与原结果分别保留。截图方面 Phase1/2 UI receipt 明确 `screenshots_saved: false`；有 Safari 观察与浏览器导出记录，不能称有该次截图。

## 2. 已完成且不必重复的任务：原问题 → 状态 → 修复与证据

| 原问题 | 当前状态和修复位置 | 核验和边界 | 后续 |
|---|---|---|---|
| Rolldown binding / 前端测试启动失败 | Compose 为 Linux 容器隔离 `frontend_node_modules`；锁文件已更新 | Phase1/2 有 581 passed；本轮现有容器定向 26 passed；当前 assessed-source ZIP 的锁文件安装/build/full suite 也通过（581 passed、1 skipped）。运行容器仍保留旧版本 node_modules | **不再列为同一启动 Bug；**如需让当前容器依赖同步，重建其 frontend volume；源码 ZIP 的干净安装已验证 |
| Blind Judge 缺输出 cap | `backend/app/evaluator/llm_judge.py` 按有效配置发送 cap，截断不接受；`backend/tests/test_blind_judge_output_budget.py` | 本轮包含该测试的 75 项隔离通过；是 mock/contract HTTP 收据。当前运行环境 cap 未设置、默认 rule evaluator；未见当前最终配置的真实 LLM judge 带 cap HTTP 收据 | 如要声称真实盲评 cap 在目标 provider 已运行，P1 补受控实测；否则标代码和契约验证、运行未验证 |
| 当前全链路 | API、浏览器及导出已实现；Phase1/2 真实 8 个 Luna 回答覆盖四维 Weak/Strong，规则提取、出题和评估 | `artifacts/local/phase12-20261027/final/` 的 9/9 文件哈希核对成功；API/浏览器 CSV/JSON 绑定两次 run，相关 UI 可见记录，截图未保存。该运行 v63/v26/v27/v42；五个记录文件后已变化 | 无需重做旧实验；最终版若声称全链路实测，需在冻结版本补一次；当前全 GenAI pipeline 仍未验证 |
| Evaluator 漏检、owner/actor 混淆 | v64 source-owner binding、v65 source-abstention 分类；`evaluator/rule_based.py`、`evaluator/source_abstention.py` | Phase3 开发/保留实体合成契约和回归；本轮 75 项定向通过。A 36 条同答重评 verdict 未变；27 个 AI 辅助参考失败里分类覆盖 0→26/27，仅工程观察 | 不能将该覆盖率当独立分类准确率。复杂指代、多个 actor、语言变化仍未全面验证 |
| 检索遗漏、跨话题错误关系 | `memory_agent/store.py` 对 Strong 冲突端点做预算组合；`extraction/rule_based.py` v27 限定无变化/食物边界；实体关联解析 | Phase3 合成前后对照、回归和 9 次真实目标 replay；目标 replay 的原自动 clarification checker 仍有假阴性，不声称实际得分改善 | 保留边界，不把一次错误一概归为检索；扩展泛化属可选 |
| Release20 / Harbour 原始文件 | 所引用 `experiments/stability-study-20261023-dev20-evidence-disjoint/` 和 `experiments/presentation-demo-20261023/result/` 在当前工作区缺失；当前 Git 树未找到前者 | `docs/REQUIREMENT_TRACEABILITY_MATRIX.md` 与 `docs/PRESENTATION_DEMO.md` 提供摘要，不能核实具体原响应。Release20 摘要为 26/36、未达自定 75%，另记录两个 actor 错误 | 不必为当前结论强制找回；若报告引用这些数值作核心实证，先向原持有人找原件，找不到只归因于摘要或不用，不能补造 |

## 3. 产品功能、需求与现有可交付边界

| 模块与 Proposal | 代码/证据 | 当前判断与风险 |
|---|---|---|
| Conversation / Ground Truth：FR1、FR2、FR3、FR9；NFR1、NFR2 | `frontend/src/components/ConversationStep.tsx`、`GroundTruthReview.tsx`、`backend/app/api/routes.py`、`backend/app/extraction/`；Phase1/2 授权合成输入、source、关系、review/confirm、持久化；本轮 GT review 11 测试通过 | 核心路径有旧快照实测及当前代码/回归。授权依赖使用者声明；真实独立提取召回与所有访问威胁未证明。Accept/Edit/Reject/Add 组件有测试，不能把部分测试和一次输入推广为所有情况 |
| Test Generation：FR4；AC2 | `backend/app/test_generator/`、`quality.py`、`baselines.py`；A 三模式 36 实际目标回答、记录预算及来源；生成器 v28 定向回归 | 四维与证据校验实现、规则生成路径有实测；A 13 个题目有效性为不确定，不能说全部题目得到独立证实。当前默认规则模式；代码支持 Agent/LLM 不代表本次 A 是 LLM 生成，更不能由此声称 GenAI 测试生成已正式验证 |
| Target / Execution：FR5、FR6、FR10；NFR5、AC5 | `target_systems/controlled.py`、`memory_agent/store.py`、provider/route 冻结；Phase1/2 8 个真实 Luna target 及请求哈希；B 72 真回答、相同问题/策略三重复 | 核心路径旧快照实测；目标记忆和参考答案隔离有请求及测试证据，服务故障与恢复有模拟测试和 B/C 实际中断记录。无法保证每类 provider 故障/断电均能恢复；v65/v28 新完整流程仍需绑定最终版 |
| Evaluation / Results：FR7、FR8、FR11、FR12；NFR3、NFR4；AC4 | `evaluator/`、`ResultDashboard.tsx`、`services/csvExport.ts`；Phase1/2 run 评分及 browser/API 导出核对；uncertain 分母回归 | 有运行及规则评分证据；原历史 dashboard 观察无保存截图。AI judge 输出 cap 有契约测试无当前真实收据；分类/语义可靠性和 novice usability 仍是局限 |

AC1：关系和提取有回顾性/限定人工复核，但完整独立标注来源、全原文 gold 和最终语义裁决不足，**不能声称正式通过**。AC2：生成题可执行、部分通过 grounding，但 13/48 审核题仍不确定，不能证明所有题均无未支持事实。AC3：没有可核验的独立盲审结果，且预先冻结 pilot 阈值及 held-out 全套指标未建立，**未证明达标**。AC4：当前来源的六次 target demo 已核对同一组 48 个 JSON/CSV 评估 ID；独立 intake retest 证明修复后的三个提取角色都能在该案例完成，但因 14 条候选记忆仍待操作员确认，完整 intake-to-results walkthrough 仍未完成。AC5：B 使用相同问题及三重复并保留配置，实测能力有证据；provider 实际 model-default sampling，temperature/seed 未发送，随机种子不能声称生效，输入等同性和记录不等于输出可逐字复现。

权限/安全：代码实现授权与服务端凭证、目标/审计器隔离及基本安全合同；现有测试不等于完整渗透测试或身份鉴权认证。`.env` ignored，敏感材料位于 ignored 目录。最终包需对实际将发布的内容做扫描与人工授权核验，本次未对全部隐私/二进制做认证。FR/NFR 全量原始定义与具体历史映射可参考 `docs/REQUIREMENT_TRACEABILITY_MATRIX.md`，但其中旧版本状态必须以本文更新为准。

## 4. 实验状态总表

| 项目 | 实际完成及可报告内容 | 不能声称 / 仍缺内容 |
|---|---|---|
| A 三方法 | `artifacts/local/phase4-20261027/A-live.json`：3 个合成历史 × 3 方法 × 4 题 = 36 个真实目标回答；同源、相同目标与 evaluator、相同预算；预先确定每历史 3 个潜在缺陷 ID 和发现去重单位。原始回答、9 个导出、请求 SHA、人工批准声明存档。最终复核的描述性指标参见 `output/engineering-verification/PHASE_4_REVIEW_METRICS_2026-10-27.md` | 不能声称上下文方法显著胜出或正式完整 FDR；多个原题存在当前/历史或后端范围歧义；原冻结缺陷定义不覆盖全部“遗漏/不知道”。人审有更正 provenance 和复核看过首次判断，6 个 A 回答未一致。题目有效性与独立 reference 不完整；原有 category 4/4 是按预执行批准和指定类别的覆盖，后续 13 题不确定不能无条件宣称经独立证实。此实验为规则/模板配置，不能写成实际大模型 Agent 三臂对比。 |
| B Weak/Strong | `B-live.json`：3 个相似合成历史 × 4 个共享问题 × 2 检索策略 × 3 重复 = 72 个真实目标回答。相同 Luna、Strong reader、规则 writer、50 记录/16000 字符/2048 输出上限；有效温度和 seed 为 model default。旧 v64 自动宏均值 Weak 25%、Strong 97.22%；Weak 9/27/0，Strong 34/1/1（pass/fail/uncertain）；Strong 三次宏结果 100/100/91.67%，SD 3.93 个百分点 | 只有三组模板相关历史，不是独立人群或泛化证明；Strong 给出更多记忆内容，检索差异不等于模型变化；失败和 uncertain 原样保留。关键错误人工评审有未定项；当前 v65 对既存答案重新评估不新增目标调用且 verdict 不变，不等于全套当前版重跑。|
| C LongMemEval | 主归档 C 使用 14/500 Oracle 个案，完成 84 个 target answers 和 84 个 pinned upstream-prompt-compatible GPT-4o judgments；Weak 15/42、Strong 30/42，Strong 三轮均高于 Weak。Proposal B 的四维 Auditor macro 同样三轮 Strong 高于 Weak，因此本地 rank-direction agreement 为 3/3。C v5 是单独的候选运行（Weak 12/42、Strong 35/42），不与主归档合并。 | 排序检验已计算；结果仍限于 14 题本地兼容子集，三轮重复相同个案，非全量官方 S/M benchmark，也没有人工校准 grader。C v5 使用 GPT-6 Luna grader，另有两次 503，不能替代主 C。主 C 预算/请求估算以原始归档和失败记录为准。|
| Extraction / relations | 27 个候选：21 双方判有效、6 有无效/不确定差异；24 个来源 reference 单位；9 个关系对有一致类型，系统匹配 6/9。研究材料绑定到原始会话，`recheck-analysis-20261027/analysis.json` | 候选条件精确率 21/21 只针对 21 个已决定候选，不是全部 27，也不证明完整全原文金标准。6 个 reference 覆盖项待定，故完整提取 Recall 不能算；9 对不是全量关系数据。|
| Auditor | A 一致 30/36，检测 TP27、TN3；B 一致 71/72，TP27、FP1、FN8、TN34，1 自动 uncertain；B decided recall 27/35，含 uncertain reference recall 27/36。完整的分母、分类、适用范围见 `PHASE_4_REVIEW_METRICS_2026-10-27.md` | 小样本、题目有效性不确定、部分分歧；复核阶段看过双方首轮判断。原文件自述 AI 辅助/非独立，用户后称标错并代为更正；原声明与更正均存档，未独立认证。不得把这些数字说成独立盲审、代表性 held-out 或 100% 全部准确。|

实验失败 ≠ 未执行：B 的 Weak 多次失败和 Release20 摘要不达线应保留；Strong 高/低分本身不证明 Auditor 有效或无效。A/B/C 是真实已执行研究/工程样本，但上述正式可信度条件未全部满足。Phase3 reserved cases 改了实体但沿用模板族；A 部分后期题目和反馈已用于 debug，不能再称未知 held-out。后期 v65 分类器用相同 A 答案评估属于开发性重评。未找到可据以证明 pilot 阈值在完整 held-out 开始前冻结并可执行的独立证据；`protocol.json` 的 B success_threshold 为 null。原分数、失败及恢复链应分别保存。C 的 LongMemEval 筛选规则在回答前冻结，但这不自动满足人工独立性或代表性。

## 5. 提交包、复现与归属

- `README.md`、`docs/DEVELOPMENT.md`、`.env.example`、`docker-compose.yml`、数据库 Alembic 迁移与 `backend/requirements.txt` / 前端锁文件存在。README 部分模型默认描述需要以实际配置复核。当前 DB healthy，但未做全新机器、空数据库、无密钥的最终包端到端复现；实际 OpenRouter 使用需自备服务凭证，不能把历史可用性视为长期可用。
- 打包脚本 `scripts/package_assessment_source.py` 现已显式包含报告复现所需的 `scripts/phase4_review_form.js`，同时仍排除任意未审查 JavaScript；`scripts/tests/test_proposal_package_scope.py` 检查了这项 allowlist、逐文件哈希和私有文件排除。打包范围仍排除 `artifacts`、`output`、`experiments`、数据库、`.env` 和私有评审返回，报告中的原始研究数据仍通过独立证据目录引用。重生成 ZIP 后应复核清单/哈希；许可证、同意声明和贡献记录仍须人工确认，轻量 secret-pattern 检查也不是全仓库隐私认证。
- 本地可复算的 LongMemEval C v5 包含目标回答、固定问题子集、评分请求/响应、失败请求、分析脚本、上游 scorer 绑定和来源 license/revision。A/B 最新原始回答和 Phase 4 metrics 仍缺失。部分请求正文是依据保存的来源/模板**重建后对照原 HTTP SHA**，不是原始完整网络包；人工复核记录的来源和更正必须同结果一起保存。正式证据包需检查复现脚本对原始路径、外部数据、环境和授权的依赖。
- 贡献：Proposal 第 9.1 节为职责分工，不自动等于实际完成量；成员应核对实际提交、设计、审核和声明。Open-source 依赖、LongMemEval 数据与评分脚本、Mem0 等用到的许可证/引用和 GenAI 辅助要逐项核对；本轮未做全仓库版权/相似性审计。历史与实验数据如含私人信息必须经人工审查后再共享。

## 6. 剩余必要任务（P0/P1/P2）

P0 是提交可复现、主流程版本对应或核心结论可信的阻塞；P1 是可信度/评分改进，不妨碍范围受限且诚实的报告；P2 暂缓。

| ID | 具体任务 | 当前缺口 | 为什么影响交付/报告 | 优先级 | 前置依赖 | 完成标准及证据 | 人工参与 |
|---|---|---|---|---|---|---|---|
| R1 | 选择最终源码快照并冻结 | 20 tracked 修改、42 untracked，revision 标记 development | 源码、演示和证据必须可对应 | P0 | 团队确定最终版本 | 导出含新增文件的不可变源码快照，commit/tag 或完整 manifest+dirty patch、SHA、依赖与记录时间；分别绑定已有历史版本 | 是：团队确认范围；不要求本轮推 main |
| R2 | 在隔离环境按 lock 重装前端并验证 | 运行 Vitest 5.0.1/Vite 8.3.0 与 lock 5.0.5/8.3.5 不符 | 防止提交包不能复现已测 UI | P0 | R1；本地可用依赖/镜像 | 干净容器执行 lock 安装、typecheck/build、相关或完整测试，保存实际版本、命令、通过/失败与源码 SHA；不碰正式 DB | 可自动执行，若需网络/权限按实际说明 |
| R3 | 同一最终源码绑定主流程证据 | 真实 8 回答 E2E 是 v63/v26/v27/v42，后续 5 文件变化；同 run 未存截图 | 若报告声称最终版实测，须对应版本；用户演示需要证据 | P0：仅对该声明；如明确采用旧快照并披露差异可降级 | R1/R2、授权合成输入、可用模型 | 选一种：隔离真实运行 Upload→review→4维 test→target→evaluate→Dashboard→JSON/CSV，记录配置、请求/响应、同 run 截图/哈希；或限定旧版 E2E、列新差异并做不调用模型回归 | 是否执行付费实跑需用户确认；人工 review 与演示截图需参与 |
| R4 | 修正提交包选择和检查 | `.js` 审核表脚本及 Phase3/4 数据、所有产物被旧打包器排除；尚未扫描最终输出 | 引用的证据/工具不可复现，可能错误包含敏感信息 | P0 | R1；确定允许提交数据和许可 | 形成安全源码包+允许公开的最小证据包/清单（或可复现取得方式）；包含必需 JS/fixtures 与来源许可；全包路径、哈希、敏感数据和可启动检查 | 是：数据许可及敏感内容核对；脚本修补/生成可后续执行 |
| R5 | 组员核对贡献、源码/资料许可和来源说明 | Proposal 只是计划分工；人工复核原声明与用户更正不同 | 团队贡献、第三方归属和结果来源需可辩护 | P1，若申报已确认的具体事实则为 P0 | 可与 R1–R4 并行 | 成员逐条确认实际工作、review 身份/来源、更正理由；整理使用的 licence/引用和授权记录。不得把复核写成独立盲审 | 是 |
| R6 | 结果来源与不确定项的诚实定稿口径 | 13/48 问题不确定，A/B 有答案分歧，FDR/Recall 边界 | 防止结果被写成完整正式检验 | P1；若报告需声称正式达标则为 P0 | 现有记录；必要时实际裁决 | 采用 `PHASE_4_REVIEW_METRICS_2026-10-27.md` 分母和缺失项，保留 34 项/来源更正；不得用 AI 强行补标签 | 由成员确认争议；统计与证据核对可自动 |
| R7 | 可选补独立人工或预冻结 held-out 研究 | 独立人工来源、完整原文提取 reference、阈值与盲审未证明 | 可增强 AC1/AC3 和假设检验，但原型可如实报告未完成 | P1 | 审核规范、可用评审和新 held-out/freeze | 双评审原始文件与独立声明、未看评分的裁决、来源绑定、完整 reference、混淆矩阵与未决数量；不得将复核当独立首轮 | 必须真实人工，不自动生成标签；如需新模型调用先单列预算 |
| R8 | 可选检索历史 Release20/Harbour | 旧原始目录缺失 | 仅影响使用这些特定历史数据的主张 | P2；若坚持作核心证据则变 P0 | 旧运行者/备份 | 原始 requests/responses、run IDs、评分与导出、hash 对得上；否则只留摘要或不引用 | 是：持有人寻找 |
| R9 | 泛化强化、新基准全量/更高分 | 语言边界、样本规模和 C14 限制 | 增加研究深度，但不应在提交前无限扩展 | P2 | 已冻结方案和额外预算 | 仅在团队选择扩展时设计预冻结数据；不覆盖历史、无降阈值 | 可能需要评审/云费；本轮不做 |

付费估计边界：最小四维双策略 E2E 如复用既有结构，约 **8 次 target 回答**，可能另有提取、出题和 AI judge 调用（例如每题评审 8 次，附加步骤和重试依实际方案确定）；最终用量不能在未选设置时准确估算。此前 8 次 target 历史估计约 US$0.0016245，非账单、非未来价格保证，也不含新 AI pipeline/重试。R7 全面新盲审或独立 held-out 的调用量取决于新冻结设计，当前不能假定。**本轮未自动启动这些操作；先列具体方案、前置条件及费用并取得确认。**

## 7. 最短完成路径与停止条件

1. **先确定交付口径和冻结版本（R1）**：确认哪些是真实结果、哪些明确为 pilot/未完成；导出源码和配置指纹。无需推 main 才能生成可检查快照。
2. **并行进行 R2 与 R4/R5**：前端 lock 干净复验；审核 source package、最小证据和许可；组员确认实际贡献与人工标注来源。R2/R4 不要求修改研究数据，R5 需要真人。
3. **决定是否需要最终版真实 E2E（R3）**：若要说最新源码完整流程已实跑，必须先冻结、明确模型成本并获确认，再做受控一次；如果限定旧版实跑及后续差异，可继续报告而不重复付费。新截图需绑定 run/版本。盲评 cap 真机测试仅在报告声称它已实测时补充。
4. **整理已有证据和分析（R6）**：A/B/C 的失败、未测项、分母与来源直接按当前证据入报告；争议不强行解决。团队若希望正式声称 AC1/AC3 达标或独立 FDR，再选择 R7 并等待真实独立标注/裁决。
5. **最终 source/evidence 包检查后定稿**：可对允许公开的数据运行离线复算，检查报告每个主张链接到同一 run、版本、原始证据；不修改或伪造历史。

必须修代码与只补证据区分：当前未发现足以断定主流程业务代码必修的新 P0 Bug；R4 若选择使用现有打包器，需要调整打包选择或采用独立受控证据打包流程。R2 是环境重建，不改业务代码；R3 是运行/证据；R5/R7 是人工事实与研究工作。盲评 cap 当前是已实现且契约测试通过，真实 provider 使用证据仍缺，不应重新宣布为“尚未实现”。

可停止优化的条件：选定快照与锁文件相符且可启动；核心路径有对应版本的真实证据或明确旧版边界；最终包可定位允许的来源/运行/计算、无已发现的秘密；团队确认贡献和资料归属；报告将规则、真实模型、历史、开发和正式评估分开，并列出未决和失败；不把小样本/未独立标签夸大为通过全部 AC。无需找到所有旧文件、让每个自动答案通过、消除所有 abstention、跑完整 500 样本或追求任意高分。

## 8. 报告内容可用性

**现在有依据可以写：** 实际系统模块/四维设计及受限 scope；规则模式与可配置模型结构；Phase1/2 原版 8 次 Luna E2E 真实请求与导出及其五文件版本差异；经本轮哈希核对的 2738+8 后端测试；A 36、B 72、C 84 实际目标回答及自动结果、预算与限制；Phase3 合成对照与真实 replay 的有限证据；具体失败和 uncertainty。

**等 R1–R6 后再定稿的核心事实：** 最终源码版本、当前锁文件环境可运行性、是否可声称最新版本完整 E2E、最终交付包 SHA/许可/隐私、成员实际贡献与审核来源。正式独立 precision/recall/FDR 或 AC1/AC3 达标只能在真实满足 R7 及协议条件后写；否则报告为未完成、给出描述性分母。

**应保留而不值得粉饰的局限：** A 问题歧义和冻结缺陷覆盖不足；两位复核阶段非盲、来源声明冲突及用户报告的更正；B 样本少且相似，随机 seed 未实发；C 是 14/500 Oracle 兼容子集而非完整官方基准；规则和 LLM pipeline 区分；Release20/Harbour 原件缺失及摘要失败；owner/semantic 泛化与 novice usability 未充分验证。以上不等于系统必然有 Bug，也不等于目标 75% 的研究阈值是课程分数要求。

### 27 October reviewer follow-up intake

Two more review artifacts were supplied, but neither establishes independent
human labeling. `review2-result(1).json` declares Codex as the AI-assisted
reviewer, `completed_by_human: false`, and references a material hash for which
the matching material was not supplied. The 40-item Chongtai recheck archive
passes its structural/reference checks but declares that Codex prepared it,
no human completed it, and the first-round judgments and prior AI analysis had
already been seen. It records 19 changes and 29 uncertain items. The archive's
state for `R-23b35e11a5783061` conflicts with the feedback pasted in chat; keep
both versions pending human adjudication. See
`docs/proposal-experiment-audit.md` and the local intake manifest for exact
hashes and scope. Do not count these items as the two independent blind
returns required for formal validation.
