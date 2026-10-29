# 双人 JSON 审核回传核对（离线）

核对前保留两份空白模板不动。若模板没有 `frozen_defect_inventory_by_history` 和 `additional_missing_facts`，请用增强后的生成器输出到一个**新目录**，不要覆盖已发出的审核包：

```sh
python3 scripts/prepare_multi_reviewer_json.py \
  --output output/proposal-delivery/multi-review-readable-new \
  --reviewers 2
```

生成器会同时保留协调人专用的只读空白模板 `templates/reviewer-N.json`，以及发给审核者填写的副本 `reviewer-N.json`。回传后，将两位审核者文件分别另存为新文件；核对时，`--template-a/b` 指向 `templates/` 下的原始模板，`--return-a/b` 指向审核者回传件：

```sh
python3 scripts/reconcile_multi_reviewer_json.py \
  --master output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json \
  --manifest output/proposal-delivery/multi-review-readable-new/manifest.json \
  --template-a output/proposal-delivery/multi-review-readable-new/templates/reviewer-1.json \
  --return-a /path/to/completed-reviewer-1.json \
  --template-b output/proposal-delivery/multi-review-readable-new/templates/reviewer-2.json \
  --return-b /path/to/completed-reviewer-2.json \
  --output output/proposal-delivery/private-adjudication-new.json
```

工具核对 master、manifest、空白模板哈希、各 item 身份、来源转录、A/B 冻结缺陷清单，以及回传文件是否只改了允许填写的字段。它按队列和主要判断字段统计双方完成、缺失、不确定、一致和分歧，保留两份实际 review、reviewer 声明、manual confirmations 与 `additional_missing_facts`。所有仍待处理的 item ID 会列在 `unresolved_items`；额外遗漏事实按 history 单独列出。

### 单份 A/B 审核导出到 Phase 4 格式

若需将一位审核者已完成的 A/B JSON 副本转成现有 `phase4-complete-review-v1` 格式，使用独立的离线导出工具。`--phase4-material` 要与审核者使用的正式 Phase 4 material 指纹相符；`--phase4-key` 是协调人私有文件。例：

```sh
python3 scripts/export_multi_reviewer_phase4_complete_review.py \
  --master output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json \
  --manifest output/proposal-delivery/multi-review-readable-new/manifest.json \
  --template output/proposal-delivery/multi-review-readable-new/templates/reviewer-1.json \
  --return /path/to/completed-reviewer-1.json \
  --source-material artifacts/local/phase4-formal-review-20261027/reviewer-1/material.json \
  --phase4-material artifacts/local/phase4-formal-review-20261027/reviewer-1/material.json \
  --phase4-key artifacts/local/phase4-formal-review-20261027/private/key.json \
  --output artifacts/local/phase4-formal-review-20261027/reviewer-1/exported-result.json
```

导出会按 item ID 复制 A/B review 字段与 `additional_missing_facts`，原样映射审核者声明中的布尔值，并调用现有 `phase4_formal_review.validate`。目标格式要求 `completed_by_human=true`、`completed_independently=true`；若审核者实际填的是 false、缺失值或不完整标签，工具会拒绝导出，不会改写声明或补答案。审阅者声明仍是自报信息，工具不认证身份或独立性。来源格式无法容纳的完成时间、声明备注和 `manual_confirmations_zh` 会保存在同目录的私有 `.provenance.json` sidecar 中。导出只新建本地私有文件，不会导入系统或改动原件。

如果模板包含 v7 答案审核队列，核对或 A/B 导出时还需加上协调人保管的 `PRIVATE-v7-identity-key.json` 和对应 v7 结果目录：`--private-key <路径> --v7-dir <路径>`。工具会逐项核对私有映射、冻结 run/protocol/subset 哈希、回答哈希、question date 和含 session date 的来源转录；回传的 v7 review 只接受 Pass、Fail、Uncertain 或空值。不要把私有映射发给审核者。

裁定文件以仅文件所有者可读写的权限新建；同名文件已存在时拒绝覆盖。工具不修改 master、模板或回传文件，不替审核者裁定，也不认证审核者身份或独立性。一致只记录为一致，`adjudicated_value` 始终留空。
