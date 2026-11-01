"""Package source-only human review, then the finished paired MAX diagnostic.

The default command makes only the 150-case human handoff, without inspecting
grader outcomes or the author's intended labels. Use --release only after all
300 scheduled grader slots and the final analysis are complete. This script
never calls a model, imports a human decision, or changes a retained review.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
RELEASE = ROOT / "research/ac3-balanced-diagnostic-20261102"
HANDOFF = STUDY / "AC3-四类诊断150题-待人工复核.zip"
PROTOCOL_SHA256 = "00be50665f8e35a53b9c9eda4d43220937799e00f0bea2fdb57e41ff2d97c09c"
SECRET = re.compile(rb"(?:sk-(?:proj-|or-v1-)?[A-Za-z0-9_-]{24,}|Bearer\s+sk-[A-Za-z0-9_-]{16,})")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return result


def scan(raw, name):
    if SECRET.search(raw):
        raise ValueError(f"Credential-like string detected; package refused: {name}")
    if raw.startswith(b"PK\x03\x04"):
        with ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if not member.is_dir() and SECRET.search(archive.read(member.filename)):
                    raise ValueError(f"Credential-like string in nested snapshot: {name}")


def write_zip(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix + ".pending")
    with ZipFile(stage, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(entries.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("Unsafe archive member name")
            scan(raw, name)
            archive.writestr(name, raw)
    stage.replace(path)


def verified_source_material():
    """Only the frozen source packet and actual independent reviews define labels."""
    protocol_path = STUDY / "protocol.json"
    if sha(protocol_path.read_bytes()) != PROTOCOL_SHA256:
        raise ValueError("The approved paired diagnostic protocol changed")
    protocol = read(protocol_path)
    for relative, expected in protocol["bound_files_sha256"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or sha(path.read_bytes()) != expected:
            raise ValueError(f"Frozen source/review/rubric changed: {relative}")
    packet_path = STUDY / "blind-review/material.json"
    packet = read(packet_path)
    refs = read(STUDY / "reference-consensus.json")
    if refs["source_packet_sha256"] != sha(packet_path.read_bytes()):
        raise ValueError("Reference consensus is not bound to the source packet")
    if refs["reasoning_effort"] != "max" or refs["review_model"] != "gpt-6-astra":
        raise ValueError("Actual source reference reviews must use Astra MAX")
    cases = unique(packet["items"], "review_id")
    sources = unique(packet["sources"], "source_id")
    labels = unique(refs["items"], "review_id")
    if len(cases) != 150 or len(sources) != 30 or set(cases) != set(labels):
        raise ValueError("Expected the exact 150 reviewed cases and 30 sources")
    if Counter(item["source_id"] for item in cases.values()) != Counter({key: 5 for key in sources}):
        raise ValueError("Every history must have exactly five cases")
    for slot in (1, 2):
        path = STUDY / f"review-max/reviewer-{slot}.json"
        if refs["review_files_sha256"][path.name] != sha(path.read_bytes()):
            raise ValueError("Raw independent reviewer file changed")
        review = read(path)
        declaration = review["reviewer_declaration"]
        if declaration.get("model") != "gpt-6-astra" or declaration.get("reasoning_effort") != "max":
            raise ValueError("Reviewer model/effort mismatch")
        if set(unique(review["items"], "review_id")) != set(cases):
            raise ValueError("Raw reviewer coverage is incomplete")
    for rid, item in cases.items():
        label = labels[rid]
        if item["source_id"] not in sources or item["source_id"] != label["source_id"] or len(label["reviews"]) != 2:
            raise ValueError("Dangling source or reference identity")
    actual_types = Counter(label["failure_type"] for label in labels.values() if label["verdict"] == "fail")
    expected_types = Counter({key: 30 for key in ("accuracy", "freshness", "conflict_resolution", "appropriate_use")})
    if refs.get("ready_for_scoring") is not True or actual_types != expected_types or Counter(label["verdict"] for label in labels.values()) != Counter({"fail": 120, "pass": 30}):
        raise ValueError("Actual independently reviewed references do not cover the balanced diagnostic")
    if not all(label["question_source_valid"] for label in labels.values()) or not all(source["accepted_by_both"] for source in refs["sources"]):
        raise ValueError("Unresolved source validity must not be silently certified")
    return protocol, packet, refs


def human_handoff(protocol, packet, refs):
    source_refs = unique(refs["sources"], "source_id")
    labels = unique(refs["items"], "review_id")
    groups = defaultdict(list)
    for original in packet["items"]:
        rid = original["review_id"]
        label = labels[rid]
        groups[original["source_id"]].append({
            "review_id": rid, "question": original["question"], "answer": original["answer"],
            "response_origin": "curated_synthetic_diagnostic_answer_not_model_generated",
            "ai_reviewer_1": label["reviews"][0], "ai_reviewer_2": label["reviews"][1],
            "ai_reference_consensus": {key: label[key] for key in ("question_source_valid", "verdict", "failure_type")},
            "human": {"question_validity": None, "answer_verdict": None, "failure_type": None,
                      "failure_type_status": None, "evidence_message_ids": [], "reason": None}})
    sources = []
    for source in sorted(packet["sources"], key=lambda s: s["source_id"]):
        sources.append({**source, "ai_source_reviews": source_refs[source["source_id"]]["reviews"],
                        "human_source_review": {"validity": None, "reason": None}})
    source_paths = [STUDY / "blind-review/material.json", STUDY / "reference-consensus.json",
                    STUDY / "review-max/reviewer-1.json", STUDY / "review-max/reviewer-2.json"]
    bindings = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in source_paths}
    integrity = {"format": "ac3-balanced-human-handoff-integrity-v1", "study_kind": protocol["study_kind"],
                 "target_model_performance_claim": False, "sources": 30, "unique_answer_ids": 150,
                 "cases_per_source": 5, "all_source_links_resolve": True,
                 "protocol_sha256": PROTOCOL_SHA256, "source_review_bindings_sha256": bindings,
                 "intended_author_key_read_for_human_material": False, "grader_outcomes_included": False,
                 "human_confirmation_pending": True,
                 "prior_552_answer_human_approval_applies": False}
    template = {"format": "ac3-balanced-150-human-verification-v1", "status": "human_confirmation_pending",
                "study_kind": protocol["study_kind"], "target_model_performance_claim": False,
                "scope": "30 fictional histories;150 deliberately curated answers. Validate evaluator classifications on controlled fault injections, not natural model-error frequency.",
                "new_material_requires_separate_human_confirmation": True,
                "review_mode": "AI-assisted human verification; AI opinions are visible, not first-pass human blind annotation",
                "reviewer_declaration": {"reviewer_slot": None, "completed_by_human": False,
                                         "completed_independently": None, "has_seen_other_human_reviewer": None,
                                         "used_ai_assistance": True, "human_confirmation_pending": True,
                                         "confirmed_at": None, "reviewer_note": None},
                "allowed_values": {"validity": ["valid", "invalid", "uncertain"],
                                   "question_validity": ["valid", "invalid", "uncertain"],
                                   "answer_verdict": ["pass", "fail", "uncertain"],
                                   "failure_type": ["accuracy", "freshness", "conflict_resolution", "appropriate_use", None],
                                   "failure_type_status": ["single", "multiple", "uncertain", "not_applicable"]},
                "instructions": ["先看sources中的原文及human_source_review，再看对应source_id的groups回答。每段原文只列一次。",
                                 "填写每条human对象；AI意见仅供参考，必须根据原文实际判断。",
                                 "先判题目有效性与回答通过/失败，再按实际错误判类别；不要从题目措辞或设计目的推断类别。",
                                 "accuracy=普通事实错误；freshness=实际沿用已被明确取代的状态；conflict_resolution=错误处理同范围内不相容的有效记录；appropriate_use=错用默认偏好或上下文例外。",
                                 "如确有多个独立错误，failure_type_status填multiple；难以确定则填uncertain，不强行选单一类别。通过时类别为null，状态为not_applicable。",
                                 "两位审核者分别独立填写，不看对方文件。全部逐项核对后才填写完成声明。",
                                 "此前552条回答的人工认可不覆盖本次新增150条；本包默认待确认，不自动视为人工通过。"],
                "sources": sources,
                "groups": [{"source_id": sid, "answers": sorted(items, key=lambda item: item["review_id"])} for sid, items in sorted(groups.items())],
                "bindings": integrity}
    instructions = """AC3 四类诊断150题：新增人工复核包

本包是30段新虚构历史、每段5条人工设计的诊断回答，共150条。回答不是Astra自然生成的目标回答；它们刻意包含可检查的不同错误及正确对照，用来检验“评分器能否检出并分对类”，不能据此声称真实模型有多高的错误率。

给两位审核者分别发送reviewer-1.json和reviewer-2.json。每份可独立阅读：sources中每段原文只出现一次，groups按source_id归组。先填human_source_review，再填写每条human字段。AI意见可见，所以记为AI辅助人工复核；不要声称这是未见AI建议的首次人工盲审。两位人类审核者需分别填写且不看对方结果。

题目有效性：valid / invalid / uncertain。回答：pass / fail / uncertain。错误类型：accuracy / freshness / conflict_resolution / appropriate_use / null。类型状态：single / multiple / uncertain / not_applicable。填写证据message_id与理由。先判对错，后判实际错误类型；有多个错误或存疑就保留，不要为了达到某个数量而强制分类。

本包不包含评分器成绩、比较条件或作者预设答案类别。材料中的两份AI判断来自分别独立的Astra MAX复审。H05一处题目歧义已在任何评分调用前澄清；其余内容及原先修订记录仍保留。最终依据本包当前原文、题目、回答来核对。

旧552条实验材料的人工确认不适用于这批新材料。当前所有human字段均为空、completed_by_human=false。完成后再填写两份文件的完成与独立性声明，并返回文件或明确逐项确认。
"""
    entries = {"填写说明.txt": instructions.encode(), "材料完整性检查.json": dump(integrity)}
    for slot in (1, 2):
        review = copy.deepcopy(template)
        review["reviewer_declaration"]["reviewer_slot"] = slot
        entries[f"reviewer-{slot}.json"] = dump(review)
    if HANDOFF.exists():
        # Repackaging must not silently replace the exact material a person received.
        with ZipFile(HANDOFF) as archive:
            existing = {name: archive.read(name) for name in archive.namelist()}
        if existing != entries:
            raise ValueError("Existing human handoff differs; preserve it and create a new study version")
    else:
        write_zip(HANDOFF, entries)
    receipt = {**integrity, "handoff_zip_sha256": sha(HANDOFF.read_bytes())}
    (STUDY / "human-handoff-integrity.json").write_bytes(dump(receipt))
    return entries, receipt


def verified_human_confirmation():
    """The optional, separately recorded explicit confirmation never edits inputs."""
    path = STUDY / "human-confirmation.json"
    if not path.exists():
        return None
    receipt = read(path)
    if receipt.get("status") != "user_reported_independent_ai_assisted" or receipt.get("answers") != 150 or receipt.get("histories") != 30:
        raise ValueError("Human confirmation is for a different cohort or review mode")
    bindings = receipt.get("bound_files_sha256")
    if not isinstance(bindings, dict) or HANDOFF.relative_to(ROOT).as_posix() not in bindings:
        raise ValueError("Human confirmation does not bind the exact original 150-case ZIP")
    for relative, expected in bindings.items():
        file = (ROOT / relative).resolve()
        if not file.is_relative_to(ROOT) or not file.is_file() or sha(file.read_bytes()) != expected:
            raise ValueError(f"Human-confirmed input changed: {relative}")
    return receipt


def release_archive(protocol, handoff_entries, handoff_integrity):
    path = STUDY / "analysis.json"
    if not path.exists():
        raise ValueError("Final analysis is not available; human handoff only is safe")
    analysis = read(path)
    if not analysis.get("complete") or analysis.get("cohort", {}).get("terminal_slots") != 300:
        raise ValueError("Refusing to archive a partially dispatched experiment")
    helper = ROOT / "scripts/analyze_ac3_balanced_taxonomy_20261102.py"
    spec = importlib.util.spec_from_file_location("balanced_packaging_verifier", helper)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    _, _, _, rows, score_hashes, progress = verifier.collect()
    if not progress["complete"] or len(rows) != 300 or score_hashes != analysis["provenance"]["score_file_sha256"]:
        raise ValueError("Terminal receipt ledger differs from the finalized analysis")
    confirmation = verified_human_confirmation()
    if confirmation and analysis.get("human_confirmed") is not True:
        raise ValueError("Final analysis has not yet applied the new 150-case confirmation")
    entries = {}
    for file in sorted(STUDY.rglob("*")):
        if not file.is_file() or file.suffix in (".tmp", ".pending", ".zip", ".pyc"):
            continue
        relative = file.relative_to(STUDY)
        if relative.parts[0] == "scores" and read(file).get("state") == "dispatched":
            raise ValueError("Mutable dispatched score must not enter a release archive")
        entries["reproduction/" + file.relative_to(ROOT).as_posix()] = file.read_bytes()
    for file in sorted((ROOT / "scripts").glob("*ac3_balanced*20261102.py")):
        entries["reproduction/" + file.relative_to(ROOT).as_posix()] = file.read_bytes()
    for relative in ("frontend/src/components/AC3BalancedDiagnostic.tsx",
                     "frontend/src/components/AC3BalancedDiagnostic.test.tsx",
                     "frontend/src/components/CompactExperimentResults.tsx",
                     "frontend/public/reports/ac3-balanced-diagnostic-v1.json"):
        file = ROOT / relative
        if not file.exists():
            raise ValueError(f"The completed diagnostic UI artifact is absent: {relative}")
        if file.suffix == ".json" and read(file).get("complete") is not True:
            raise ValueError("Dashboard diagnostic summary is still a mutable progress snapshot")
        if file.suffix == ".json" and confirmation and read(file).get("human_confirmed") is not True:
            raise ValueError("Dashboard diagnostic summary has not applied the new 150-case approval")
        entries["implementation/" + relative] = file.read_bytes()
    # The live validator is the one hash-bound by the pre-call protocol. Other
    # import dependencies are a read-only release snapshot, not a retrospective
    # claim that every runtime file was independently preregistered.
    runtime_manifest = {}
    for file in sorted((ROOT / "backend/app").rglob("*.py")):
        raw = file.read_bytes()
        name = "implementation/" + file.relative_to(ROOT).as_posix()
        entries[name] = raw
        runtime_manifest[file.relative_to(ROOT).as_posix()] = sha(raw)
    entries["reproduction/backend/app/evaluator/llm_judge.py"] = (ROOT / "backend/app/evaluator/llm_judge.py").read_bytes()
    entries["reproduction/" + HANDOFF.relative_to(ROOT).as_posix()] = HANDOFF.read_bytes()
    entries["implementation/runtime-snapshot-manifest.json"] = dump({
        "format": "balanced-diagnostic-release-runtime-snapshot-v1", "files_sha256": runtime_manifest,
        "frozen_validator": "backend/app/evaluator/llm_judge.py",
        "validator_protocol_sha256": protocol["bound_files_sha256"]["backend/app/evaluator/llm_judge.py"],
        "notice": "The grader runner and validator are pre-call hash-bound. Other Python modules are a release dependency snapshot, not a claim that every file was independently frozen before calls."})
    prefix = "historical/blank-human-verification/" if confirmation else "human-verification/"
    entries.update({prefix + name: raw for name, raw in handoff_entries.items()})
    if confirmation:
        entries["approval/human-confirmation.json"] = (STUDY / "human-confirmation.json").read_bytes()
        entries["historical/blank-human-verification/STATUS.txt"] = (
            "HISTORICAL BLANK TEMPLATES. These exact pending forms were provided for the new 150-case review. "
            "They are preserved unchanged, not filled human item forms or current pending status. "
            "The explicit user-reported two-person AI-assisted confirmation is separately retained in approval/human-confirmation.json. "
            "The frozen source reference-consensus retains its pre-scoring phase metadata and has not been edited.\n").encode()
    readme = """# AC3 balanced MAX diagnostic, 2026-11-02

This supplementary evaluator validation uses 30 new fictional source histories and 150 deliberately curated answers: 120 reference failures with four actual categories and 30 reference passes, as judged by two independent MAX AI source reviewers. The answers are controlled fault injections, not natural LLM target outputs and not an estimate of target-model error frequency. Human confirmation of this new 150-case batch is pending; the prior 552-answer confirmation does not apply.

The frozen paired experiment evaluates two rubrics on the exact same question, answer and source-confirmed memory inputs, with 300 official OpenAI GPT-6 Astra MAX calls (8192 output limit, one provider attempt). All scheduled terminal outcomes, including failures or missing/error states, must remain in the analysis. The author-intended key does not supply reference labels: the actual source-only independent judgments in reference-consensus.json do. H05 wording was clarified and re-reviewed before any grader call; pre-freeze-v1 retains the original uncertain judgments and wording.

The two human-verification JSONs contain 150 cases each, sources once and editable human fields. AI opinions are visible, so this is AI-assisted human verification, not first-pass human blind annotation. They exclude grader outcomes, arm identities and the author-intended key. The complete reproduction archive contains those mappings, rubric texts and scores separately; it should not be substituted for a source-only reviewer packet.

Model transport receipts, 300-slot raw journals, protocol and source hashes, original independent reviews, final paired analysis, prerecorded analysis plan, development diagnosis and both rubrics are retained. The runner and actual validator are pre-call hash-bound; other app Python modules are a release dependency snapshot. Code, receipts and analysis can be inspected or replayed without purchasing new calls. A fresh provider run may return different text.

These are designed synthetic cases from 30 clusters. Reviewers and graders share the Astra family and can share biases. Threshold success is limited to this diagnostic and cannot certify population-wide reliability, unseen natural errors, or independent human agreement. Preserve strong baseline results, ties, regressions, uncertainty and limitations.

For offline replay, copy reproduction/ into a separate checkout of this project. It includes the exact original review ZIP at the approval-bound path and the frozen validator; implementation/backend/app supplies the remaining release dependencies if needed. Saved analyses can be replayed without model requests. New grading calls require explicit authorisation and are not covered by the existing human reference approval.

No environment files, credentials, databases, PPTs or unrelated historical full archives are included. Each member has a SHA-256 manifest and passes a credential-pattern scan. See the analysis.json and final project report for observed metrics and scope.
"""
    if confirmation:
        readme = readme.replace(
            "Human confirmation of this new 150-case batch is pending; the prior 552-answer confirmation does not apply.",
            "The user explicitly reports that two people independently checked and accepted this new 150-case source/question/answer/type-reference batch. The separate bound receipt is in approval/human-confirmation.json; this is new approval, not inherited from the earlier 552 answers. It is AI-assisted verification, not authenticated human identity or first-pass blind annotation, and blindness to automatic scores is not separately established. The confirmation does not cover the 300 automatic grader predictions.")
        readme = readme.replace(
            "The two human-verification JSONs contain 150 cases each, sources once and editable human fields.",
            "The two historical blank human-verification JSONs contain 150 cases each, sources once and unfilled human fields. They remain byte-identical under historical/blank-human-verification/; no filled human forms are fabricated. Their pending declarations and the frozen reference-consensus pre-call phase metadata are historical, while the separate current receipt and derived analysis record the new approval.")
    observed = []
    for arm in ("original", "revised"):
        summary = analysis[arm]
        primary = summary["metrics"]["joint_detection_and_correct_category"]
        false_positive = summary["metrics"]["false_positive_rate_all_reference_passes"]
        coverage = summary["metrics"]["decided_coverage"]
        observed.append(f"{arm}: correct detection and category {primary['numerator']}/{primary['denominator']}; "
                        f"false positives {false_positive['numerator']}/{false_positive['denominator']}; "
                        f"decided coverage {coverage['numerator']}/{coverage['denominator']}.")
    readme += "\nObserved paired results: " + " ".join(observed) + "\n"
    if analysis["original"]["metrics"] == analysis["revised"]["metrics"]:
        readme += "The two rubrics tie on these controlled cases. This result validates the tested diagnostic behaviour but provides no evidence of a rubric improvement. Zero observed errors does not establish zero risk on new cases.\n"
    entries["README.md"] = readme.encode()
    content_manifest = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(entries.items())}
    entries["member-manifest.json"] = dump({"format": "ac3-balanced-key-evidence-members-v1", "files": content_manifest})
    RELEASE.mkdir(parents=True, exist_ok=True)
    output = RELEASE / "key-evidence.zip"
    write_zip(output, entries)
    manifest = {"format": "ac3-balanced-key-evidence-release-v1", "study_kind": protocol["study_kind"],
                "target_model_performance_claim": False, "human_confirmation_pending": confirmation is None,
                "previous_552_approval_applies": False, "source_histories": 30, "cases": 150,
                "terminal_grader_slots": 300, "receipt_verification": progress["receipt_verification"],
                "protocol_sha256": PROTOCOL_SHA256, "analysis_sha256": sha(path.read_bytes()),
                "observed_metrics": {arm: analysis[arm]["metrics"] for arm in ("original", "revised")},
                "human_handoff_sha256": handoff_integrity["handoff_zip_sha256"],
                "evidence_sha256": sha(output.read_bytes()), "evidence_bytes": output.stat().st_size,
                "archive_members": len(entries), "credential_pattern_scan": "passed"}
    if confirmation:
        manifest.update(human_confirmation_status=confirmation["status"],
                        human_confirmation_receipt_sha256=sha((STUDY / "human-confirmation.json").read_bytes()),
                        original_blank_human_zip_preserved=True,
                        approval_scope="150 source/question/curated-answer/type-reference judgments only; not 300 automatic grader predictions")
    (RELEASE / "manifest.json").write_bytes(dump(manifest))
    (RELEASE / "README.md").write_text(readme, encoding="utf-8")
    return output


def main(make_release=False):
    protocol, packet, refs = verified_source_material()
    entries, integrity = human_handoff(protocol, packet, refs)
    confirmation = verified_human_confirmation()
    result = {"human_handoff": str(HANDOFF), "cases": 150, "sources": 30,
              "human_confirmation_pending": confirmation is None, "target_model_performance_claim": False,
              "human_handoff_sha256": integrity["handoff_zip_sha256"]}
    if make_release:
        result["evidence_archive"] = str(release_archive(protocol, entries, integrity))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="Archive only the finalized 300-slot experiment; default makes source-only human handoff")
    main(parser.parse_args().release)
