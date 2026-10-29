"""Offline, non-destructive validator and agreement summary for reviewer JSON returns.

The tool validates source/template integrity, preserves each actual reviewer
entry, and leaves every item needing human resolution explicitly unresolved.
It cannot authenticate reviewer identity or independence and never makes
adjudication decisions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MASTER_DEFAULT = Path("output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json")
FORMAL_MATERIAL_DEFAULT = Path("artifacts/local/phase4-formal-review-20261027/reviewer-1/material.json")
ANSWER_FIELDS = {"answer_judgment", "answer_verdict", "verdict", "answer_correctness"}
QUESTION_FIELDS = {"question_validity", "valid"}
UNCERTAIN = {"uncertain", "unsure", "unknown", "cannot determine", "无法确定", "不确定"}
FORMAL_AB_FIELDS = {
    "valid": "仅 A/B 的 question、candidate、reference：支持填 true，不支持填 false，不确定填 \"uncertain\"。",
    "verdict": "A/B response：填小写 \"pass\"、\"fail\" 或 \"uncertain\"。",
    "failure_dimension": "仅 fail 时填 \"accuracy\"、\"freshness\"、\"conflict_resolution\"、\"appropriate_use\" 或 \"unclassified\"；其余情况保留 null。",
    "critical_error": "A/B response：填 \"yes\"、\"no\" 或 \"uncertain\"，不要填布尔值；判断依据见该队列 critical_error_definition。",
    "source_message_ids": "引用实际支持判断的来源消息 ID，使用字符串数组，例如 [\"P4H1S1\"]。",
    "defect_ids": "仅 A 的 response：先独立判断答案，再对照该队列末尾 frozen_defect_inventory_by_history，填写适用的已冻结 defect_id 数组；没有匹配项填 []。",
    "coverage": "reference：填 \"full\"、\"partial\"、\"none\" 或 \"uncertain\"；candidate_ids 填支持该覆盖判断的候选 ID 数组。",
    "relationship_type": "relationship：填 \"UPDATE\"、\"CONFLICT\"、\"CONTEXTUAL_OVERRIDE\"、\"NONE\" 或 \"uncertain\"。",
    "additional_missing_facts": "完整检查每段来源后，按 history 填写遗漏事实及来源；确定没有遗漏填空字符串，不确定时保持 null 并说明。",
}
FORMAL_AB_REVIEW_INSTRUCTION = (
    "依据每项 source_history_zh 及本队列来源判断：question、candidate 和 reference 的 valid 填 true、false 或 \"uncertain\"；"
    "response 的 verdict 填 \"pass\"、\"fail\" 或 \"uncertain\"；relationship 的关系类型按 formal_ab_fields 填写。"
    "先独立判断答案，再对照队列末尾冻结的 defect inventory 填写 A 的 defect_ids。"
)


class ReconciliationError(ValueError):
    """Inputs cannot be safely compared to the frozen review materials."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"无法读取 JSON 文件：{path}") from exc


def _queue_map(document: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    queues = document.get("queues")
    if not isinstance(queues, list):
        raise ReconciliationError(f"{label} 缺少 queues 列表。")
    result = {}
    for queue in queues:
        if not isinstance(queue, dict) or not isinstance(queue.get("queue_id"), str):
            raise ReconciliationError(f"{label} 包含无效队列。")
        qid = queue["queue_id"]
        if qid in result:
            raise ReconciliationError(f"{label} 的队列 ID 重复：{qid}")
        result[qid] = queue
    return result


def _item_map(queue: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    items = queue.get("items")
    if not isinstance(items, list):
        raise ReconciliationError(f"{label} 缺少 items 列表。")
    result = {}
    for item in items:
        item_id = _item_key(item) if isinstance(item, dict) else None
        if not isinstance(item, dict) or not isinstance(item_id, str):
            raise ReconciliationError(f"{label} 含有无效 item_id。")
        if item_id in result:
            raise ReconciliationError(f"{label} 的稳定 item 身份重复：{item_id}")
        result[item_id] = item
    return result


def _item_key(item: dict[str, Any]) -> str | None:
    value = item.get("item_id")
    if isinstance(value, str) and value:
        return value
    for key in ("candidate_id", "question_id", "response_id", "reference_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _primary_fields(queue_id: str, item: dict[str, Any]) -> list[str]:
    task = item.get("task") or {}
    kind = task.get("kind") if isinstance(task, dict) else None
    if queue_id == "proposal_ab_formal_review_216":
        by_kind = {
            "question": ["valid"],
            "candidate": ["valid"],
            "response": ["verdict"],
            "reference": ["valid", "coverage", "candidate_ids"],
            "relationship": ["relationship_type"],
        }
        fields = by_kind.get(kind, [])
    elif queue_id in {"proposal_c_archived_review_84", "proposal_c_v5_review_84",
                      "proposal_c_v6_review_180", "four_strategy_v7_answers"}:
        fields = ["answer_judgment"]
    elif queue_id == "current_source_repair_24":
        fields = ["question_validity", "answer_verdict"]
    elif queue_id == "current_source_six_run_48":
        fields = ["answer_verdict"]
    elif queue_id == "earlier_repair_loop_36":
        fields = ["question_validity", "answer_correctness"]
    elif queue_id == "current_source_intake_candidates_14":
        fields = ["decision"]
    else:
        review = item.get("review") or {}
        fields = [key for key in (
            "answer_judgment", "answer_verdict", "verdict", "answer_correctness",
            "question_validity", "valid", "decision", "relationship_type", "coverage",
        ) if key in review]
    if not fields:
        raise ReconciliationError(f"无法识别队列 {queue_id} 的主要判断字段：{item.get('item_id')}")
    return fields


def _state(value: Any, *, empty_list_is_complete: bool = False) -> str:
    if (value is None or value == "" or (value == [] and not empty_list_is_complete)
            or value == {}):
        return "missing"
    normalized = str(value).strip().casefold() if isinstance(value, str) else None
    if normalized in UNCERTAIN:
        return "uncertain"
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        if value[0].strip().casefold() in UNCERTAIN:
            return "uncertain"
    return "complete"


def _comparison_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, list):
        normalized = [_comparison_value(item) for item in value]
        return sorted(normalized, key=canonical)
    if isinstance(value, dict):
        return {key: _comparison_value(child) for key, child in value.items()}
    return value


def _derived_source_fields(master: dict[str, Any], queue: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    expected = {}
    refs = item.get("evidence_refs", [])
    if refs:
        catalog = master.get("evidence_catalog", {})
        if not isinstance(refs, list) or any(ref not in catalog for ref in refs):
            raise ReconciliationError(f"无效的 evidence_refs：{item.get('item_id')}")
        expected["source_evidence_zh"] = [catalog[ref] for ref in refs]
    task = item.get("task")
    history = task.get("history") if isinstance(task, dict) else None
    histories = queue.get("source_histories", {})
    if history and history in histories:
        expected["source_history_zh"] = histories[history]
    return expected


def _without_review(item: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(item)
    result.pop("review", None)
    result.pop("source_evidence_zh", None)
    result.pop("source_history_zh", None)
    return result


def _frozen_defect_inventory(master: dict[str, Any], material_path: Path) -> dict[str, Any]:
    queue = next((row for row in master.get("queues", [])
                  if row.get("queue_id") == "proposal_ab_formal_review_216"), None)
    if queue is None or not material_path.is_file() or material_path.is_symlink():
        raise ReconciliationError("缺少 A/B 冻结来源材料，无法核对 defect inventory。")
    if sha256_file(material_path) != queue.get("source_material_sha256"):
        raise ReconciliationError("A/B frozen defect inventory 来源材料哈希与 master 不符。")
    material = read_json(material_path)
    result: dict[str, Any] = {}
    for item in (material.get("items") or {}).values():
        if item.get("kind") == "response" and item.get("study") == "A":
            history, defects = item.get("history"), item.get("defects")
            if not isinstance(history, str) or not isinstance(defects, list):
                raise ReconciliationError("A/B 冻结 defect inventory 的来源结构无效。")
            if history in result and result[history] != defects:
                raise ReconciliationError("同一 history 的冻结 defect inventory 来源不一致。")
            result[history] = defects
    if not result:
        raise ReconciliationError("来源材料中没有 A 组 frozen defect inventory。")
    return result


def _master_with_frozen_benchmark_enrichment(master: dict[str, Any]) -> dict[str, Any]:
    """Rebuild supplemental LongMemEval dates/evidence from pinned private keys.

    The reviewer-packet preparer enriches archived and v6 benchmark items with
    dates and source transcripts that are intentionally absent from the public
    master. Recreate those fields from the same hash-bound inputs before
    comparing a packet; never accept those additions as unverified edits.
    """
    queue_ids = {row.get("queue_id") for row in master.get("queues", []) if isinstance(row, dict)}
    if not {"proposal_c_archived_review_84", "proposal_c_v6_review_180"}.issubset(queue_ids):
        return copy.deepcopy(master)
    try:
        try:
            import prepare_multi_reviewer_json as preparer
        except ImportError:
            from scripts import prepare_multi_reviewer_json as preparer
        enriched = copy.deepcopy(master)
        preparer.enrich_existing_benchmark_dates(enriched)
        return enriched
    except Exception as exc:
        raise ReconciliationError("无法按冻结 run、subset 与私有映射重建 benchmark 日期/来源证据。") from exc


def _compare_master_template(master: dict[str, Any], template: dict[str, Any], label: str,
                             extra_queue_ids: set[str], defect_inventory: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    master_queues = _queue_map(master, "master")
    template_queues = _queue_map(template, label)
    if set(template_queues) != set(master_queues) | extra_queue_ids:
        raise ReconciliationError(f"{label} 的队列集合与冻结 master 不一致。")
    allowed_top_level = {"title_zh", "reviewer_slot", "read_me_zh", "summary", "source_files_preserved",
                         "queues", "evidence_catalog", "填写示例_zh", "label_definitions_zh", "reviewer_declaration"}
    master_top = {k: v for k, v in master.items() if k not in allowed_top_level}
    template_top = {k: v for k, v in template.items() if k not in allowed_top_level}
    if canonical(master_top) != canonical(template_top):
        raise ReconciliationError(f"{label} 的顶层来源材料或声明结构与 master 不一致。")
    master_catalog = master.get("evidence_catalog", {})
    template_catalog = template.get("evidence_catalog", {})
    if not isinstance(master_catalog, dict) or not isinstance(template_catalog, dict):
        raise ReconciliationError(f"{label} 的 evidence_catalog 格式不正确。")
    if any(canonical(template_catalog.get(ref)) != canonical(value) for ref, value in master_catalog.items()):
        raise ReconciliationError(f"{label} 的 evidence_catalog 中已有来源材料与 master 不一致。")
    source_labels = master.get("label_definitions_zh", {})
    template_labels = template.get("label_definitions_zh", {})
    if any(canonical(template_labels.get(key)) != canonical(value)
           for key, value in source_labels.items()):
        raise ReconciliationError(f"{label} 的 label_definitions_zh 改动了 master 中的标签说明。")
    if template_labels.get("formal_ab_fields") != FORMAL_AB_FIELDS:
        raise ReconciliationError(f"{label} 的 A/B 判断字段说明与生成器冻结的说明不同。")
    source_declaration = copy.deepcopy(master.get("reviewer_declaration", {}))
    source_declaration.setdefault("completed_by_human", None)
    if canonical(template.get("reviewer_declaration")) != canonical(source_declaration):
        raise ReconciliationError(f"{label} 的空白 reviewer_declaration 与 master 模板不符。")
    bound_items: dict[str, dict[str, dict[str, Any]]] = {}
    for queue_id, source_queue in master_queues.items():
        review_queue = template_queues[queue_id]
        source_items = _item_map(source_queue, f"master/{queue_id}")
        template_items = _item_map(review_queue, f"{label}/{queue_id}")
        if set(source_items) != set(template_items):
            raise ReconciliationError(f"{label}/{queue_id} 的 item_id 集合与 master 不一致。")
        # Review copies deliberately omit source paths and prior open-item totals.
        ignored = {"source_packet", "source_material", "previous_review_open_item_count",
                   "additional_missing_facts", "frozen_defect_inventory_by_history"}
        if queue_id == "proposal_ab_formal_review_216":
            ignored.add("review_instruction")
        source_queue_projection = {k: v for k, v in source_queue.items() if k not in ignored and k != "items"}
        template_queue_projection = {k: v for k, v in review_queue.items() if k not in ignored and k != "items"}
        if canonical(source_queue_projection) != canonical(template_queue_projection):
            raise ReconciliationError(f"{label}/{queue_id} 的队列来源材料或说明已变化。")
        if queue_id == "proposal_ab_formal_review_216":
            if (template_labels.get("formal_ab_fields") != FORMAL_AB_FIELDS
                    or review_queue.get("review_instruction") != FORMAL_AB_REVIEW_INSTRUCTION):
                raise ReconciliationError(f"{label} 的 A/B 说明字段不匹配。")
            if review_queue.get("frozen_defect_inventory_by_history") != defect_inventory:
                raise ReconciliationError(f"{label} 的 frozen_defect_inventory_by_history 与源材料不符。")
            facts_map = review_queue.get("additional_missing_facts")
            if not isinstance(facts_map, dict) or set(facts_map) != set(source_queue.get("source_histories", {})):
                raise ReconciliationError(f"{label} 的 additional_missing_facts 必须覆盖全部冻结 histories。")
            if any(value is not None for value in facts_map.values()):
                raise ReconciliationError(f"{label} 的空白 additional_missing_facts 模板应全部为 null。")
        bound_items[queue_id] = template_items
        for item_id, source_item in source_items.items():
            review_item = template_items[item_id]
            if canonical(_without_review(source_item)) != canonical(_without_review(review_item)):
                raise ReconciliationError(f"{label}/{queue_id}/{item_id} 的身份或来源内容与 master 不一致。")
            derived = _derived_source_fields(master, source_queue, source_item)
            for field, expected in derived.items():
                if canonical(review_item.get(field)) != canonical(expected):
                    raise ReconciliationError(f"{label}/{queue_id}/{item_id} 的展示来源证据已变化：{field}")
            for field in ("source_evidence_zh", "source_history_zh"):
                if field in review_item and field not in derived:
                    raise ReconciliationError(f"{label}/{queue_id}/{item_id} 有未绑定的来源展示字段：{field}")
    return bound_items


def _validate_v7_queue(template_queues: dict[str, dict[str, Any]], identity_key_path: Path | None,
                        v7_dir: Path | None, evidence_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    queue_id = "four_strategy_v7_answers"
    if queue_id not in template_queues:
        if identity_key_path or v7_dir:
            raise ReconciliationError("传入了 v7 私有映射，但模板中没有 v7 审核队列。")
        return {}
    if identity_key_path is None or v7_dir is None:
        raise ReconciliationError("v7 队列需要 --private-key 与 --v7-dir 来核对脱敏 ID 和答案来源。")
    key = read_json(identity_key_path)
    run_path, subset_path, protocol_path = (v7_dir / name for name in ("C-live.json", "longmemeval-subset.json", "protocol.json"))
    run, subset, protocol = read_json(run_path), read_json(subset_path), read_json(protocol_path)
    if (key.get("source_run_sha256") != sha256_file(run_path)
            or key.get("protocol_sha256") != sha256_file(protocol_path)
            or key.get("subset_sha256") != sha256_file(subset_path)
            or run.get("protocol_sha256") != key.get("protocol_sha256")
            or run.get("subset_sha256") != key.get("subset_sha256")
            or protocol.get("id") != run.get("protocol_id")):
        raise ReconciliationError("v7 私有身份映射未绑定到当前 run、protocol 与 subset。")
    cases = {row.get("question_id"): row for row in subset if isinstance(row, dict)}
    receipts = {(row.get("repetition"), row.get("strategy"), row.get("question_id")): row
                for row in run.get("target_receipts", [])}
    mapping = key.get("mapping")
    template_items = _item_map(template_queues[queue_id], f"template/{queue_id}")
    if not isinstance(mapping, list) or len(mapping) != len(template_items) or len(mapping) != len(run.get("target_receipts", [])):
        raise ReconciliationError("v7 私有映射数量与审核模板或 run 收据数量不一致。")
    by_item = {}
    seen_source = set()
    for row in mapping:
        item_id = row.get("item_id")
        ident = (row.get("repetition"), row.get("strategy"), row.get("question_id"))
        item = template_items.get(item_id)
        case = cases.get(row.get("question_id"))
        receipt = receipts.get(ident)
        if (item is None or case is None or receipt is None or ident in seen_source
                or row.get("response_sha256") != receipt.get("response_sha256")):
            raise ReconciliationError("v7 脱敏 item_id 与原始答案身份无法一一核对。")
        seen_source.add(ident)
        answer = (receipt.get("response") or {}).get("response_text")
        try:
            try:
                import prepare_multi_reviewer_json as preparer
            except ImportError:
                from scripts import prepare_multi_reviewer_json as preparer
            evidence = preparer.evidence_for(case)
        except Exception as exc:
            raise ReconciliationError(f"v7/{item_id} 的日期化来源转录无法按冻结子集重建。") from exc
        evidence_bytes = canonical(evidence).encode("utf-8")
        evidence_ref = "E-" + hashlib.sha256(evidence_bytes).hexdigest()[:16]
        if (item.get("question") != case.get("question")
                or "question_date" not in item or item.get("question_date") != case.get("question_date")
                or item.get("reference_answer") != case.get("answer")
                or item.get("target_response") != answer
                or hashlib.sha256(str(answer).encode("utf-8")).hexdigest() != row.get("response_sha256")
                or item.get("evidence_refs") != [evidence_ref]):
            raise ReconciliationError(f"v7/{item_id} 的问题、参考答案或模型回答与冻结来源不符。")
        if (canonical(template_items[item_id].get("source_evidence_zh")) != canonical([evidence])
                or canonical(evidence_catalog.get(evidence_ref)) != canonical(evidence)):
            raise ReconciliationError(f"v7/{item_id} 展示的来源转录与冻结 session 不一致。")
        by_item[item_id] = {"question_id": row["question_id"], "strategy": row["strategy"],
                            "repetition": row["repetition"], "response_sha256": row["response_sha256"]}
    if seen_source != set(receipts):
        raise ReconciliationError("v7 私有映射遗漏或多列了原始答案身份。")
    return by_item


def _validate_return(template: dict[str, Any], returned: dict[str, Any], label: str) -> None:
    if returned.get("reviewer_slot") != template.get("reviewer_slot"):
        raise ReconciliationError(f"{label} 的 reviewer_slot 与空白模板不一致。")
    def skeleton(document: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(document)
        result.pop("reviewer_declaration", None)
        result.pop("manual_confirmations_zh", None)
        for queue in result.get("queues", []):
            queue.pop("additional_missing_facts", None)
            for item in queue.get("items", []):
                item.pop("review", None)
        return result
    if canonical(skeleton(template)) != canonical(skeleton(returned)):
        raise ReconciliationError(f"{label} 的来源证据、item 身份或队列结构与对应空白模板不同。")


def _validate_v7_return_labels(template_queue: dict[str, Any], returned_queue: dict[str, Any], label: str) -> None:
    template_items = _item_map(template_queue, f"template/{label}/four_strategy_v7_answers")
    returned_items = _item_map(returned_queue, f"return/{label}/four_strategy_v7_answers")
    if set(template_items) != set(returned_items):
        raise ReconciliationError(f"{label} 的 v7 审核 item_id 集合与模板不符。")
    allowed = {"pass", "fail", "uncertain"}
    expected_fields = {"answer_judgment", "rationale"}
    for item_id, template_item in template_items.items():
        blank_review = template_item.get("review")
        review = returned_items[item_id].get("review")
        if (not isinstance(blank_review, dict) or set(blank_review) != expected_fields
                or not isinstance(review, dict) or set(review) != expected_fields):
            raise ReconciliationError(f"{label}/v7/{item_id} 的 review 字段与模板不符。")
        judgment = review.get("answer_judgment")
        if judgment not in (None, "") and (
                not isinstance(judgment, str) or judgment.strip().casefold() not in allowed):
            raise ReconciliationError(f"{label}/v7/{item_id} 的 answer_judgment 必须是 Pass、Fail、Uncertain 或留空。")
        if not isinstance(review.get("rationale"), str):
            raise ReconciliationError(f"{label}/v7/{item_id} 的 rationale 必须是文本。")


def _review_declaration(document: dict[str, Any]) -> dict[str, Any]:
    declaration = document.get("reviewer_declaration")
    if not isinstance(declaration, dict):
        return {"values": declaration, "required_fields_complete": False,
                "identity_authenticated": False, "independence_authenticated": False}
    required = ("reviewer_label", "completed_at", "completed_by_human", "used_ai_assistance",
                "has_seen_automated_or_aggregate_results", "completed_independently")
    complete = all(declaration.get(key) not in (None, "") for key in required)
    return {"values": copy.deepcopy(declaration), "required_fields_complete": complete,
            "identity_authenticated": False, "independence_authenticated": False,
            "note": "以上是审核者本人填写的声明；本工具不验证身份、AI 使用情况或审核独立性。"}


def _readable_identity(item: dict[str, Any]) -> dict[str, Any]:
    task = item.get("task")
    identity = {key: item[key] for key in ("item_id", "question_id", "response_id", "candidate_id", "reference_id")
                if key in item}
    identity.setdefault("stable_item_id", _item_key(item))
    if isinstance(task, dict):
        task_fields = {key: task[key] for key in ("kind", "study", "history", "question_id", "method", "repetition", "strategy")
                       if key in task}
        if task_fields:
            identity["task"] = task_fields
    subject = item.get("question")
    if not isinstance(subject, str) and isinstance(task, dict):
        subject = task.get("question", task.get("text"))
    if isinstance(subject, str) and subject:
        identity["subject"] = subject[:240]
    return identity


def reconcile(master_path: Path, manifest_path: Path, template_a_path: Path, return_a_path: Path,
              template_b_path: Path, return_b_path: Path, output_path: Path,
              private_key_path: Path | None = None, v7_dir: Path | None = None,
              formal_material_path: Path | None = None) -> dict[str, Any]:
    paths = [master_path, manifest_path, template_a_path, return_a_path, template_b_path, return_b_path]
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ReconciliationError("所有 master、manifest、空白模板和回传文件都必须是普通文件。")
    if template_a_path.resolve() == return_a_path.resolve() or template_b_path.resolve() == return_b_path.resolve():
        raise ReconciliationError("空白模板必须保留原样；回传文件要另存为新文件。")
    master, manifest = read_json(master_path), read_json(manifest_path)
    defect_inventory = _frozen_defect_inventory(master, formal_material_path or FORMAL_MATERIAL_DEFAULT)
    template_a, returned_a = read_json(template_a_path), read_json(return_a_path)
    template_b, returned_b = read_json(template_b_path), read_json(return_b_path)
    if manifest.get("format") != "multi-reviewer-json-v1":
        raise ReconciliationError("manifest 格式不是 multi-reviewer-json-v1。")
    if manifest.get("master_sha256") != sha256_file(master_path):
        raise ReconciliationError("master 文件与审核包 manifest 的 SHA-256 不一致。")
    master = _master_with_frozen_benchmark_enrichment(master)
    expected_templates = {row.get("file"): row.get("sha256") for row in manifest.get("reviewer_copies", [])}
    for template_path in (template_a_path, template_b_path):
        expected_sha = expected_templates.get(template_path.name)
        if not expected_sha or sha256_file(template_path) != expected_sha:
            raise ReconciliationError(f"空白模板与 manifest 哈希不符：{template_path.name}")
    slots = [template_a.get("reviewer_slot"), template_b.get("reviewer_slot")]
    if slots[0] == slots[1] or not all(isinstance(slot, int) for slot in slots):
        raise ReconciliationError("两个模板必须是不同 reviewer_slot 的副本。")
    _validate_return(template_a, returned_a, "审核者 A")
    _validate_return(template_b, returned_b, "审核者 B")

    master_queues = _queue_map(master, "master")
    template_a_queues, template_b_queues = _queue_map(template_a, "template A"), _queue_map(template_b, "template B")
    extra = (set(template_a_queues) | set(template_b_queues)) - set(master_queues)
    if set(template_a_queues) != set(template_b_queues):
        raise ReconciliationError("两个空白模板的队列集合不同。")
    base_items_a = _compare_master_template(master, template_a, "template A", extra, defect_inventory)
    base_items_b = _compare_master_template(master, template_b, "template B", extra, defect_inventory)
    v7_identity = _validate_v7_queue(template_a_queues, private_key_path, v7_dir,
                                     template_a.get("evidence_catalog", {})) if extra else {}
    if extra:
        v7_identity_b = _validate_v7_queue(template_b_queues, private_key_path, v7_dir,
                                           template_b.get("evidence_catalog", {}))
        if v7_identity_b != v7_identity:
            raise ReconciliationError("两份模板的 v7 item_id 来源映射不同。")
    if extra:
        extra_a = _item_map(template_a_queues["four_strategy_v7_answers"], "template A/v7") if extra == {"four_strategy_v7_answers"} else {}
        extra_b = _item_map(template_b_queues["four_strategy_v7_answers"], "template B/v7") if extra == {"four_strategy_v7_answers"} else {}
        if extra != {"four_strategy_v7_answers"} or set(v7_identity) != set(extra_a):
            raise ReconciliationError("额外队列必须是已绑定源 run 的 v7 答案审核队列。")
        if set(extra_a) != set(extra_b):
            raise ReconciliationError("两份模板的 v7 脱敏 item_id 集合不一致。")

    returned_queues = [_queue_map(returned_a, "return A"), _queue_map(returned_b, "return B")]
    template_queues = [template_a_queues, template_b_queues]
    reviewer_docs = [returned_a, returned_b]
    if "four_strategy_v7_answers" in template_a_queues:
        _validate_v7_return_labels(template_a_queues["four_strategy_v7_answers"],
                                   returned_queues[0]["four_strategy_v7_answers"], "审核者 A")
        _validate_v7_return_labels(template_b_queues["four_strategy_v7_answers"],
                                   returned_queues[1]["four_strategy_v7_answers"], "审核者 B")
    reviewer_labels = [f"reviewer_slot_{slots[0]}", f"reviewer_slot_{slots[1]}"]
    declarations = {reviewer_labels[0]: _review_declaration(returned_a),
                    reviewer_labels[1]: _review_declaration(returned_b)}
    manual_confirmations = {reviewer_labels[0]: copy.deepcopy(returned_a.get("manual_confirmations_zh")),
                            reviewer_labels[1]: copy.deepcopy(returned_b.get("manual_confirmations_zh"))}
    queues_summary: dict[str, Any] = {}
    item_records = []
    unresolved_items = []
    additional_missing_facts_by_queue = {}
    for queue_id in sorted(template_a_queues):
        queues = [template_queues[0][queue_id], template_queues[1][queue_id]]
        return_items = [_item_map(q, f"return/{queue_id}") for q in (returned_queues[0][queue_id], returned_queues[1][queue_id])]
        template_items = [_item_map(q, f"template/{queue_id}") for q in queues]
        item_ids = sorted(template_items[0])
        if set(item_ids) != set(template_items[1]) or any(set(item_ids) != set(m) for m in return_items):
            raise ReconciliationError(f"{queue_id} 的 item_id 集合在两位审核者之间不一致。")
        queue_fields: dict[str, dict[str, Any]] = {}
        item_level = {"expected_items": len(item_ids),
                      "reviewer_a_complete": 0, "reviewer_a_has_missing": 0, "reviewer_a_has_uncertain": 0,
                      "reviewer_b_complete": 0, "reviewer_b_has_missing": 0, "reviewer_b_has_uncertain": 0,
                      "pair_agreed": 0, "pair_disagreed": 0, "pair_unresolved": 0}
        if queue_id == "proposal_ab_formal_review_216":
            facts = [returned_queues[i][queue_id].get("additional_missing_facts") for i in range(2)]
            expected_histories = set(defect_inventory)
            if any(not isinstance(value, dict) or set(value) != expected_histories for value in facts):
                raise ReconciliationError("回传的 additional_missing_facts 必须保留每个 history 的字段。")
            facts_rows = []
            for history in sorted(expected_histories):
                a, b = facts[0][history], facts[1][history]
                state_a = "uncertain" if a is None else "complete" if isinstance(a, str) else "invalid"
                state_b = "uncertain" if b is None else "complete" if isinstance(b, str) else "invalid"
                if "invalid" in (state_a, state_b):
                    raise ReconciliationError(f"{history} 的 additional_missing_facts 只能是字符串或 null。")
                comparison = ("agreed" if state_a == state_b == "complete" and a.strip() == b.strip()
                              else "disagreed" if state_a == state_b == "complete"
                              else "unresolved_uncertain")
                facts_rows.append({"history": history,
                                   reviewer_labels[0]: {"state": state_a, "value": a},
                                   reviewer_labels[1]: {"state": state_b, "value": b},
                                   "comparison": comparison,
                                   "adjudicated_value": None})
            additional_missing_facts_by_queue[queue_id] = facts_rows
        for item_id in item_ids:
            items = [template_items[i][item_id] for i in range(2)]
            reviews = []
            for i in range(2):
                raw_review = return_items[i][item_id].get("review")
                if raw_review is not None and not isinstance(raw_review, dict):
                    raise ReconciliationError(f"{queue_id}/{item_id} 的 review 必须是对象。")
                reviews.append(raw_review if isinstance(raw_review, dict) else {})
            if any(not isinstance(review, dict) for review in reviews):
                raise ReconciliationError(f"{queue_id}/{item_id} 的 review 必须是对象。")
            fields = _primary_fields(queue_id, items[0])
            if fields != _primary_fields(queue_id, items[1]):
                raise ReconciliationError(f"{queue_id}/{item_id} 两份模板的主要判断字段不同。")
            judgment_rows = []
            states_by_reviewer = [[], []]
            all_fields_agree = True
            any_field_disagrees = False
            for field in fields:
                values = [reviews[i].get(field) for i in range(2)]
                states = [_state(value, empty_list_is_complete=(
                    queue_id == "proposal_ab_formal_review_216" and field == "candidate_ids"))
                    for value in values]
                for i, state in enumerate(states):
                    states_by_reviewer[i].append(state)
                counter = queue_fields.setdefault(field, {
                    "expected_pairs": 0,
                    "reviewer_a": {"complete": 0, "missing": 0, "uncertain": 0},
                    "reviewer_b": {"complete": 0, "missing": 0, "uncertain": 0},
                    "both_complete": 0, "agreed": 0, "disagreed": 0,
                    "unresolved_pairs": 0, "uncertain_pairs": 0, "missing_pairs": 0,
                })
                counter["expected_pairs"] += 1
                for i, state in enumerate(states):
                    counter["reviewer_a" if i == 0 else "reviewer_b"][state] += 1
                if states == ["complete", "complete"]:
                    counter["both_complete"] += 1
                    is_agreement = canonical(_comparison_value(values[0])) == canonical(_comparison_value(values[1]))
                    counter["agreed" if is_agreement else "disagreed"] += 1
                    all_fields_agree &= is_agreement
                    any_field_disagrees |= not is_agreement
                    comparison = "agreed" if is_agreement else "disagreed"
                else:
                    counter["unresolved_pairs"] += 1
                    counter["uncertain_pairs"] += int("uncertain" in states)
                    counter["missing_pairs"] += int("missing" in states)
                    all_fields_agree = False
                    comparison = "unresolved_uncertain" if "uncertain" in states else "unresolved_missing"
                judgment_rows.append({"field": field,
                                      reviewer_labels[0]: {"state": states[0], "value": copy.deepcopy(values[0])},
                                      reviewer_labels[1]: {"state": states[1], "value": copy.deepcopy(values[1])},
                                      "comparison": comparison})
            for i, label in enumerate(("reviewer_a", "reviewer_b")):
                if all(state == "complete" for state in states_by_reviewer[i]):
                    item_level[f"{label}_complete"] += 1
                if "missing" in states_by_reviewer[i]:
                    item_level[f"{label}_has_missing"] += 1
                if "uncertain" in states_by_reviewer[i]:
                    item_level[f"{label}_has_uncertain"] += 1
            if all_fields_agree:
                item_level["pair_agreed"] += 1
                resolution_status = "reviewer_agreement_recorded_no_adjudication"
            elif any_field_disagrees:
                item_level["pair_disagreed"] += 1
                item_level["pair_unresolved"] += 1
                resolution_status = "disagreement_pending_human_adjudication"
            else:
                item_level["pair_unresolved"] += 1
                resolution_status = "missing_or_uncertain_pending_human_review"
            identity = v7_identity.get(item_id) if queue_id == "four_strategy_v7_answers" else None
            record = {"queue_id": queue_id, "item_id": item_id,
                      "identity": identity,
                      "identity_fields": _readable_identity(items[0]),
                      "immutable_item_sha256": hashlib.sha256(canonical(_without_review(items[0])).encode("utf-8")).hexdigest(),
                      "primary_judgments": judgment_rows,
                      "actual_review_fields": {reviewer_labels[0]: copy.deepcopy(reviews[0]),
                                               reviewer_labels[1]: copy.deepcopy(reviews[1])},
                      "status": resolution_status,
                      "adjudicated_value": None}
            item_records.append(record)
            if resolution_status != "reviewer_agreement_recorded_no_adjudication":
                unresolved_items.append({"queue_id": queue_id, "item_id": item_id,
                                         "identity": identity, "status": resolution_status,
                                         "primary_judgments": judgment_rows})
        queues_summary[queue_id] = {"title": queues[0].get("title"),
                                    "expected_items": len(item_ids),
                                    "primary_judgments_by_field": queue_fields,
                                    "item_counts": item_level,
                                    "unresolved_item_ids": [row["item_id"] for row in unresolved_items
                                                             if row["queue_id"] == queue_id],
                                    "additional_missing_facts_by_reviewer": {
                                        reviewer_labels[0]: copy.deepcopy(returned_queues[0][queue_id].get("additional_missing_facts")),
                                        reviewer_labels[1]: copy.deepcopy(returned_queues[1][queue_id].get("additional_missing_facts")),
                                    } if queue_id == "proposal_ab_formal_review_216" else None}

    output = {
        "format": "multi-reviewer-private-reconciliation-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_integrity": {
            "master_sha256": sha256_file(master_path),
            "manifest_sha256": sha256_file(manifest_path),
            "reviewer_a_template_sha256": sha256_file(template_a_path),
            "reviewer_b_template_sha256": sha256_file(template_b_path),
            "reviewer_a_return_source_sha256": sha256_file(return_a_path),
            "reviewer_b_return_source_sha256": sha256_file(return_b_path),
            "template_identities_and_source_material_match_master": True,
            "frozen_defect_inventory_sha256": sha256_file(formal_material_path or FORMAL_MATERIAL_DEFAULT),
            "frozen_defect_inventory_matches_source": True,
            "returns_change_only_allowed_review_fields_declarations_manual_confirmations_and_additional_missing_facts": True,
            "original_templates_and_returns_modified": False,
        },
        "reviewer_declarations": declarations,
        "manual_confirmations_by_reviewer": manual_confirmations,
        "additional_missing_facts_by_queue": additional_missing_facts_by_queue,
        "provenance_limits": {
            "reviewer_labels_are_self_declared": True,
            "identity_authenticated": False,
            "reviewer_independence_authenticated": False,
            "agreement_is_not_adjudication": True,
            "tool_does_not_create_consensus_or_fill_missing_labels": True,
        },
        "counts": {
            "queue_count": len(queues_summary), "item_count": len(item_records),
            "unresolved_item_count": len(unresolved_items),
            "agreement_count": sum(q["item_counts"]["pair_agreed"] for q in queues_summary.values()),
            "disagreement_count": sum(q["item_counts"]["pair_disagreed"] for q in queues_summary.values()),
            "additional_missing_fact_histories": sum(len(rows) for rows in additional_missing_facts_by_queue.values()),
            "additional_missing_fact_disagreements": sum(row["comparison"] == "disagreed"
                                                           for rows in additional_missing_facts_by_queue.values() for row in rows),
            "additional_missing_fact_unresolved": sum(row["comparison"].startswith("unresolved")
                                                       for rows in additional_missing_facts_by_queue.values() for row in rows),
        },
        "queues": queues_summary,
        "items": item_records,
        "unresolved_items": unresolved_items,
        "adjudication_instruction_zh": "只把 unresolved_items 交由有权限且知情的人逐项裁定。审阅者一致也仅记录为一致；本工具的 adjudicated_value 一律留空，不自动形成共识或金标准。",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=MASTER_DEFAULT)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--template-a", type=Path, required=True, help="审核者 A 对应的未修改空白模板")
    parser.add_argument("--return-a", type=Path, required=True, help="审核者 A 完成后另存的回传 JSON")
    parser.add_argument("--template-b", type=Path, required=True, help="审核者 B 对应的未修改空白模板")
    parser.add_argument("--return-b", type=Path, required=True, help="审核者 B 完成后另存的回传 JSON")
    parser.add_argument("--output", type=Path, required=True, help="新的私人裁定 JSON；不会覆盖已有文件")
    parser.add_argument("--private-key", type=Path, help="可选：v7 脱敏 item_id 身份映射")
    parser.add_argument("--v7-dir", type=Path, help="可选：包含 C-live.json、protocol.json、subset 的 v7 目录")
    parser.add_argument("--formal-material", type=Path, default=FORMAL_MATERIAL_DEFAULT,
                        help="A/B 冻结缺陷清单的原始来源材料 JSON")
    args = parser.parse_args()
    result = reconcile(args.master, args.manifest, args.template_a, args.return_a,
                       args.template_b, args.return_b, args.output, args.private_key, args.v7_dir,
                       args.formal_material)
    print(json.dumps({"output": str(args.output), "items": result["counts"]["item_count"],
                      "unresolved": result["counts"]["unresolved_item_count"],
                      "originals_modified": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
