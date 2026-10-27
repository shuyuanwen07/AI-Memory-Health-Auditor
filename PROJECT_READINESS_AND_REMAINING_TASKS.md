# AI Memory Health Auditor：最终报告准备度与剩余任务

检查日期：2026-10-27（Australia/Sydney）。范围：当前工作区源码、运行容器、Proposal、课程 A2、旧审计与之后的保存证据。本轮只读核查并运行隔离定向测试，没有修改业务代码、依赖锁、`.env`、正式数据或 Final Report，没有执行付费模型调用。

## 判断：B — 基本具备，冻结和最终定稿前有少量明确阻塞

可以立即开始整理架构、实现、实验方法、初步结果及局限的报告草稿。提交版定稿前需要：确定并冻结实际源码和运行环境；处理运行前端依赖与锁文件不一致；形成可检查的源码及经过授权筛选的证据包；核对团队贡献、第三方归属及拟引用结论。当前尚无后续 v65/v28 源码的同一条真实 Upload→Export 完整运行记录；如果报告要声称最终版真实端到端已验证，必须补一次受控实跑或使用绑定旧版本的现有证据并明确版本差异。正式独立可靠性和完整 A 缺陷发现率不能宣称完成，但课程 A2 并不要求删除所有失败或把研究假设证明为真；如将其标为未完成、保留限制，可以据实交付原型，而不必无限期等到研究指标全部达标。

课程材料：`/Users/yichaowang/Downloads/ELEC5623_A2.pdf`（5 页；开发 20 分，截止 11 月 3 日 23:59；演示和 Q&A 10 分，11 月 4 日，现场禁用 AI）。Project Development 分项为功能与实现 4、GenAI 与架构 4、评价与分析 4、相关工作与创新 3、Track 对齐 2、产品体验 2、文档与团队 1。提交源码和报告两项，源码应可检查、含设置与占位符、无秘密，报告建议 8–12 页不含参考及附录。批准 Proposal：`../ELEC5623_Group2_Proposal.pdf`，Track B，FR1–12 / NFR1–5 / AC1–5、三组实验和四维指标。课程要求诚实论证、基线与局限，不规定 Release20 自设 75% 为课程及格线，也不要求复现全部历史原件。旧基线：`output/evidence-audit/FINAL_REPORT_EVIDENCE_AUDIT_2026-10-27.md`；其 A/B/C 缺失和前端启动失败结论已被之后证据部分更新，不能当作现状。

证据等级：**实现**＝代码可定位；**实测**＝有绑定版本的执行/测试证据；**历史**＝真实但属于旧快照；**摘要**＝缺原始记录；**未验证**＝不证明有 Bug；**人工待确认**＝不能由软件或 AI 自行证明。下面不以存在测试源码代替测试通过，也不把规则模式说成 LLM 模式。

## 1. 当前版本、配置与检查结果

- 分支 `codex/owner-c-validation`；HEAD `b44ced90ea39eb569eaa6ea01dee4c3df5712085`。检查时 20 个 tracked 修改、42 个未跟踪文件；包括业务源码、测试、锁文件、Compose 和研究脚本。HEAD 不等于完整被测工作树；尚无此次最终干净提交或正式 tag。`git diff --check` 通过。
- Docker Compose 的 backend/frontend 正在运行，PostgreSQL healthy；容器内 `GET /api/v1/health` 返回 200 且 database ready。后端/前端 bind mount 分别映射当前源码目录；后端采用 Uvicorn reload。后端容器磁盘上的 `rule_based.py` 哈希与本地和 Phase 4 follow-up manifest 一致，但仅凭 bind mount/文件哈希不能证明运行进程每个模块都已重载，冻结时仍需实际进程/版本收据。`AUDITOR_CODE_REVISION=development`，并非发布版本。
- 容器环境当前 `PIPELINE_PROVIDER=rule_based`、`EVALUATOR_PROVIDER=rule_based`，`OPENROUTER_DEFAULT_MODEL` 和 `PIPELINE_MAX_OUTPUT_TOKENS` 环境变量未设置；代码 OpenRouter 模型回退为 `openai/gpt-6-luna`，实际 target provider/model 由每次运行配置决定，不能仅由该默认值断言本次运行目标。按当前代码：rule evaluator v65、rule generator v28、extractor v27、target controlled-memory-v35、policy v43。Phase 4 A/B/C 历史实际 provider/model 为 OpenRouter `openai/gpt-6-luna`，规则评估 v64；C 的 GPT-4o judge 为单独设置。默认规则流水线不证明 LLM extraction/generation/judging 的当前实际执行。
- 运行前端 Node 22.22.2 / npm 10.9.7；容器实际 Vite 8.3.0、Vitest 5.0.1，而当前 package manifest 和 lock 分别为 Vite 8.3.5、Vitest 5.0.5（TypeScript 均 5.7.3）。本轮 26 项前端定向测试确实通过，但使用的是当前容器实际安装版本，不能称为锁文件版本的运行验证。需要在不影响正式数据的环境按锁文件重建验证并记录版本；本轮未执行 npm ci。
- 较早完整测试：Phase 4 follow-up 后端日志 **2738 passed、8 skipped、1 warning**；8 个 PostgreSQL 项在隔离迁移测试库 **8 passed**。对 follow-up manifest 的 137 个后端源码文件，本轮逐一核验 **137/137 哈希一致**，说明该后端测试证据对应当前这些源码，具体日志 `artifacts/local/phase4-followup-20261027/backend-full.log`、`postgres.log`。不说明当前容器依赖或整棵工作树与测试机完全相同。此前前端记录 **581 passed/62 files**，`artifacts/local/phase12-20261027/frontend-full.log`；当前容器依赖不一致，不能升级为本轮当前锁文件全量结果。
- 本轮隔离检查：`scripts/run_offline_backend_tests.py` 对 blind judge cap、Phase3 和 Phase4 follow-up **75 passed**（SQLite 临时库，外部 socket blocked attempts 0；证据 `/private/tmp/mha-readiness-20261027/isolated-suite-vvswoji5/isolation-evidence.json`）；`python3 -m unittest discover -s scripts/tests -q` **57 passed**；当前容器两个前端文件 **26 passed**。真实 provider 未被调用。这个定向结果不是重新运行的后端/前端全套。
- 来源版本：Phase1/2 端到端 source manifest 20 个受记录文件中 15 同哈希、5 已变化：`backend/app/api/routes.py`、`evaluator/rule_based.py`、`extraction/rule_based.py`、`test_generator/rule_based.py` 和一个测试文件。Phase4 冻结 app source 136 文件中 132 一致、4 已变化（evaluator、baselines、rule generator、domain schema）；现有后续同答案重评 v65 与原结果分别保留。截图方面 Phase1/2 UI receipt 明确 `screenshots_saved: false`；有 Safari 观察与浏览器导出记录，不能称有该次截图。

## 2. 已完成且不必重复的任务：原问题 → 状态 → 修复与证据

| 原问题 | 当前状态和修复位置 | 核验和边界 | 后续 |
|---|---|---|---|
| Rolldown binding / 前端测试启动失败 | Compose 为 Linux 容器隔离 `frontend_node_modules`；锁文件已更新 | Phase1/2 581 passed；本轮 26 passed。但当前安装的 Vite/Vitest 与锁文件不同 | **不再列为同一启动 Bug；**按锁文件重建并验证最终环境 |
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

AC1：关系和提取有人工记录/限定人工复核，但完整独立标注来源、全原文 gold 和最终语义裁决不足，**不能声称正式通过**。AC2：生成题可执行、部分通过 grounding，但 13/48 审核题仍不确定，不能证明所有无未支持事实。AC3：没有可核验独立盲审且预先冻结 pilot 阈值的 held-out 全套指标，**未证明达标**。AC4：旧快照四维报告及 source/export 的工程路径完成；当前版最终截图/配套 run 待绑定。AC5：B 使用相同问题及三重复并保留配置，实测能力有证据；provider 实际 model-default sampling，temperature/seed 未发送，随机种子不能声称生效，输入等同性和记录不等于输出可逐字复现。

权限/安全：代码实现授权与服务端凭证、目标/审计器隔离及基本安全合同；现有测试不等于完整渗透测试或身份鉴权认证。`.env` ignored，敏感材料位于 ignored 目录。最终包需对实际将发布的内容做扫描与人工授权核验，本次未对全部隐私/二进制做认证。FR/NFR 全量原始定义与具体历史映射可参考 `docs/REQUIREMENT_TRACEABILITY_MATRIX.md`，但其中旧版本状态必须以本文更新为准。

## 4. 实验状态总表

| 项目 | 实际完成及可报告内容 | 不能声称 / 仍缺内容 |
|---|---|---|
| A 三方法 | `artifacts/local/phase4-20261027/A-live.json`：3 个合成历史 × 3 方法 × 4 题 = 36 个真实目标回答；同源、相同目标与 evaluator、相同预算；预先确定每历史 3 个潜在缺陷 ID 和发现去重单位。原始回答、9 个导出、请求 SHA、人工批准声明存档。最终复核的描述性指标参见 `output/engineering-verification/PHASE_4_REVIEW_METRICS_2026-10-27.md` | 不能声称上下文方法显著胜出或正式完整 FDR；多个原题存在当前/历史或后端范围歧义；原冻结缺陷定义不覆盖全部“遗漏/不知道”。人审有更正 provenance 和复核看过首次判断，6 个 A 回答未一致。题目有效性与独立 reference 不完整；原有 category 4/4 是按预执行批准和指定类别的覆盖，后续 13 题不确定不能无条件宣称经独立证实。此实验为规则/模板配置，不能写成实际大模型 Agent 三臂对比。 |
| B Weak/Strong | `B-live.json`：3 个相似合成历史 × 4 个共享问题 × 2 检索策略 × 3 重复 = 72 个真实目标回答。相同 Luna、Strong reader、规则 writer、50 记录/16000 字符/2048 输出上限；有效温度和 seed 为 model default。旧 v64 自动宏均值 Weak 25%、Strong 97.22%；Weak 9/27/0，Strong 34/1/1（pass/fail/uncertain）；Strong 三次宏结果 100/100/91.67%，SD 3.93 个百分点 | 只有三组模板相关历史，不是独立人群或泛化证明；Strong 给出更多记忆内容，检索差异不等于模型变化；失败和 uncertain 原样保留。关键错误人工评审有未定项；当前 v65 对既存答案重新评估不新增目标调用且 verdict 不变，不等于全套当前版重跑。|
| C LongMemEval | `C-live.json`、`longmemeval-subset.json`、`upstream/source-binding.json`：官方 Oracle 500 中预选 14 ID、7 类 × 2，2 策略 × 3 重复 = 84 真回答和 84 judge 结果；Weak 15/42、Strong 30/42；与 B 相对排序 3/3 一致 | 本地兼容 Oracle 子集、适配及 OpenRouter grader transport，非官方完整 S/M benchmark；重复复用题目，3/3 非三个独立外部研究；无独立 judge 校准。来源数据及 upstream LICENSE 现已保存，旧审计“全部缺失”过时。|
| Extraction / relations | 27 个候选：21 双方判有效、6 有无效/不确定差异；24 个来源 reference 单位；9 个关系对有一致类型，系统匹配 6/9。研究材料绑定到原始会话，`recheck-analysis-20261027/analysis.json` | 候选条件精确率 21/21 只针对 21 个已决定候选，不是全部 27，也不证明完整全原文金标准。6 个 reference 覆盖项待定，故完整提取 Recall 不能算；9 对不是全量关系数据。|
| Auditor | A 一致 30/36，检测 TP27、TN3；B 一致 71/72，TP27、FP1、FN8、TN34，1 自动 uncertain；B decided recall 27/35，含 uncertain reference recall 27/36。完整的分母、分类、适用范围见 `PHASE_4_REVIEW_METRICS_2026-10-27.md` | 小样本、题目有效性不确定、部分分歧；复核阶段看过双方首轮判断。原文件自述 AI 辅助/非独立，用户后称标错并代为更正；原声明与更正均存档，未独立认证。不得把这些数字说成独立盲审、代表性 held-out 或 100% 全部准确。|

实验失败 ≠ 未执行：B 的 Weak 多次失败和 Release20 摘要不达线应保留；Strong 高/低分本身不证明 Auditor 有效或无效。A/B/C 是真实已执行研究/工程样本，但上述正式可信度条件未全部满足。Phase3 reserved cases 改了实体但沿用模板族；A 部分后期题目和反馈已用于 debug，不能再称未知 held-out。后期 v65 分类器用相同 A 答案评估属于开发性重评。未找到可据以证明 pilot 阈值在完整 held-out 开始前冻结并可执行的独立证据；`protocol.json` 的 B success_threshold 为 null。原分数、失败及恢复链应分别保存。C 的 LongMemEval 筛选规则在回答前冻结，但这不自动满足人工独立性或代表性。

## 5. 提交包、复现与归属

- `README.md`、`docs/DEVELOPMENT.md`、`.env.example`、`docker-compose.yml`、数据库 Alembic 迁移与 `backend/requirements.txt` / 前端锁文件存在。README 部分模型默认描述需要以实际配置复核。当前 DB healthy，但未做全新机器、空数据库、无密钥的最终包端到端复现；实际 OpenRouter 使用需自备服务凭证，不能把历史可用性视为长期可用。
- 打包脚本 `scripts/package_assessment_source.py` 的 `allowed()` 本轮仅做静态审计：包含 Python/TS 等源码及部分 fixtures，但**排除所有 `.js`**，其中 `scripts/prepare_phase4_complete_review.py` 运行时读取的 `scripts/phase4_review_form.js` 因而缺失；还排除 `datasets/phase3-engineering-v1`、`datasets/phase4-candidate-v1`、`artifacts`、`output`、`experiments` 和根目录本盘点文件。报告若引用这些实验、审阅工具或原始证据，仅运行旧打包器无法复现。是否提交允许的合成子集、数据许可和必要脚本须由团队检查并建立独立 evidence manifest；不要把 private reviewer keys、运行 DB、`.env` 或未经授权数据直接打包。此轮未生成对外交付包，也未证明全包无秘密。
- 长期证据目录包含原始 A/B/C 回答、固定问题、输入、运行设置、失败、request-hash 验证、分析脚本、LongMemEval 原文件、license/revision 绑定。部分请求正文是依据保存的来源/模板**重建后对照原 HTTP SHA**，不是原始完整网络包；人工复核记录的来源和更正必须同结果一起保存。正式证据包需检查复现脚本对原始路径、外部数据、环境和授权的依赖。
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
