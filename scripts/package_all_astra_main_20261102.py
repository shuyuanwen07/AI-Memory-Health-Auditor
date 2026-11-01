"""Package the complete new Astra MAX review handoff without inventing human labels.

This is an offline, idempotent packaging operation. It does not run a model,
change reviews, import human judgments, or overwrite any previous experiment.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/proposal-delivery"
A = OUTPUT / "a-astra-max-retest-20261101-v2"
BC = OUTPUT / "bc-reader-retest-20261101-v2"
AC3 = OUTPUT / "ac3-astra-max-retest-20261101-v2"
DEST = OUTPUT / "all-astra-main-results-20261101"
RELEASE = ROOT / "research/all-astra-main-results-20261102"
SECRET = re.compile(rb"(?:sk-(?:proj-|or-v1-)?[A-Za-z0-9_-]{24,}|Bearer\s+sk-[A-Za-z0-9_-]{16,})")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def unique(items, field="review_id"):
    result = {x[field]: x for x in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate {field}")
    return result


def human_answer_fields(study):
    fields = {"question_validity": None, "reference_validity": None,
              "answer_verdict": None, "safe_but_incomplete": None,
              "source_message_ids": [], "reason": None}
    if study == "A":
        fields.update(detected_defect_ids=None, outside_inventory_errors=None)
    if study == "AC3":
        fields.update(failure_type=None, failure_type_status=None,
                      classification_reason=None)
    return fields


def group_items(items, source_field):
    groups = defaultdict(list)
    for item in items:
        groups[item[source_field]].append(item)
    return [{"source_id": key, "answers": sorted(value, key=lambda x: x["review_id"])}
            for key, value in sorted(groups.items())]


def a_study():
    pack = read(A / "blind-review/material.json")
    analysis = read(A / "analysis.json")
    labels = unique(analysis["items"])
    reviewers = [unique(read(A / f"review-max/reviewer-{slot}.review.json")["items"])
                 for slot in (1, 2)]
    items = []
    for original in pack["items"]:
        rid = original["review_id"]
        item = {k: original[k] for k in ("review_id", "source_id", "dimension", "question", "expected_behavior", "answer")}
        item.update(ai_reviewer_1=reviewers[0][rid], ai_reviewer_2=reviewers[1][rid],
                    ai_consensus={k: labels[rid][k] for k in ("verdict", "question_reference_valid", "detected_defect_ids", "disputed_defect_ids", "safe_but_incomplete")},
                    human=human_answer_fields("A"))
        items.append(item)
    return {"description": "A：四场景、三种测试方法，共48条回答；先核对答案，再核对是否确实触发冻结的候选错误。",
            "sources": pack["sources"], "groups": group_items(items, "source_id")}


def bc_studies():
    consensus = read(BC / "review/consensus.json")
    if consensus["review_reasoning_effort"] != "max":
        raise ValueError("Final BC reference is not MAX")
    labels = unique(consensus["items"])
    b = read(BC / "B/blind-review/compact-batch-001.json")
    c = read(BC / "C/compact-review/final-all.json")
    questions = {q["question_id"]: q for q in b["questions"]}
    raw = {"B": [], "C": c["items"]}
    for path in sorted((BC / "B/blind-review").glob("compact-batch-*.json")):
        if ".private-key." not in path.name:
            raw["B"].extend(read(path)["items"])
    result = {}
    for study, sourcepack in (("B", b), ("C", c)):
        reviewer_items = [unique(read(BC / f"review-max/reviewer-{slot}/{study}-all.review.json")["items"])
                          for slot in (1, 2)]
        items = []
        for original in raw[study]:
            rid = original["review_id"]
            item = {k: original[k] for k in ("review_id", "question_id", "answer") if k in original}
            item["source_id"] = (questions[item["question_id"]]["source_id"] if study == "B" else original["source_handle"])
            item.update(ai_reviewer_1=reviewer_items[0][rid], ai_reviewer_2=reviewer_items[1][rid],
                        ai_consensus={k: labels[rid][k] for k in ("verdict", "source_validity_confirmed_by_both_ai", "answer_judgments", "reasons")},
                        human=human_answer_fields(study))
            items.append(item)
        source_reviews = [{**entry, "human_question_validity": None,
                           "human_reference_validity": None, "human_reason": None}
                          for entry in consensus["sources"] if entry["study"] == study]
        result[study] = {"description": f"{study}：16道固定题、四策略、三次重复，共192条回答。条件身份不在本审核文件中展示；请依据原文独立判断。",
                         "sources": sourcepack["sources"], "source_reviews": source_reviews,
                         "groups": group_items(items, "source_id")}
        if study == "B":
            result[study]["questions"] = b["questions"]
    return result


def ac3_study():
    pack = read(AC3 / "blind-review/compact-all.json")
    labels = unique(read(AC3 / "reference-consensus.json")["items"])
    items = []
    for original in pack["items"]:
        rid = original["review_id"]
        item = {k: original[k] for k in ("review_id", "question", "reference_behavior", "answer")}
        item.update(source_id=original["source_handle"], ai_reviewer_1=labels[rid]["reviewer_1"],
                    ai_reviewer_2=labels[rid]["reviewer_2"], ai_consensus=labels[rid]["reference"],
                    human=human_answer_fields("AC3"))
        items.append(item)
    return {"description": "AC3：30段历史、120条回答。先判题目/参考有效性和通过/失败；仅对失败再独立判实际错误类别。不要按题目原定类别推断回答类别。",
            "sources": pack["sources"], "groups": group_items(items, "source_id")}


def all_items(studies):
    for study, data in studies.items():
        for group in data["groups"]:
            for item in group["answers"]:
                yield study, item


def scan_bytes(data: bytes, label: str):
    if SECRET.search(data):
        raise ValueError(f"Credential-shaped string detected; no package published: {label}")
    if data[:4] == b"PK\x03\x04":
        with ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    nested = archive.read(info.filename)
                    if SECRET.search(nested):
                        raise ValueError(f"Credential-shaped string in nested archive: {label}")


def safe_write_archive(path, entries):
    # Stage outside the published path so a failed check cannot corrupt a valid handoff.
    stage = path.with_suffix(path.suffix + ".pending")
    with ZipFile(stage, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("Unsafe archive path")
            scan_bytes(content, name)
            archive.writestr(name, content)
    stage.replace(path)


def evidence_entries():
    entries = {}
    for base in (A, BC, AC3):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix in (".tmp", ".pending", ".pyc"):
                continue
            rel = path.relative_to(base)
            if path.suffix == ".zip" and path.name not in ("frozen-application-runtime.zip", "implementation-snapshot.zip"):
                continue
            if "blank" in path.name or "human-review" in rel.parts:
                continue
            # Repeated standalone C source packets are preserved by compact final-all;
            # keep receipts/raw journals, but omit redundant 5 MB blank templates.
            root_name = "reproduction/" + str(path.relative_to(ROOT)).replace("\\", "/")
            entries[root_name] = path.read_bytes()
    patterns = ("a_astra_max_*20261101.py", "ac3_astra_max_*2026110*.py", "verify_ac3_astra_max_receipts_20261102.py",
                "analyze_a_astra_max_20261102.py", "analyze_ac3_astra_max_20261102.py", "*bc*20261101.py",
                "split_bc_max_reviews_20261102.py", "package_all_astra_main_20261102.py",
                "finalize_astra_human_confirmation_20261102.py")
    for pattern in patterns:
        for path in sorted((ROOT / "scripts").glob(pattern)):
            entries["reproduction/" + path.relative_to(ROOT).as_posix()] = path.read_bytes()
    return entries


def verify_confirmation(answer_counts, handoff):
    """Read a separately recorded user confirmation; never create an approval."""
    path = DEST / "human-confirmation.json"
    if not path.exists():
        return None
    receipt = read(path)
    if receipt.get("status") != "user_reported_independent_ai_assisted":
        raise ValueError("The confirmation receipt has an unsupported status")
    if receipt.get("answer_counts") != answer_counts:
        raise ValueError("Confirmation counts do not cover the complete new cohort")
    bindings = receipt.get("bound_files_sha256")
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError("Confirmation must bind the actual reviewed files")
    handoff_relative = handoff.relative_to(ROOT).as_posix()
    if handoff_relative not in bindings:
        raise ValueError("Confirmation is not bound to the original full handoff ZIP")
    for relative, expected in bindings.items():
        file = (ROOT / relative).resolve()
        if not file.is_relative_to(ROOT) or not file.is_file():
            raise ValueError("Unsafe or missing bound confirmation file")
        if not isinstance(expected, str) or sha(file.read_bytes()) != expected:
            raise ValueError(f"Human-confirmation binding changed: {relative}")
    a = read(A / "analysis.json")
    bc = read(BC / "review/consensus.json")
    ac3 = read(AC3 / "analysis.json")
    views = {
        "A": {key: a[key] for key in ("methods", "items")},
        "BC": {key: bc[key] for key in ("sources", "items")},
        "AC3": {"cohort": ac3["cohort"], **{
            arm: {key: ac3[arm][key] for key in ("counts", "confusion_matrix", "metrics")}
            for arm in ("baseline", "candidate")}},
    }
    semantics = {key: sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())
                 for key, value in views.items()}
    if receipt.get("semantic_result_sha256") != semantics:
        raise ValueError("Substantive judgments changed after human confirmation")
    if a.get("review_status") != "human_confirmed" or not bc.get("human_confirmed") or not ac3.get("human_confirmed"):
        raise ValueError("Derived confirmation statuses are not finalized yet")
    return receipt


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    RELEASE.mkdir(parents=True, exist_ok=True)
    studies = {"A": a_study(), **bc_studies(), "AC3": ac3_study()}
    flat = list(all_items(studies))
    expected = {"A": 48, "B": 192, "C": 192, "AC3": 120}
    counts = dict(Counter(study for study, _ in flat))
    if counts != expected or len({(study, item["review_id"]) for study, item in flat}) != 552:
        raise ValueError("Expected exactly 552 independently reviewed answer identities")
    # Source IDs and question links must be resolvable inside each standalone reviewer JSON.
    for study, data in studies.items():
        source_ids = {source.get("source_id", source.get("source_handle")) for source in data["sources"]}
        if len(source_ids) != len(data["sources"]):
            raise ValueError("Duplicate source identifier")
        for group in data["groups"]:
            if group["source_id"] not in source_ids:
                raise ValueError("Dangling source reference")
        if study == "B":
            qids = {q["question_id"] for q in data["questions"]}
            if any(item["question_id"] not in qids for group in data["groups"] for item in group["answers"]):
                raise ValueError("Dangling B question")
    created = datetime.now(timezone.utc).isoformat()
    declaration = {"reviewer_slot": None, "completed_by_human": False,
                   "completed_independently": None, "has_seen_other_human_reviewer": None,
                   "used_ai_assistance": True, "human_confirmation_pending": True,
                   "confirmed_at": None, "reviewer_note": None}
    template = {"format": "all-astra-max-human-verification-20261102-v1", "created_at_utc": created,
                "status": "human_confirmation_pending", "answer_counts": counts,
                "review_mode": "AI-assisted human verification; not blind first-pass human annotation",
                "target_and_model_judge": {"provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max"},
                "ai_reference_reviewers": {"count": 2, "model": "gpt-6-astra", "reasoning_effort": "max", "independent": True},
                "reviewer_declaration": declaration,
                "allowed_values": {"question_validity": ["valid", "invalid", "uncertain"],
                                   "reference_validity": ["valid", "invalid", "uncertain"],
                                   "answer_verdict": ["pass", "fail", "uncertain"],
                                   "failure_type": ["accuracy", "freshness", "conflict_resolution", "appropriate_use", None],
                                   "failure_type_status": ["classified", "multiple", "uncertain", "not_applicable"],
                                   "safe_but_incomplete": [True, False]},
                "instructions": ["两人各自填写自己的 reviewer JSON；核对期间不要看对方的文件。",
                                 "sources 中每段原文只列一次。groups 按该来源归组；B 的 question_id 对应 questions。",
                                 "优先填写 human 对象。AI 意见可参考，也可明确反对；不要为了达到阈值而改判。",
                                 "B/C 的 source_reviews 需先核对题目及参考有效性；有歧义可保留 uncertain。",
                                 "A 的 detected_defect_ids 只能引用来源中冻结的 candidate_failure_patterns；清单外错误另填 outside_inventory_errors。",
                                 "AC3 只按实际回答的错误判 failure_type。多种错误或证据不足时填 multiple/uncertain；不要从题目维度照抄类别。",
                                 "安全但遗漏可回答事实的回答可填 safe_but_incomplete=true；这不自动等于 pass。",
                                 "完成逐条审核后才填写 completed_by_human=true、completed_independently=true 及 confirmed_at。此包预留字段均未自动确认。"],
                "studies": studies}
    focus = {"format": "astra-max-review-focus-20261102-v1", "status": "human_confirmation_pending",
             "notice": "这是重点项索引，不能代替552条全量复核；原始独立AI意见和两份独立填写文件均保留。",
             "A_mapping_disputes": [item for study, item in flat if study == "A" and item["ai_consensus"]["disputed_defect_ids"]],
             "BC_question_reference_flags": [{"study": study, **entry} for study in ("B", "C") for entry in studies[study]["source_reviews"] if not entry["accepted_by_both_ai"]],
             "BC_unresolved_answers": [{"study": study, "review_id": item["review_id"], "source_id": item["source_id"], "ai_consensus": item["ai_consensus"]} for study, item in flat if study in ("B", "C") and item["ai_consensus"]["verdict"] == "uncertain"],
             "AC3_failure_type_unresolved": [item for study, item in flat if study == "AC3" and item["ai_consensus"]["answer_verdict"] == "fail" and item["ai_consensus"]["primary_type_consensus_status"] != "agreed_single_primary_type"]}
    checks = {"format": "astra-max-handoff-integrity-v1", "created_at_utc": created,
              "answer_counts": counts, "total_unique_answer_ids": 552,
              "source_counts": {study: len(data["sources"]) for study, data in studies.items()},
              "all_source_references_resolve": True, "all_new_answers_human_confirmation_pending": True,
              "private_condition_keys_in_human_zip": False,
              "focus_counts": {k: len(v) for k, v in focus.items() if isinstance(v, list)},
              "main_review_effort": "max", "raw_high_reviews": "archived only; not used as current reference labels"}
    instructions = """Astra MAX 全部新增实验：人工逐项复核入口

本包共552条新回答：A48、B192、C192、AC3120。所有模型调用均为OpenAI Astra MAX；规则与统计代码不需要模型档位。此前已确认的AC1、AC2、写入器结果不要求在本包重复审核。

1. 给两位审核者分别发送 reviewer-1.json 和 reviewer-2.json。每份都包含完整原文、题目、回答及两份独立MAX AI意见；无需再查其他散文件。
2. 每人按studies → sources / questions → groups → answers阅读。sources只展示一次；B按question_id查questions。重点先看“重点复核.json”，但仍需完成全量逐项核对。
3. 填写每条human对象：question_validity/reference_validity用valid、invalid或uncertain；answer_verdict用pass、fail或uncertain；reason填写原文证据和理由。
4. A额外核对detected_defect_ids及outside_inventory_errors。冻结候选错误是潜在问题，不能把未命中的候选一律算漏检。
5. AC3失败回答额外核对failure_type、failure_type_status、classification_reason。现仅42/69失败有两份AI一致的单一类别；其余27条需要实际裁定，不按原题维度强行填满。freshness阳性类别尚无已确认例子。
6. B/C先判source_reviews中的题目与参考有效性，再判断回答。当前4个C来源/参考有疑点，59条回答因来源或独立意见分歧保留未决；未决不等于失败。
7. 两位人类审核者独立填写，不查看对方判断；最终有分歧时另行裁定并保留两份原判断。
8. 完成后再填写reviewer_declaration。此包默认completed_by_human=false、human_confirmation_pending=true，未把AI审核写成人工完成。

本包AI意见可见，因此属于“AI辅助人工复核”，不能声称为未看AI意见的首次双人人工盲审。包中不包含策略身份映射、系统自动分数或汇总成绩，避免额外提示判断。匿名review_id用于回填。需要重点复核的索引不覆盖独立意见。

建议先完成source_reviews，再完成answers。存疑时保留uncertain并说明；不要为使指标通过而强制判定。两份JSON完成后返回原文件即可。
"""
    handoff_entries = {"填写说明.txt": instructions.encode(), "重点复核.json": dump(focus), "完整性检查.json": dump(checks)}
    for slot in (1, 2):
        human = copy.deepcopy(template)
        human["reviewer_declaration"]["reviewer_slot"] = slot
        handoff_entries[f"reviewer-{slot}.json"] = dump(human)
    handoff = DEST / "Astra-MAX-全部新增实验-待人工复核.zip"
    confirmation = verify_confirmation(counts, handoff)
    if confirmation is None:
        safe_write_archive(handoff, handoff_entries)
        (DEST / "handoff-integrity.json").write_bytes(dump(checks))
    else:
        # The original blank pack is part of the user's binding. Its contents and
        # SHA must remain untouched; no filled reviewer forms are fabricated.
        with ZipFile(handoff) as archive:
            handoff_entries = {name: archive.read(name) for name in archive.namelist()}
        for slot in (1, 2):
            original = json.loads(handoff_entries[f"reviewer-{slot}.json"])
            actual = {(study, item["review_id"]) for study, item in all_items(original["studies"])}
            if actual != {(study, item["review_id"]) for study, item in flat}:
                raise ValueError("Confirmed handoff IDs do not match current cohort")
        checks.update(all_new_answers_human_confirmation_pending=False,
                      human_confirmation_status="user_reported_independent_ai_assisted",
                      human_confirmation_receipt_sha256=sha((DEST / "human-confirmation.json").read_bytes()),
                      original_blank_handoff_preserved=True,
                      confirmation_scope="User reports two independent people accepted all new outputs without edits; AI-assisted verification, not authenticated blind first-pass annotation.")

    entries = evidence_entries()
    human_prefix = "historical/blank-human-verification/" if confirmation else "human-verification/"
    entries.update({human_prefix + name: content for name, content in handoff_entries.items()})
    if confirmation:
        entries["approval/human-confirmation.json"] = (DEST / "human-confirmation.json").read_bytes()
        entries["reproduction/output/proposal-delivery/all-astra-main-results-20261101/human-confirmation.json"] = (DEST / "human-confirmation.json").read_bytes()
        entries["reproduction/output/proposal-delivery/all-astra-main-results-20261101/" + handoff.name] = handoff.read_bytes()
        entries["historical/blank-human-verification/STATUS.txt"] = (
            "HISTORICAL BLANK TEMPLATES. These unchanged pending forms were sent for review. "
            "They are preserved for audit provenance, not current pending-review status and not filled human labels. "
            "The current user-reported AI-assisted independent human confirmation is recorded separately in approval/human-confirmation.json.\n").encode()
    evidence_readme = """# All new Astra MAX main-results evidence, 2026-11-02

The archive preserves new A48+B192+C192+AC3120 target answers,120MAX taxonomy judgments, frozen source/protocols, actual request receipts, two independent MAX reference reviews, unresolved decisions and reproducible analyses. Rules/statistics are deterministic code, not a model effort setting. Human verification of these new outputs remains pending.

The two standalone human-verification JSON files include AI opinions and omit private condition mappings and automatic aggregate scores. This is AI-assisted human verification, not first-pass blind human annotation. Sources are included once per file and all552answer IDs resolve to source material.

Reproduction material includes private identity maps under its original explicitly private filenames, raw journals, target/scorer receipts and source snapshots. Those mappings are necessary to reconnect opaque review IDs to conditions, but were not supplied to the independent AI reviewers and are absent from the human review ZIP. Do not give the full reproduction archive to a reviewer who is meant to remain condition-blind.

Original independent high-effort BC review files are historical only; current consensus is derived from separate MAX review files. Old experiments are preserved elsewhere and have not been relabeled. The frozen application snapshot and trial helpers permit rerunning the fixed inputs. Actual provider responses are inherently nondeterministic; replaying archived results reproduces the analysis, not guaranteed identical new text.

C is a pinned16case LongMemEval Oracle evidence-only subset, including two reused anchors, not an official full benchmark score. B has four related synthetic histories. Repeated answers are correlated, not independent new histories. A exposes candidate patterns, not a verified error prevalence denominator. AC3 does not establish the whole failure taxonomy: only42/69failures have agreed single types, no freshness positives, and suitable-use type performance is limited. See each analysis.json and the latest main report for full denominators and source flags.

For offline analysis replay, extract the archive to a temporary directory, copy its reproduction/ contents into a separate project checkout, then run the analysis helpers from that checkout. The original handoff and bound confirmation receipt are included at their expected output paths. No provider call is needed to replay saved analyses; new target execution requires an authorised OpenAI key and produces new evidence not covered by this approval.

No API keys, environment files, databases or presentation files are intentionally included. An automated credential-pattern scan checks each included file and snapshot member before publication. Original retained source content may include benchmark and approved synthetic conversation text. LongMemEval source attribution/provenance is retained in C/protocol.json and selected-source.json.
"""
    if confirmation:
        evidence_readme = evidence_readme.replace(
            "Human verification of these new outputs remains pending.",
            "The user explicitly reports that two people independently checked and accepted all552new answers and associated judgments without edits. The bound user-reported confirmation is in approval/human-confirmation.json. It is AI-assisted verification; reviewer identities and independence are not externally authenticated, and blindness to system scores is not newly asserted.")
        evidence_readme = evidence_readme.replace(
            "The two standalone human-verification JSON files include AI opinions and omit private condition mappings and automatic aggregate scores.",
            "The two unchanged HISTORICAL BLANK human-verification JSON files are retained under historical/blank-human-verification/. Their pending fields describe the original templates, not current overall status. They include AI opinions and omit private condition mappings and automatic aggregate scores. No filled human item forms have been fabricated.")
        evidence_readme += ("\nAcceptance preserves all negative and unresolved findings: fourCsource/reference flags,59BCunresolved answers,27AC3failures without an agreed single primary type, and the Amappingdispute. No AC3 whole-taxonomy acceptance or freshness-positive validation is claimed.\n")
    entries["README.md"] = evidence_readme.encode()
    checks["human_zip_sha256"] = sha(handoff.read_bytes())
    entries["handoff-integrity.json"] = dump(checks)
    member_manifest = {"format": "astra-max-evidence-member-manifest-v1", "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(entries.items())}}
    entries["member-manifest.json"] = dump(member_manifest)
    evidence = RELEASE / "key-evidence.zip"
    safe_write_archive(evidence, entries)
    manifest = {**checks, "evidence_sha256": sha(evidence.read_bytes()),
                "evidence_bytes": evidence.stat().st_size, "archive_members": len(entries),
                "source_file_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (A / "analysis.json", BC / "analysis.json", BC / "review/consensus.json", AC3 / "analysis.json", AC3 / "reference-consensus.json")},
                "credential_pattern_scan": "passed", "human_handoff": str(handoff.relative_to(ROOT)),
                "main_report": "docs/EXPERIMENT_REPORT_ASTRA_MAX_20261102.md"}
    (RELEASE / "manifest.json").write_bytes(dump(manifest))
    (RELEASE / "README.md").write_text(evidence_readme + "\nSee ../../docs/EXPERIMENT_REPORT_ASTRA_MAX_20261102.md.\n", encoding="utf-8")
    print(json.dumps({"human_zip": str(handoff), "evidence": str(evidence), "counts": counts,
                      "focus": checks["focus_counts"], "archive_members": len(entries), "archive_bytes": evidence.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
