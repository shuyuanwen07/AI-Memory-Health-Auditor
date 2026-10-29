"""Explicit offline conversion of one completed JSON review to Phase 4 schema.

The export is accepted only after validating the frozen packet, original A/B
source material, reviewer-specific Phase 4 material fingerprint, and the
existing phase4-complete-review-v1 validator. It never writes to the app/API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import phase4_formal_review
import reconcile_multi_reviewer_json as reconcile


QUEUE_ID = "proposal_ab_formal_review_216"
SOURCE_FIELDS = {
    "question": ("question", "proposed_reference"),
    "response": ("study", "question", "answer", "question_id"),
    "candidate": ("text", "proposed_source_ids"),
    "reference": ("text", "source_ids", "candidate_ids"),
    "relationship": ("from_text", "to_text"),
}
REVIEW_FIELDS = {
    "question": {"valid", "note"},
    "candidate": {"valid", "note"},
    "response": {"verdict", "failure_dimension", "critical_error", "source_message_ids", "note"},
    "reference": {"valid", "coverage", "candidate_ids", "note"},
    "relationship": {"relationship_type", "note"},
}


class ExportError(ValueError):
    """The requested conversion is not supported by the verified source."""


def _read(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise ExportError(f"必须提供普通文件：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"无法读取 JSON：{path}") from exc


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _material_fingerprint(material: dict[str, Any]) -> str:
    # This matches prepare_phase4_complete_review.py's exact serializer.
    return _sha_bytes(json.dumps(material, ensure_ascii=False).encode("utf-8"))


def _verify_ab_material(master: dict[str, Any], source_material: dict[str, Any],
                        source_material_path: Path, phase4_material: dict[str, Any],
                        phase4_key: dict[str, Any]) -> dict[str, Any]:
    queues = reconcile._queue_map(master, "master")
    queue = queues.get(QUEUE_ID)
    if queue is None:
        raise ExportError("冻结 master 中没有 A/B formal review 队列。")
    if reconcile.sha256_file(source_material_path) != queue.get("source_material_sha256"):
        raise ExportError("A/B source material 的文件哈希与 master 不符。")
    if reconcile.canonical(source_material) != reconcile.canonical(phase4_material):
        raise ExportError("Phase 4 material 与 master 绑定的 A/B source material 内容不同。")
    if reconcile.canonical(queue.get("source_histories")) != reconcile.canonical(source_material.get("histories")):
        raise ExportError("master 展示的 A/B 历史记录与冻结 Phase 4 material 不同。")
    for field in ("reference_unit_definition", "relationship_unit_definition", "critical_error_definition"):
        if reconcile.canonical(queue.get(field)) != reconcile.canonical(source_material.get(field)):
            raise ExportError(f"master 的 {field} 与冻结 Phase 4 material 不同。")
    if _material_fingerprint(phase4_material) not in phase4_key.get("material_sha256", []):
        raise ExportError("Phase 4 material 的序列化指纹不在正式 key 中。")
    material_items = phase4_material.get("items")
    if not isinstance(material_items, dict):
        raise ExportError("Phase 4 material 缺少 items 对象。")
    source_items = reconcile._item_map(queue, f"master/{QUEUE_ID}")
    if set(source_items) != set(material_items):
        raise ExportError("A/B queue 与 Phase 4 material 的 item ID 集合不同。")
    for item_id, packet_item in source_items.items():
        task = packet_item.get("task")
        material_item = material_items[item_id]
        kind = material_item.get("kind")
        if not isinstance(task, dict) or kind not in SOURCE_FIELDS:
            raise ExportError(f"{item_id} 的任务类型不受支持。")
        if task.get("kind") != kind:
            raise ExportError(f"{item_id} 的 item kind 与冻结 Phase 4 material 不同。")
        fields = ("kind", "history", *SOURCE_FIELDS[kind])
        projection = {field: task.get(field) for field in fields}
        expected = {field: material_item.get(field) for field in fields}
        if reconcile.canonical(projection) != reconcile.canonical(expected):
            raise ExportError(f"{item_id} 的任务身份或来源字段与 Phase 4 material 不同。")
    return queue


def _validate_packet(master_path: Path, manifest_path: Path, template_path: Path,
                     returned_path: Path, source_material_path: Path,
                     private_key_path: Path | None = None, v7_dir: Path | None = None
                     ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    master, manifest = _read(master_path), _read(manifest_path)
    template, returned = _read(template_path), _read(returned_path)
    source_material = _read(source_material_path)
    if manifest.get("format") != "multi-reviewer-json-v1":
        raise ExportError("审核包 manifest 格式不受支持。")
    if manifest.get("master_sha256") != reconcile.sha256_file(master_path):
        raise ExportError("master 文件哈希与审核包 manifest 不符。")
    master = reconcile._master_with_frozen_benchmark_enrichment(master)
    declared_templates = {row.get("file"): row.get("sha256")
                          for row in manifest.get("reviewer_copies", []) if isinstance(row, dict)}
    if declared_templates.get(template_path.name) != reconcile.sha256_file(template_path):
        raise ExportError("空白模板哈希与审核包 manifest 不符。")
    if template_path.resolve() == returned_path.resolve():
        raise ExportError("回传文件必须另存为新文件，不能覆盖空白模板。")
    if returned.get("reviewer_slot") != template.get("reviewer_slot"):
        raise ExportError("回传 reviewer_slot 与空白模板不符。")

    master_queues = reconcile._queue_map(master, "master")
    template_queues = reconcile._queue_map(template, "template")
    extra_queues = set(template_queues) - set(master_queues)
    defect_inventory = reconcile._frozen_defect_inventory(master, source_material_path)
    bound = reconcile._compare_master_template(master, template, "template", extra_queues, defect_inventory)
    reconcile._validate_return(template, returned, "reviewer return")
    if extra_queues:
        if extra_queues != {"four_strategy_v7_answers"} or private_key_path is None or v7_dir is None:
            raise ExportError("模板有额外队列；若包含 v7，必须同时提供 --private-key 和 --v7-dir。")
        reconcile._validate_v7_queue(template_queues, private_key_path, v7_dir,
                                     template.get("evidence_catalog", {}))
        returned_queues = reconcile._queue_map(returned, "return")
        reconcile._validate_v7_return_labels(template_queues["four_strategy_v7_answers"],
                                             returned_queues["four_strategy_v7_answers"], "审核者")

    return_queues = reconcile._queue_map(returned, "return")
    ab_queue = return_queues.get(QUEUE_ID)
    template_ab = template_queues.get(QUEUE_ID)
    if ab_queue is None or template_ab is None or QUEUE_ID not in bound:
        raise ExportError("回传文件缺少 A/B formal review 队列。")
    returned_items = reconcile._item_map(ab_queue, f"return/{QUEUE_ID}")
    template_items = reconcile._item_map(template_ab, f"template/{QUEUE_ID}")
    if set(returned_items) != set(template_items):
        raise ExportError("回传 item ID 集合与空白模板不符。")
    if set(returned_items) != set(source_material.get("items", {})):
        raise ExportError("回传 item ID 集合与冻结 Phase 4 source material 不符。")
    if set(ab_queue.get("additional_missing_facts", {})) != set(source_material.get("histories", {})):
        raise ExportError("additional_missing_facts 必须覆盖全部冻结 history。")
    facts = ab_queue["additional_missing_facts"]
    if any(not isinstance(value, str) for value in facts.values()):
        raise ExportError("additional_missing_facts 只能是审核者填写的字符串；不确定/null 不能导出。")
    return master, template, returned, ab_queue


def _make_export(template: dict[str, Any], returned: dict[str, Any], ab_queue: dict[str, Any],
                 material: dict[str, Any], key: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    declaration = returned.get("reviewer_declaration")
    if not isinstance(declaration, dict):
        raise ExportError("回传没有 reviewer_declaration。")
    label = declaration.get("reviewer_label")
    completed_at = declaration.get("completed_at")
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
        raise ExportError("reviewer_label 必须是 1–80 个字符的实际审核者标识。")
    if not isinstance(completed_at, str) or not completed_at.strip():
        raise ExportError("completed_at 必须保留真实填写时间。")
    boolean_sources = {
        "completed_by_human": "completed_by_human",
        "completed_independently": "completed_independently",
        "used_ai_assistance": "used_ai_assistance",
        "has_seen_automated_results": "has_seen_automated_or_aggregate_results",
    }
    mapped_declaration = {}
    for destination, source in boolean_sources.items():
        value = declaration.get(source)
        if type(value) is not bool:
            raise ExportError(f"reviewer_declaration.{source} 必须是审核者实际填写的布尔值。")
        mapped_declaration[destination] = value
    if mapped_declaration["completed_by_human"] is not True:
        raise ExportError("phase4-complete-review-v1 只接受 completed_by_human=true；未改写声明。")
    if mapped_declaration["completed_independently"] is not True:
        raise ExportError("phase4-complete-review-v1 只接受 completed_independently=true；未改写声明。")

    labels: dict[str, Any] = {}
    returned_items = reconcile._item_map(ab_queue, f"return/{QUEUE_ID}")
    template_items = reconcile._item_map(reconcile._queue_map(template, "template")[QUEUE_ID],
                                         f"template/{QUEUE_ID}")
    for item_id, material_item in material["items"].items():
        kind = material_item["kind"]
        template_review = template_items[item_id].get("review")
        actual_review = returned_items[item_id].get("review")
        if not isinstance(template_review, dict) or not isinstance(actual_review, dict):
            raise ExportError(f"{item_id} 缺少 review 对象。")
        expected_fields = set(REVIEW_FIELDS[kind])
        if kind == "response" and material_item.get("study") == "A":
            expected_fields.add("defect_ids")
        if set(template_review) != expected_fields or set(actual_review) != expected_fields:
            raise ExportError(f"{item_id} 的 review 字段与冻结模板不完全匹配；拒绝静默丢弃字段。")
        # Copy declared values verbatim. Validation below rejects incomplete or
        # semantically invalid labels instead of filling defaults.
        labels[item_id] = {field: actual_review[field] for field in expected_fields}
        if kind == "response" and material_item.get("study") == "A":
            defect_ids = actual_review.get("defect_ids")
            if not isinstance(defect_ids, list):
                raise ExportError(f"{item_id} 的 A 组 defect_ids 必须是审核者明确填写的数组。")
            labels[item_id]["defect_ids"] = defect_ids
        if kind == "response" and material_item.get("study") != "A" and "defect_ids" in actual_review:
            raise ExportError(f"{item_id} 的 B 组 review 出现模板外 defect_ids。")

    review = {
        "schema_version": "phase4-complete-review-v1",
        "material_sha256": _material_fingerprint(material),
        "reviewer_id": label,
        **mapped_declaration,
        "completed_at": completed_at,
        "reviewer_label": label,
        "declaration_note": declaration.get("note", ""),
        "additional_missing_facts": dict(ab_queue["additional_missing_facts"]),
        "labels": labels,
    }
    if not isinstance(review["declaration_note"], str):
        raise ExportError("reviewer_declaration.note 必须是文本。")
    try:
        phase4_formal_review.validate(material, key, review)
    except (KeyError, TypeError, ValueError) as exc:
        raise ExportError(f"phase4_formal_review.validate 拒绝该回传：{exc}") from exc

    provenance = {
        "format": "multi-reviewer-to-phase4-export-v1",
        "source_reviewer_slot": template.get("reviewer_slot"),
        "reviewer_declaration_as_returned": declaration,
        "manual_confirmations_zh_as_returned": returned.get("manual_confirmations_zh"),
        "mapping": {
            "reviewer_label_to_reviewer_id": "copied verbatim",
            "has_seen_automated_or_aggregate_results_to_has_seen_automated_results": "copied verbatim",
            "review_fields": "copied by exact item_id and field name",
            "additional_missing_facts": "copied by history key and value",
        },
        "limits": [
            "Declaration values are self-reported; this export does not authenticate identity, human completion, or reviewer independence.",
            "The completed_independently value was copied as declared because the destination schema validator requires true; false or missing values are refused.",
            "manual_confirmations_zh and declaration metadata unsupported by the destination schema are retained in this private sidecar.",
            "This is an offline file conversion; no app/server import was performed.",
        ],
    }
    return review, provenance


def _write_private_exclusive(path: Path, data: dict[str, Any]) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ExportError("输出目录必须已经存在且不能是符号链接。")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def export(master_path: Path, manifest_path: Path, template_path: Path, returned_path: Path,
           source_material_path: Path, phase4_material_path: Path, phase4_key_path: Path,
           output_path: Path, private_key_path: Path | None = None, v7_dir: Path | None = None
           ) -> dict[str, Any]:
    input_paths = [master_path, manifest_path, template_path, returned_path, source_material_path,
                   phase4_material_path, phase4_key_path]
    if private_key_path is not None:
        input_paths.append(private_key_path)
    if any(path.resolve() == output_path.resolve() for path in input_paths):
        raise ExportError("输出路径不能覆盖任何来源文件。")
    sidecar_path = output_path.with_name(output_path.name + ".provenance.json")
    if sidecar_path.resolve() in {path.resolve() for path in input_paths}:
        raise ExportError("sidecar 路径不能覆盖任何来源文件。")
    master, template, returned, ab_queue = _validate_packet(
        master_path, manifest_path, template_path, returned_path, source_material_path,
        private_key_path, v7_dir)
    phase4_material, phase4_key = _read(phase4_material_path), _read(phase4_key_path)
    _verify_ab_material(master, _read(source_material_path), source_material_path,
                        phase4_material, phase4_key)
    review, provenance = _make_export(template, returned, ab_queue, phase4_material, phase4_key)
    provenance["source_sha256"] = {
        "master": reconcile.sha256_file(master_path),
        "manifest": reconcile.sha256_file(manifest_path),
        "blank_template": reconcile.sha256_file(template_path),
        "reviewer_return": reconcile.sha256_file(returned_path),
        "a_b_source_material": reconcile.sha256_file(source_material_path),
        "phase4_material": reconcile.sha256_file(phase4_material_path),
        "phase4_key": reconcile.sha256_file(phase4_key_path),
    }
    # Ensure both files are new. If creating the sidecar fails after the return
    # file, remove only the file this invocation just created.
    if output_path.exists() or output_path.is_symlink() or sidecar_path.exists() or sidecar_path.is_symlink():
        raise FileExistsError("拒绝覆盖已有导出文件或 provenance sidecar。")
    _write_private_exclusive(output_path, review)
    try:
        _write_private_exclusive(sidecar_path, provenance)
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise
    return {"output": str(output_path), "provenance": str(sidecar_path),
            "reviewer_id": review["reviewer_id"], "label_count": len(review["labels"]),
            "validated": True, "server_import_performed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--return", dest="returned", type=Path, required=True)
    parser.add_argument("--source-material", type=Path,
                        default=reconcile.FORMAL_MATERIAL_DEFAULT,
                        help="A/B material whose file hash is frozen in the review master.")
    parser.add_argument("--phase4-material", type=Path, required=True,
                        help="Reviewer-specific material.json accepted by phase4_formal_review.validate.")
    parser.add_argument("--phase4-key", type=Path, required=True,
                        help="Private phase4 key.json containing the material fingerprint.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-key", type=Path,
                        help="Coordinator-only v7 identity key, only when the template contains v7.")
    parser.add_argument("--v7-dir", type=Path,
                        help="Frozen v7 run directory, only when the template contains v7.")
    args = parser.parse_args()
    result = export(args.master, args.manifest, args.template, args.returned,
                    args.source_material, args.phase4_material, args.phase4_key,
                    args.output, args.private_key, args.v7_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
