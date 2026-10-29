"""Read-only local database observation for an AC3 prospective source.

This checks the configured Docker Compose backend's current database only. It
does not prove that an external model was never called or that another person
never saw any answer. The record must not be represented as a human signature.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNNER = r'''import json,sys
from sqlalchemy import select,func,cast,String,text
from app.database.session import SessionLocal
from app.models.entities import MessageModel, TestCaseModel, TargetResponseModel, AuditRunModel
data=json.load(sys.stdin)
session=SessionLocal()
try:
    session.execute(text("SET TRANSACTION READ ONLY"))
    tests=select(TestCaseModel.id).where(TestCaseModel.prompt.in_(data["prompts"]))
    counts={
      "source_message_count":session.scalar(select(func.count()).select_from(MessageModel).where(MessageModel.source_message_id.in_(data["message_ids"]))),
      "matching_prompt_tests":session.scalar(select(func.count()).select_from(TestCaseModel).where(TestCaseModel.prompt.in_(data["prompts"]))),
      "matching_prompt_responses":session.scalar(select(func.count()).select_from(TargetResponseModel).where(TargetResponseModel.test_id.in_(tests))),
      "ac3_generated_responses":session.scalar(select(func.count()).select_from(TargetResponseModel).join(TestCaseModel,TargetResponseModel.test_id==TestCaseModel.id).where(TestCaseModel.id.like("AC3%"))),
      "source_fingerprint_audits":session.scalar(select(func.count()).select_from(AuditRunModel).where(cast(AuditRunModel.reproducibility_metadata,String).contains(data["sha256"])))
    }
    print(json.dumps(counts))
finally:
    session.rollback()
    session.close()
'''


def observe(source):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('Candidate source must be a regular, non-symlink file.')
    raw = source.read_bytes(); suite = json.loads(raw)
    cases = suite.get('cases')
    if not isinstance(cases, list) or len(cases) not in (8, 30):
        raise ValueError('Expected an eight- or thirty-history prospective suite.')
    prompts = [q['question'] for case in cases for q in case['tests']]
    message_ids = [msg['message_id'] for case in cases for msg in case['source_messages']]
    if len(prompts) != 4 * len(cases) or len(set(prompts)) != len(prompts) or len(message_ids) != len(set(message_ids)):
        raise ValueError('Candidate question or source IDs are incomplete or duplicated.')
    source_sha = hashlib.sha256(raw).hexdigest()
    data = {'prompts': prompts, 'message_ids': message_ids, 'sha256': source_sha}
    started_at = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(['docker','compose','exec','-T','backend','python','-c',RUNNER], cwd=ROOT,
                          input=json.dumps(data), text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise ValueError('Read-only database observation failed: ' + proc.stderr[-500:])
    counts = json.loads(proc.stdout)
    expected = {'source_message_count','matching_prompt_tests','matching_prompt_responses',
                'ac3_generated_responses','source_fingerprint_audits'}
    if set(counts) != expected or any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError('Database returned malformed observation counts.')
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha:
        raise ValueError('Candidate source changed during observation.')
    return {'format':'ac3-local-heldout-observation-v1', 'observed_at_utc':datetime.now(timezone.utc).isoformat(),
            'observation_started_at_utc':started_at, 'observer':'Codex (AI); read-only database observation',
            'human_attestation_created':False, 'source_path':str(source.resolve()), 'source_sha256':source_sha,
            'question_count':len(prompts), 'source_message_id_count':len(message_ids), 'database_counts':counts,
            'local_matching_responses_found':counts['matching_prompt_responses'] != 0 or counts['ac3_generated_responses'] != 0,
            'scope_limitations':'Current configured local database snapshot only. Does not authenticate users, rule out external model calls or files, or establish that another person did not see an answer. Observation timestamps are self-reported.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=observe(args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(args.output),'counts':result['database_counts'],
                      'human_attestation_created':False,'external_calls_ruled_out':False}))


if __name__=='__main__':
    main()
