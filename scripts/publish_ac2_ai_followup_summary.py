"""Publish aggregate AI follow-up as AI-only, preserving prior human results.

This command has no timer and does not interpret user silence as human review.
It is intentionally not run as part of generating the private review artifact.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import review_ac2_uncertain_with_context as source

OUTPUT = ROOT / 'frontend/public/reports/ac2-ai-followup-v1.json'
CONFIRMATION = ROOT / 'output/proposal-delivery/ac2-ai-followup-user-human-confirmation-2026-10-28.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_summary(adjudication_raw, baseline_raw, context_raw, followup_raw, confirmation_raw):
    actual = json.loads(followup_raw)
    confirmation = json.loads(confirmation_raw)
    expected = source.build(adjudication_raw, baseline_raw, context_raw)
    if actual != expected:
        raise ValueError('AI follow-up differs from the verified source evidence')
    if (confirmation.get('format') != 'ac2-ai-followup-human-confirmation-v1'
        or confirmation.get('user_response') != '没问题 我已让两名人员分别复审 他们各自独立且都认同结果'
        or confirmation.get('reviewed_file_sha256') != sha(followup_raw)):
        raise ValueError('The user confirmation must bind the exact follow-up')
    baseline = json.loads(baseline_raw)
    return {'format':'ac2-ai-followup-public-v1',
        'status':'human_confirmed_ai_followup',
        'original_human_adjudicated_structural':baseline['results']['structurally_executable'],
        'ai_followup_counts':actual['counts'],
        'mixed_structural':actual['mixed_supplemental_summary']['structurally_executable'],
        'context_source_id_coverage_counts':actual['context_source_id_coverage_counts'],
        'limitations':['User reports two people separately reviewed and agreed with the same AI follow-up; this is not independent blind first-pass labelling and identity is not authenticated.',
            'The follow-up does not overwrite original judgments.',
            'The retrieval context was reconstructed in isolated SQLite under one frozen target configuration, not observed in the AC2 run.',
            'A matched source ID is not proof of full semantic coverage or a correct answer; no AC2 model answers were collected.'],
        'source_sha256':{'human_adjudication':sha(adjudication_raw),'human_adjudicated_summary':sha(baseline_raw),
                         'offline_context':sha(context_raw),'ai_followup':sha(followup_raw),'user_confirmation':sha(confirmation_raw)}}


def main():
    paths=[source.ADJ,source.BASELINE,source.CONTEXT,source.OUTPUT,CONFIRMATION]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError('Inputs must be existing regular files')
    data=[p.read_bytes() for p in paths]
    summary=build_summary(*data)
    if any(path.read_bytes()!=raw for path,raw in zip(paths,data)):
        raise ValueError('Input evidence changed during publication')
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o644)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(summary,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(OUTPUT),'status':summary['status']}))


if __name__=='__main__':
    main()
