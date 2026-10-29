# 将基线审核进度迁入含 v7 的审核包

这一步用于在审核者已经填写 686 项基线材料、而 v7 答案审核队列稍后才生成时，继续使用同一份审核进度。工具只读取旧回传文件，并在新位置建立合并版回传件；不会覆盖旧回传件、任一空白模板或审核包。

每位审核者分别运行一次，并保持 reviewer slot 对应：reviewer-1 的旧回传只能迁入 reviewer-1 的合并模板，reviewer-2 同理。`--baseline-template` 和 `--combined-template` 都必须使用协调人保留的 `templates/reviewer-N.json`；审核者的填写内容使用 `--baseline-return` 单独传入。

示例（将尖括号占位路径换成合并审核包实际路径和回传文件路径）：

```sh
python3 scripts/transfer_multi_reviewer_progress.py \
  --master output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json \
  --baseline-manifest output/proposal-delivery/multi-review-ready-2026-10-28/manifest.json \
  --baseline-template output/proposal-delivery/multi-review-ready-2026-10-28/templates/reviewer-1.json \
  --baseline-return /path/to/reviewer-1-baseline-return.json \
  --combined-manifest <combined-packet>/manifest.json \
  --combined-template <combined-packet>/templates/reviewer-1.json \
  --private-key <combined-packet>/PRIVATE-v7-identity-key.json \
  --v7-dir <frozen-v7-run-directory> \
  --output output/proposal-delivery/reviewer-1-combined-return.json
```

工具会分别验证旧模板、合并模板、manifest、master、A/B 冻结 defect inventory，以及 v7 私有身份映射和冻结 run/protocol/subset。只迁移审核者声明、基线 item 的现有 `review`、A/B `additional_missing_facts` 和授权的 `manual_confirmations_zh` 填写。输出沿用合并模板的来源、槽位和 provenance；所有 v7 `answer_judgment` 保持空白。工具拒绝不匹配的 reviewer slot、已变更来源内容、额外 review 字段、非授权手工改动以及任何覆盖写入。

成功后生成一个新的私有 JSON 回传件，以及同名 `.provenance.json` sidecar，记录两版模板与回传件哈希、v7 来源哈希、迁移项数和输出哈希。该流程不证明审核者身份或独立性，也不裁定任何标签。迁移后的回传件可作为新合并审核包的 `--return` 输入进行完整核对。
