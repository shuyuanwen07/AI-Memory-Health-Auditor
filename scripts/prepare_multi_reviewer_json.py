"""Create separate, readable review JSONs without sharing reviewer decisions.

The existing master remains untouched.  When a completed or partial v7 run is
provided, saved target answers are added with shuffled IDs; their identities and
automatic grades stay in a private key, outside the reviewer files.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import secrets
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json"
FORMAL_MATERIAL = ROOT / "artifacts/local/phase4-formal-review-20261027/reviewer-1/material.json"
STRATEGIES = {"weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"}
V7_PROTOCOL_ID = "phase4-c-openrouter-gpt6-luna-four-arm-20261028-v7"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_private(path: Path, value: Any) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def evidence_for(case: dict[str, Any]) -> list[dict[str, Any]]:
    ids = case.get("haystack_session_ids") or []
    sessions = case.get("haystack_sessions") or []
    dates = case.get("haystack_dates") or []
    if (not isinstance(ids, list) or not isinstance(sessions, list) or not isinstance(dates, list)
            or len(ids) != len(sessions) or len(ids) != len(dates)):
        raise ValueError("A benchmark case has inconsistent source-session metadata.")
    by_id = {sid: (date, messages) for sid, date, messages in zip(ids, dates, sessions)}
    selected = [by_id[x] for x in (case.get("answer_session_ids") or []) if x in by_id]
    if not selected:
        selected = list(zip(dates, sessions))
    if not selected:
        raise ValueError("A benchmark case has no source transcript for review.")
    return [{"source_transcript": i, "session_date": date, "messages": messages}
            for i, (date, messages) in enumerate(selected, 1)]


def store_evidence(master: dict[str, Any], evidence: Any) -> str:
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    evidence_id = "E-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    master["evidence_catalog"].setdefault(evidence_id, evidence)
    return evidence_id


def enrich_existing_benchmark_dates(master: dict[str, Any]) -> None:
    """Restore source and question dates without exposing the private condition key."""
    definitions = [
        ("proposal_c_archived_review_84", ROOT / "output/proposal-delivery/phase4-c-review-2026-10-28/review-key-private.json",
         ROOT / "artifacts/local/phase4-20261027/C-live.json", ROOT / "output/longmemeval-official-v1/source/longmemeval_oracle.json"),
        ("proposal_c_v6_review_180", ROOT / "output/proposal-delivery/phase4-c-v6-human-review/review-key-private.json",
         ROOT / "artifacts/local/phase4-c-openrouter-20261028-v6/C-live.json",
         ROOT / "artifacts/local/phase4-c-openrouter-20261028-v6/longmemeval-subset.json"),
    ]
    for queue_id, key_path, run_path, source_path in definitions:
        queue = next((q for q in master["queues"] if q.get("queue_id") == queue_id), None)
        if queue is None:
            raise ValueError(f"The review master is missing {queue_id}.")
        key, cases = load(key_path), load(source_path)
        if key.get("source_run_sha256") != digest(run_path):
            raise ValueError(f"The saved condition key for {queue_id} does not match its source run.")
        if queue_id == "proposal_c_v6_review_180" and key.get("source_subset_sha256") != digest(source_path):
            raise ValueError("The saved v6 condition key does not match its frozen subset.")
        by_id = {case["question_id"]: case for case in cases}
        mapping = {row["blind_item_id"]: row["question_id"] for row in key["mapping"]}
        if len(mapping) != len(key["mapping"]) or set(mapping) != {item["item_id"] for item in queue["items"]}:
            raise ValueError(f"The public items and private condition key differ for {queue_id}.")
        for item in queue["items"]:
            case = by_id[mapping[item["item_id"]]]
            if item.get("question") != case.get("question"):
                raise ValueError(f"A reviewer question does not match its source in {queue_id}.")
            item["question_date"] = case.get("question_date")
            item["evidence_refs"] = [store_evidence(master, evidence_for(case))]


def add_v7(master: dict[str, Any], directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_path, subset_path, protocol_path = (directory / name for name in
                                            ("C-live.json", "longmemeval-subset.json", "protocol.json"))
    run, subset, protocol = load(run_path), load(subset_path), load(protocol_path)
    if (protocol.get("id") != V7_PROTOCOL_ID or run.get("protocol_id") != V7_PROTOCOL_ID
            or run.get("protocol_sha256") != digest(protocol_path)):
        raise ValueError("The v7 run is not bound to its saved protocol.")
    if (set((protocol.get("target") or {}).get("memory_strategies", [])) != STRATEGIES
            or (protocol.get("target") or {}).get("repetitions_per_strategy") != 3
            or set((run.get("target_configuration") or {}).get("strategies", [])) != STRATEGIES
            or (run.get("target_configuration") or {}).get("repetitions") != 3):
        raise ValueError("The protocol or run does not describe the frozen four-strategy, three-repeat matrix.")
    if run.get("subset_sha256") != digest(subset_path):
        raise ValueError("The v7 run is not bound to its saved subset.")
    by_id = {case.get("question_id"): case for case in subset if isinstance(case, dict)}
    if len(subset) != 30 or len(by_id) != 30 or None in by_id:
        raise ValueError("The v7 subset must have 30 unique questions.")
    rows, identities, seen = [], [], set()
    for receipt in run.get("target_receipts", []):
        repetition, strategy, qid = receipt.get("repetition"), receipt.get("strategy"), receipt.get("question_id")
        identity = (repetition, strategy, qid)
        if repetition not in (1, 2, 3) or strategy not in STRATEGIES or qid not in by_id or identity in seen:
            raise ValueError("A v7 target receipt is duplicated or outside the frozen matrix.")
        seen.add(identity)
        answer = (receipt.get("response") or {}).get("response_text")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("A v7 target receipt has no saved answer.")
        if hashlib.sha256(answer.encode("utf-8")).hexdigest() != receipt.get("response_sha256"):
            raise ValueError("A v7 target answer does not match its saved response hash.")
        case = by_id[qid]
        evidence = evidence_for(case)
        evidence_id = store_evidence(master, evidence)
        rows.append({"question": case["question"], "reference_answer": case["answer"],
                     "question_date": case.get("question_date"), "target_response": answer, "evidence_refs": [evidence_id],
                     "review": {"answer_judgment": None, "rationale": ""}})
        identities.append({"question_id": qid, "strategy": strategy, "repetition": repetition,
                           "response_sha256": receipt["response_sha256"]})
    if not rows:
        raise ValueError("The v7 run has no saved target answers to review.")
    seed = secrets.randbits(64)
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    items, mapping = [], []
    for number, index in enumerate(order, 1):
        blind_id = f"V7-{number:03d}"
        items.append({"item_id": blind_id, **rows[index]})
        mapping.append({"item_id": blind_id, **identities[index]})
    expected = 30 * len(STRATEGIES) * 3
    queue = {
        "queue_id": "four_strategy_v7_answers", "title": "四策略补充实验：答案审核",
        "status": "待人工审核", "review_count": len(items),
        "review_instruction": "对照来源和参考答案，将 answer_judgment 填为 Pass、Fail 或 Uncertain，并在 rationale 写明依据。",
        "scope_note": f"已保存 {len(items)}/{expected} 条答案，最多来自同一批 30 段历史的重复运行；不显示策略、轮次和自动分数。",
        "label_choices": ["Pass", "Fail", "Uncertain"], "items": items,
    }
    master["queues"].append(queue)
    master["summary"]["counts_by_queue"][queue["queue_id"]] = len(items)
    master["summary"]["total_item_records_for_review"] = sum(len(q.get("items", [])) for q in master["queues"])
    master["summary"]["evidence_catalog_entries"] = len(master["evidence_catalog"])
    return master, {"warning": "仅协调人保管，不要发送给审核者。", "source_run_sha256": digest(run_path),
                    "protocol_sha256": digest(protocol_path), "subset_sha256": digest(subset_path),
                    "shuffle_seed": seed, "mapping": mapping}


def prepare(output: Path, v7_dir: Path | None, reviewers: int) -> dict[str, Any]:
    if reviewers < 2 or reviewers > 20:
        raise ValueError("Prepare between two and twenty reviewer copies.")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("The destination is not empty; existing review work will not be overwritten.")
    master = load(MASTER)
    if not isinstance(master, dict) or not isinstance(master.get("queues"), list):
        raise ValueError("The source review master is malformed.")
    enrich_existing_benchmark_dates(master)
    formal_queue = next((q for q in master["queues"] if q.get("queue_id") == "proposal_ab_formal_review_216"), None)
    if formal_queue is None or digest(FORMAL_MATERIAL) != formal_queue.get("source_material_sha256"):
        raise ValueError("The frozen A/B reviewer material does not match the master packet.")
    material = load(FORMAL_MATERIAL)
    defect_inventory: dict[str, Any] = {}
    for item in material.get("items", {}).values():
        if item.get("kind") == "response" and item.get("study") == "A":
            history, defects = item.get("history"), item.get("defects")
            if not isinstance(history, str) or not isinstance(defects, list):
                raise ValueError("The frozen A defect inventory is malformed.")
            if history in defect_inventory and defect_inventory[history] != defects:
                raise ValueError("The frozen A defect inventory differs within one history.")
            defect_inventory[history] = defects
    private_key = None
    if v7_dir is not None:
        master, private_key = add_v7(master, v7_dir)
    output.mkdir(parents=True, exist_ok=True)
    instructions = [
        "每位审核者使用自己的 JSON 副本，先独立完成，不查看其他人的答案或自动评分。",
        "先填写 reviewer_declaration，真实记录是否使用 AI、是否看过自动结果以及是否独立完成。",
        "审核队列中只修改每项 review 和 A/B 队列的 additional_missing_facts；保留 item_id、evidence_refs、来源材料和其他结构。",
        "每项的 source_evidence_zh 或 source_history_zh 就是可直接查看的来源；evidence_refs 也可在文件末尾 evidence_catalog 中查找。证据不足时可以填写 Uncertain 或留空并解释。",
        "答案审核选 Pass、Fail 或 Uncertain；其他任务按各队列说明和 label_definitions_zh 填写。",
        "可直接保存自己的 reviewer-N.json；协调人会保留 templates 中的空白原件。分别交回，勿相互覆盖。manual_confirmations_zh 中的 review、members 和 observations 仅由了解事实的责任人填写。",
        "A/B 队列中的 valid 用 true、false 或字符串 \"uncertain\"；critical_error 用 \"yes\"、\"no\" 或 \"uncertain\"。其他队列按本文件对应说明填写。",
    ]
    files = []
    templates = output / "templates"
    templates.mkdir(mode=0o700)
    for n in range(1, reviewers + 1):
        document = copy.deepcopy(master)
        document["title_zh"] = f"多人独立审核材料：审核副本 {n}"
        document["reviewer_slot"] = n
        document["reviewer_declaration"].setdefault("completed_by_human", None)
        document["read_me_zh"] = instructions + list(master.get("read_me_zh", []))
        document["填写示例_zh"] = {
            "说明": "以下只是格式示例，不是审核结论。根据每个项目的真实证据填写对应 review。",
            "reviewer_declaration示例": {"reviewer_label": "Reviewer A", "completed_at": "2026-11-01",
                                       "completed_by_human": True,
                                       "used_ai_assistance": False,
                                       "has_seen_automated_or_aggregate_results": False,
                                       "completed_independently": True, "note": ""},
            "答案review示例": {"answer_judgment": "Pass", "rationale": "答案与来源中的对应事实一致。"},
            "注意": "true 和 false 是 JSON 布尔值，不加引号；看过自动或汇总结果时须如实填 true。",
        }
        document["label_definitions_zh"]["formal_ab_fields"] = {
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
        # Reviewers need the evidence itself, not paths to source runs or earlier
        # reconciliation summaries that could reveal outcomes during review.
        document.pop("source_files_preserved", None)
        document["summary"] = {
            "total_item_records_for_review": sum(len(q.get("items", [])) for q in document["queues"]),
            "counts_by_queue": {q["queue_id"]: len(q.get("items", [])) for q in document["queues"]},
            "evidence_catalog_entries": len(document["evidence_catalog"]),
        }
        for queue in document["queues"]:
            for key in ("source_packet", "source_material", "previous_review_open_item_count"):
                queue.pop(key, None)
            histories = queue.get("source_histories", {})
            for item in queue.get("items", []):
                refs = item.get("evidence_refs", [])
                if refs:
                    if any(ref not in document["evidence_catalog"] for ref in refs):
                        raise ValueError("A review item has an unresolved evidence reference.")
                    item["source_evidence_zh"] = [document["evidence_catalog"][ref] for ref in refs]
                task = item.get("task")
                history = task.get("history") if isinstance(task, dict) else None
                if history and history in histories:
                    item["source_history_zh"] = histories[history]
            if queue.get("queue_id") == "proposal_ab_formal_review_216":
                queue["review_instruction"] = (
                    "依据每项 source_history_zh 及本队列来源判断：question、candidate 和 reference 的 valid 填 true、false 或 \"uncertain\"；"
                    "response 的 verdict 填 \"pass\"、\"fail\" 或 \"uncertain\"；relationship 的关系类型按 formal_ab_fields 填写。"
                    "先独立判断答案，再对照队列末尾冻结的 defect inventory 填写 A 的 defect_ids。"
                )
                queue["frozen_defect_inventory_by_history"] = defect_inventory
                queue["additional_missing_facts"] = {history: None for history in histories}
        file = output / f"reviewer-{n}.json"
        write_private(file, document)
        blank = templates / file.name
        write_private(blank, document)
        blank.chmod(0o400)
        if digest(blank) != digest(file):
            raise ValueError("The preserved blank template differs from the reviewer copy.")
        files.append({"file": file.name, "template_path": f"templates/{file.name}", "sha256": digest(blank)})
    if private_key:
        write_private(output / "PRIVATE-v7-identity-key.json", private_key)
    manifest = {"format": "multi-reviewer-json-v1", "master_sha256": digest(MASTER),
                "reviewer_copies": files, "items_per_reviewer": sum(len(q.get("items", [])) for q in master["queues"]),
                "v7_included": private_key is not None,
                "instruction": "只发 reviewer-N.json 给对应审核者；PRIVATE 文件由协调人保管。"}
    write_private(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v7-dir", type=Path)
    parser.add_argument("--reviewers", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, args.v7_dir, args.reviewers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
