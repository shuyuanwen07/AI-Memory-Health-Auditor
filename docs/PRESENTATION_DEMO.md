# Harbour：一组可展示、可复现的记忆审计

**真实运行已完成：6次运行、48条回答、48条评估；独立验证器PASS，完成48项实际输入核对。**

[直接打开实验组](http://localhost:5173/experiments/EXPD9C66FE3D5F946998AF5A8A0A3B272C9)
实验组ID：`EXPD9C66FE3D5F946998AF5A8A0A3B272C9`

## 展示顺序

1. **New audit：看原始对话。** 默认Harbour示例共28轮、5603英文字符；`Download example JSON`与默认输入使用同一JSON。若页面恢复了旧草稿，可点`Load presentation example`。加载示例不会调用模型，处理授权仍需由操作者确认。
2. **看候选与审阅入口。** 展示实际提取候选、来源消息、编辑和确认步骤。本次采用18条有精确来源的**工程作者合成参考**，不是独立人工金标准，不得把脚本参考导入说成人工逐条批准。
3. **看关系。** 参考中有2条UPDATE、2条CONFLICT、2条CONTEXTUAL_OVERRIDE：旧安排被明确替换、仍有效文件的未决冲突，以及项目要求覆盖一般偏好的适用范围。助手未被采纳的建议不能变成用户决定。
4. **同题看弱强回答。** 两个条件使用同一OpenRouter GPT6Luna基础模型；8道冻结题，每维2道，Weak与Strong各重复3次。比较同一道题的实际回答，不只挑最好一次。
5. **看四维结果。** Accuracy、Freshness、Conflict Resolution、Appropriate Use分别展示得分、已判定数量及不确定数量。不能把受维度未决影响的macro-average当成“全部8题正确率”。
6. **展开失败，追到原文。** 从实际问题、回答和自动评估理由，追到来源消息及目标记忆轨迹；区分“原文存在”“写入/保留”“检索到”“确实发送”。自动通过不等于来源安全，来源复核也不改写原自动分数。
7. **下载原始记录。** 实验组内可下载`Results table (CSV)`、`Answer report (JSON)`、`Reproduction package`及`Fixed test materials`，保留原问题、回答、评估ID和未决结果。
8. **区分重看与重跑。** 打开上方链接是查看已保存原组，不产生新模型回答。重新执行同冻结题会创建新组、产生调用费用和新输出，不能覆盖原结果，也不能重新生成类似题后称为同题复现。

## 已测结果

下表每格依次为 **通过 / 失败 / 不确定**，每轮每条件8条。

| 重复 | Weak | Strong |
| --- | --- | --- |
| 1 | 1 / 6 / 1 | 5 / 0 / 3 |
| 2 | 1 / 7 / 0 | 3 / 2 / 3 |
| 3 | 1 / 5 / 2 | 5 / 2 / 1 |
| 合计 | **3 / 18 / 3** | **13 / 4 / 7** |

Strong不是100%通过；不确定结果原样保留，不计作通过。这是一组工程演示，不是新benchmark或普遍优越性结论。固定seed42也不保证下次采用相同措辞或得到相同分数。

**恢复记录：** 首次coverage planner请求上限512时输出截断，当时尚有0条目标回答。原失败记录保留；planner修为v21、最小输出预算2048，服务pipeline cap设8192后，在同一组恢复生成并完成运行。这不是对已有成功回答或分数重试择优。

## 文件与同题重跑

- 素材：[对话](../datasets/demo/presentation-memory-v1/conversation.json)、[工程参考](../datasets/demo/presentation-memory-v1/curated-inventory.json)、[设置](../datasets/demo/presentation-memory-v1/settings.json)。默认镜像：[presentationDemo.json](../frontend/src/data/presentationDemo.json)。
- 结果归档：[result/](../experiments/presentation-demo-20261023/result/)：`presentation-demo-report.json`、`experiment.bundle.json`、`experiment.csv`、`verification.json`、`frozen-test-suite.json`。
- 首次失败与修复记录保留在[演示证据目录](../experiments/presentation-demo-20261023/)，不能由完成结果取代。

如确实需要再次执行，在仓库根目录使用**原运行仍所在的同一个backend数据库**，使用最终repeat guard版本脚本，另选一个尚不存在的输出目录：

```bash
docker compose exec -T backend python /scripts/run_presentation_demo.py \
  --source /datasets/demo/presentation-memory-v1 \
  --output /app/.engineering-smoke/presentation-demo-v1-repeat1 \
  --base-url http://127.0.0.1:8000 \
  --repeat-from-report /app/.engineering-smoke/presentation-demo-v1-generation-recovery1/presentation-demo-report.json \
  --execute
```

此命令会实际调用模型。脚本须先核对原数据库、来源、参考、设置与冻结题，再创建新的6次运行组并使用原8题；不重新提取或生成题目。仅复制结果JSON不能恢复数据库实验组，数据库不匹配时应停止。演示保持额外回答校验关闭；不要为观看结果重新运行此命令。
