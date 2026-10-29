"""Safely copy completed baseline reviews into a later combined reviewer packet.

This offline utility verifies both packet versions against the same frozen
master. It transfers only reviewer-entered baseline fields into a new combined
return file; any later v7 queue stays exactly as it appears in the blank
combined template.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import reconcile_multi_reviewer_json as validator

FORMAT = "multi-reviewer-progress-transfer-v1"
BASELINE_QUEUES = {"proposal_ab_formal_review_216", "proposal_c_archived_review_84",
                   "proposal_c_v5_review_84", "proposal_c_v6_review_180",
                   "current_source_repair_24", "current_source_six_run_48",
                   "earlier_repair_loop_36", "current_source_intake_candidates_14"}
V7_QUEUE = "four_strategy_v7_answers"
MANUAL_EDITABLE = {"review", "members", "observations"}


def _fail(message: str) -> None:
    raise validator.ReconciliationError(message)


def _require_regular(paths: list[Path]) -> None:
    if any(not path.is_file() or path.is_symlink() for path in paths):
        _fail("所有 master、manifest、模板、回传、私有映射和来源文件都必须是普通文件。")


def _manifest_template_hash(manifest: dict[str, Any], template_path: Path) -> str:
    rows = manifest.get("reviewer_copies")
    if not isinstance(rows, list):
        _fail("reviewer manifest 缺少 reviewer_copies 列表。")
    matches = [row for row in rows if isinstance(row, dict) and row.get("file") == template_path.name]
    if len(matches) != 1 or not isinstance(matches[0].get("sha256"), str):
        _fail(f"manifest 中没有唯一的模板记录：{template_path.name}")
    return matches[0]["sha256"]


def _load_and_validate_packet(master_path: Path, manifest_path: Path, template_path: Path,
                              label: str, formal_material_path: Path,
                              *, combined: bool, private_key_path: Path | None,
                              v7_dir: Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    master = validator.read_json(master_path)
    manifest = validator.read_json(manifest_path)
    template = validator.read_json(template_path)
    if manifest.get("format") != "multi-reviewer-json-v1":
        _fail(f"{label} manifest 格式不是 multi-reviewer-json-v1。")
    if manifest.get("master_sha256") != validator.sha256_file(master_path):
        _fail(f"{label} manifest 未绑定到当前 master。")
    if validator.sha256_file(template_path) != _manifest_template_hash(manifest, template_path):
        _fail(f"{label} 空白模板与 manifest 哈希不一致。")
    defect_inventory = validator._frozen_defect_inventory(master, formal_material_path)
    enriched_master = validator._master_with_frozen_benchmark_enrichment(master)
    master_queues = validator._queue_map(enriched_master, "master")
    template_queues = validator._queue_map(template, label)
    extra = set(template_queues) - set(master_queues)
    if not combined and extra:
        _fail("基线审核模板不应包含额外实验队列。")
    if combined and extra != {V7_QUEUE}:
        _fail("合并审核模板的额外队列必须恰好是已验证的 v7 审核队列。")
    bound = validator._compare_master_template(enriched_master, template, label, extra, defect_inventory)
    v7_identity = {}
    if combined:
        v7_identity = validator._validate_v7_queue(template_queues, private_key_path, v7_dir,
                                                   template.get("evidence_catalog", {}))
        if set(v7_identity) != set(validator._item_map(template_queues[V7_QUEUE], f"{label}/{V7_QUEUE}")):
            _fail("合并模板的 v7 item identities 未与私有映射完整对应。")
        _validate_v7_template_blank(template_queues[V7_QUEUE], label)
        _validate_v7_queue_metadata(template_queues[V7_QUEUE], label, len(v7_identity))
    _validate_summary(template, template_queues, label)
    return master, manifest, template, bound, {"queues": template_queues, "v7_identity": v7_identity,
                                               "enriched_master": enriched_master}


def _validate_summary(document: dict[str, Any], queues: dict[str, dict[str, Any]], label: str) -> None:
    summary = document.get("summary")
    if not isinstance(summary, dict):
        _fail(f"{label} summary 缺失或格式错误。")
    expected_counts = {queue_id: len(queue.get("items", [])) for queue_id, queue in queues.items()}
    if (summary.get("counts_by_queue") != expected_counts
            or summary.get("total_item_records_for_review") != sum(expected_counts.values())
            or summary.get("evidence_catalog_entries") != len(document.get("evidence_catalog", {}))):
        _fail(f"{label} summary 与模板中的队列或来源条目数不符。")


def _validate_v7_template_blank(queue: dict[str, Any], label: str) -> None:
    for item in queue.get("items", []):
        review = item.get("review")
        if (not isinstance(review, dict) or set(review) != {"answer_judgment", "rationale"}
                or review.get("answer_judgment") not in (None, "") or review.get("rationale") != ""):
            _fail(f"{label}/v7/{item.get('item_id')} 不是未填写的答案审核模板。")


def _validate_v7_queue_metadata(queue: dict[str, Any], label: str, receipt_count: int) -> None:
    expected = {
        "queue_id": V7_QUEUE,
        "title": "四策略补充实验：答案审核",
        "status": "待人工审核",
        "review_count": receipt_count,
        "review_instruction": "对照来源和参考答案，将 answer_judgment 填为 Pass、Fail 或 Uncertain，并在 rationale 写明依据。",
        "scope_note": f"已保存 {receipt_count}/360 条答案，最多来自同一批 30 段历史的重复运行；不显示策略、轮次和自动分数。",
        "label_choices": ["Pass", "Fail", "Uncertain"],
    }
    if any(queue.get(key) != value for key, value in expected.items()):
        _fail(f"{label} 的 v7 队列说明与冻结的生成规则不符。")


def _validate_manual_confirmations(template: Any, returned: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(template, list) or not isinstance(returned, list) or len(template) != len(returned):
        _fail(f"{label} manual_confirmations_zh 的条目数量与模板不同。")
    copied = []
    for index, (blank, actual) in enumerate(zip(template, returned)):
        if not isinstance(blank, dict) or not isinstance(actual, dict) or set(blank) != set(actual):
            _fail(f"{label} manual confirmation #{index + 1} 的结构与模板不同。")
        for key in blank:
            if key not in MANUAL_EDITABLE and validator.canonical(blank[key]) != validator.canonical(actual[key]):
                _fail(f"{label} manual confirmation #{index + 1} 修改了授权填写字段之外的内容。")
        item = copy.deepcopy(blank)
        if "review" in blank:
            if not isinstance(blank["review"], dict) or not isinstance(actual["review"], dict) \
                    or set(blank["review"]) != set(actual["review"]):
                _fail(f"{label} manual confirmation #{index + 1} 的 review 字段结构与模板不同。")
            item["review"] = copy.deepcopy(actual["review"])
        if "members" in blank:
            blank_members, returned_members = blank["members"], actual["members"]
            if not isinstance(blank_members, list) or not isinstance(returned_members, list) \
                    or len(blank_members) != len(returned_members):
                _fail(f"{label} manual confirmation #{index + 1} 的成员身份集合与模板不同。")
            members = []
            for member_blank, member_actual in zip(blank_members, returned_members):
                if (not isinstance(member_blank, dict) or not isinstance(member_actual, dict)
                        or set(member_blank) != set(member_actual)
                        or member_blank.get("member_slot") != member_actual.get("member_slot")):
                    _fail(f"{label} manual confirmation #{index + 1} 修改了成员身份或字段结构。")
                member = copy.deepcopy(member_blank)
                for key in ("actual_contributions", "evidence_references", "confirmed", "confirmed_at"):
                    if key in member_blank:
                        member[key] = copy.deepcopy(member_actual[key])
                members.append(member)
            item["members"] = members
        if "observations" in blank:
            blank_rows, returned_rows = blank["observations"], actual["observations"]
            if not isinstance(blank_rows, list) or not isinstance(returned_rows, list):
                _fail(f"{label} manual confirmation #{index + 1} 的 observations 必须是数组。")
            if not blank_rows:
                if returned_rows:
                    _fail(f"{label} manual confirmation #{index + 1} 没有可复制的观察记录模板。")
            else:
                shape = set(blank_rows[0]) if isinstance(blank_rows[0], dict) else set()
                if not shape or any(not isinstance(row, dict) or set(row) != shape for row in returned_rows):
                    _fail(f"{label} manual confirmation #{index + 1} 的观察记录字段与模板不同。")
            item["observations"] = copy.deepcopy(returned_rows)
        copied.append(item)
    return copied


def _validate_additional_facts(base_template: dict[str, Any], returned: dict[str, Any],
                               combined_template: dict[str, Any], label: str) -> dict[str, Any]:
    base_queues = validator._queue_map(base_template, "baseline template")
    returned_queues = validator._queue_map(returned, "baseline return")
    combined_queues = validator._queue_map(combined_template, "combined template")
    copied = {}
    for queue_id in base_queues:
        in_base = "additional_missing_facts" in base_queues[queue_id]
        in_return = "additional_missing_facts" in returned_queues[queue_id]
        in_combined = "additional_missing_facts" in combined_queues[queue_id]
        if (in_base, in_return, in_combined) != (in_base, in_base, in_base):
            _fail(f"{label}/{queue_id} additional_missing_facts 结构与两版模板不一致。")
        if not in_base:
            continue
        baseline_map = base_queues[queue_id]["additional_missing_facts"]
        return_map = returned_queues[queue_id]["additional_missing_facts"]
        combined_map = combined_queues[queue_id]["additional_missing_facts"]
        if (not isinstance(baseline_map, dict) or not isinstance(return_map, dict)
                or not isinstance(combined_map, dict) or set(baseline_map) != set(return_map)
                or set(baseline_map) != set(combined_map)):
            _fail(f"{label}/{queue_id} additional_missing_facts history 键与模板不同。")
        if queue_id != "proposal_ab_formal_review_216":
            if validator.canonical(return_map) != validator.canonical(baseline_map):
                _fail(f"{label}/{queue_id} 不允许填写 additional_missing_facts。")
            continue
        if any(value is not None for value in baseline_map.values()) \
                or any(value is not None for value in combined_map.values()):
            _fail(f"{label}/{queue_id} 两份模板的 additional_missing_facts 必须保持空白。")
        if any(value is not None and not isinstance(value, str) for value in return_map.values()):
            _fail(f"{label}/{queue_id} additional_missing_facts 只能是文本或 null。")
        copied[queue_id] = copy.deepcopy(return_map)
    return copied


def _copy_review_progress(baseline_template: dict[str, Any], baseline_return: dict[str, Any],
                          combined_template: dict[str, Any], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if baseline_template.get("reviewer_slot") != combined_template.get("reviewer_slot"):
        _fail("旧模板和合并模板的 reviewer_slot 不同，不能迁移审核进度。")
    if validator.canonical(baseline_template.get("reviewer_declaration")) != \
            validator.canonical(combined_template.get("reviewer_declaration")):
        _fail("两版空白模板的 reviewer_declaration 基础结构不同。")
    if validator.canonical(baseline_template.get("manual_confirmations_zh")) != \
            validator.canonical(combined_template.get("manual_confirmations_zh")):
        _fail("两版空白模板的 manual_confirmations_zh 基础结构不同。")
    base_queues = validator._queue_map(baseline_template, "baseline template")
    returned_queues = validator._queue_map(baseline_return, "baseline return")
    combined_queues = validator._queue_map(combined_template, "combined template")
    if set(base_queues) != set(BASELINE_QUEUES) or set(combined_queues) != set(BASELINE_QUEUES) | {V7_QUEUE}:
        _fail("模板队列集合不符合基线/新增 v7 的预期。")
    output = copy.deepcopy(combined_template)
    output["reviewer_declaration"] = copy.deepcopy(baseline_return["reviewer_declaration"])
    output["manual_confirmations_zh"] = _validate_manual_confirmations(
        baseline_template.get("manual_confirmations_zh"), baseline_return.get("manual_confirmations_zh"), label)
    fact_maps = _validate_additional_facts(baseline_template, baseline_return, combined_template, label)
    output_queues = validator._queue_map(output, "new return")
    copied_items = 0
    for queue_id in sorted(BASELINE_QUEUES):
        base_items = validator._item_map(base_queues[queue_id], f"baseline/{queue_id}")
        returned_items = validator._item_map(returned_queues[queue_id], f"return/{queue_id}")
        combined_items = validator._item_map(combined_queues[queue_id], f"combined/{queue_id}")
        output_items = validator._item_map(output_queues[queue_id], f"output/{queue_id}")
        if not (set(base_items) == set(returned_items) == set(combined_items) == set(output_items)):
            _fail(f"{label}/{queue_id} 的 item identities 在模板间不一致。")
        for item_id, blank in base_items.items():
            actual, newer = returned_items[item_id], combined_items[item_id]
            blank_review, actual_review, newer_review = (blank.get("review"), actual.get("review"), newer.get("review"))
            if (not isinstance(blank_review, dict) or not isinstance(actual_review, dict)
                    or not isinstance(newer_review, dict)
                    or set(blank_review) != set(actual_review) or set(blank_review) != set(newer_review)
                    or validator.canonical(blank_review) != validator.canonical(newer_review)):
                _fail(f"{label}/{queue_id}/{item_id} review 字段结构不匹配，或合并模板并非空白基线副本。")
            output_items[item_id]["review"] = copy.deepcopy(actual_review)
            copied_items += 1
        # Replace the copied list on the actual document; item maps reference the objects in the lists.
        output_queues[queue_id]["items"] = [output_items[validator._item_key(row)] for row in output_queues[queue_id]["items"]]
        if queue_id in fact_maps:
            output_queues[queue_id]["additional_missing_facts"] = fact_maps[queue_id]

    if not isinstance(baseline_return.get("reviewer_declaration"), dict) \
            or set(baseline_return["reviewer_declaration"]) != set(baseline_template.get("reviewer_declaration", {})):
        _fail(f"{label} reviewer_declaration 字段结构与模板不同。")
    # Keep the v7 queue byte-for-byte equivalent as parsed JSON to the blank template.
    if validator.canonical(output_queues[V7_QUEUE]) != validator.canonical(combined_queues[V7_QUEUE]):
        _fail("v7 审核判断必须保持为空白模板中的状态。")
    return output, {"copied_item_reviews": copied_items, "copied_additional_missing_facts_queues": sorted(fact_maps)}


def transfer(master_path: Path, baseline_manifest_path: Path, baseline_template_path: Path,
             baseline_return_path: Path, combined_manifest_path: Path, combined_template_path: Path,
             private_key_path: Path, v7_dir: Path, formal_material_path: Path,
             output_path: Path) -> dict[str, Any]:
    inputs = [master_path, baseline_manifest_path, baseline_template_path, baseline_return_path,
              combined_manifest_path, combined_template_path, private_key_path,
              v7_dir / "C-live.json", v7_dir / "protocol.json", v7_dir / "longmemeval-subset.json",
              formal_material_path]
    _require_regular(inputs)
    resolved_inputs = {p.resolve() for p in inputs}
    sidecar_path = output_path.with_name(output_path.name + ".provenance.json")
    if output_path.resolve() in resolved_inputs or sidecar_path.resolve() in resolved_inputs:
        _fail("输出文件不能覆盖或替代任何输入。")
    if output_path.exists() or output_path.is_symlink() or sidecar_path.exists() or sidecar_path.is_symlink():
        raise FileExistsError("拒绝覆盖已有迁移文件或 provenance sidecar。")
    before = {str(path): validator.sha256_file(path) for path in inputs}

    _, baseline_manifest, baseline_template, _, baseline_state = _load_and_validate_packet(
        master_path, baseline_manifest_path, baseline_template_path, "baseline template", formal_material_path,
        combined=False, private_key_path=None, v7_dir=None)
    _, combined_manifest, combined_template, _, combined_state = _load_and_validate_packet(
        master_path, combined_manifest_path, combined_template_path, "combined template", formal_material_path,
        combined=True, private_key_path=private_key_path, v7_dir=v7_dir)
    baseline_return = validator.read_json(baseline_return_path)
    validator._validate_return(baseline_template, baseline_return, "baseline return")
    if baseline_return.get("reviewer_slot") != baseline_template.get("reviewer_slot"):
        _fail("基线回传件的 reviewer_slot 与原模板不一致。")

    baseline_queues = baseline_state["queues"]
    combined_queues = combined_state["queues"]
    # Verify every shared queue and base evidence item matches between packet generations.
    for queue_id in sorted(BASELINE_QUEUES):
        old_queue, new_queue = baseline_queues[queue_id], combined_queues[queue_id]
        old_meta = {key: value for key, value in old_queue.items() if key != "items"}
        new_meta = {key: value for key, value in new_queue.items() if key != "items"}
        if validator.canonical(old_meta) != validator.canonical(new_meta):
            _fail(f"两版模板的基线队列说明或冻结属性不同：{queue_id}")
        old_items, new_items = validator._item_map(old_queue, f"baseline/{queue_id}"), validator._item_map(new_queue, f"combined/{queue_id}")
        if set(old_items) != set(new_items) or any(
                validator.canonical(old_items[item_id]) != validator.canonical(new_items[item_id])
                for item_id in old_items):
            _fail(f"两版模板的基线 item 内容或空白 review 结构不同：{queue_id}")
    old_catalog, new_catalog = baseline_template.get("evidence_catalog", {}), combined_template.get("evidence_catalog", {})
    if any(validator.canonical(new_catalog.get(key)) != validator.canonical(value) for key, value in old_catalog.items()):
        _fail("合并模板没有完整保留基线模板的冻结 evidence_catalog。")
    for key in ("title_zh", "reviewer_slot", "read_me_zh", "label_definitions_zh", "填写示例_zh", "reviewer_declaration"):
        if validator.canonical(baseline_template.get(key)) != validator.canonical(combined_template.get(key)):
            _fail(f"两版模板的基础审核说明或身份字段不同：{key}")
    if baseline_template.get("reviewer_slot") != combined_template.get("reviewer_slot"):
        _fail("旧模板和合并模板 reviewer_slot 不同。")

    output, summary = _copy_review_progress(baseline_template, baseline_return, combined_template,
                                            f"reviewer_slot_{baseline_template['reviewer_slot']}")
    # Run the normal return skeleton validator on the freshly assembled combined packet.
    validator._validate_return(combined_template, output, "new combined return")
    if validator.canonical(validator._queue_map(output, "new return")[V7_QUEUE]) != \
            validator.canonical(combined_queues[V7_QUEUE]):
        _fail("新回传件不得预填或改变 v7 人工判断。")
    after = {str(path): validator.sha256_file(path) for path in inputs}
    if before != after:
        _fail("迁移期间有输入文件改变；未写出迁移结果。")

    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    provenance = {
        "format": FORMAT,
        "reviewer_slot": output["reviewer_slot"],
        "baseline_packet": {"manifest_sha256": validator.sha256_file(baseline_manifest_path),
                            "template_sha256": validator.sha256_file(baseline_template_path),
                            "returned_review_sha256": validator.sha256_file(baseline_return_path)},
        "combined_packet": {"manifest_sha256": validator.sha256_file(combined_manifest_path),
                            "template_sha256": validator.sha256_file(combined_template_path),
                            "master_sha256": validator.sha256_file(master_path),
                            "v7_run_sha256": validator.sha256_file(v7_dir / "C-live.json"),
                            "v7_protocol_sha256": validator.sha256_file(v7_dir / "protocol.json"),
                            "v7_subset_sha256": validator.sha256_file(v7_dir / "longmemeval-subset.json"),
                            "private_identity_key_sha256": validator.sha256_file(private_key_path)},
        "copied_progress": summary,
        "v7_review_decisions_copied": 0,
        "v7_decisions_left_as_template": True,
        "reviewer_identity_and_independence_authenticated": False,
        "source_inputs_modified": False,
    }
    data = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    provenance["output_sha256"] = hashlib.sha256(data).hexdigest()
    provenance_data = (json.dumps(provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    created: list[Path] = []
    try:
        for path, payload in ((output_path, data), (sidecar_path, provenance_data)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
            created.append(path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {"output": str(output_path), "output_sha256": provenance["output_sha256"],
            "provenance": str(sidecar_path), "reviewer_slot": output["reviewer_slot"],
            **summary, "v7_review_decisions_copied": 0, "source_inputs_modified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=validator.MASTER_DEFAULT)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--baseline-template", type=Path, required=True,
                        help="Original blank template for the same reviewer slot.")
    parser.add_argument("--baseline-return", type=Path, required=True,
                        help="The reviewer’s saved baseline work; never overwritten.")
    parser.add_argument("--combined-manifest", type=Path, required=True)
    parser.add_argument("--combined-template", type=Path, required=True,
                        help="Later blank template that includes the v7 queue.")
    parser.add_argument("--private-key", type=Path, required=True,
                        help="Coordinator-only v7 identity key; do not send to reviewer.")
    parser.add_argument("--v7-dir", type=Path, required=True)
    parser.add_argument("--formal-material", type=Path, default=validator.FORMAL_MATERIAL_DEFAULT)
    parser.add_argument("--output", type=Path, required=True,
                        help="New combined reviewer JSON; refuses to overwrite existing files.")
    args = parser.parse_args()
    result = transfer(args.master, args.baseline_manifest, args.baseline_template,
                      args.baseline_return, args.combined_manifest, args.combined_template,
                      args.private_key, args.v7_dir, args.formal_material, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
