"""Frozen offline comparison of source-supplement candidate and baseline.

The pilot source pool is a new, separately recorded study. It is synthetic,
non-random and not certified novel. Candidate memories are provisional and
must be independently checked by reviewers; no AI service is called.
"""
import argparse
import hashlib
import importlib.util
import json
import secrets
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/ac2-source-supplement-paired-20261029-v1'
DEV=ROOT/'output/proposal-delivery/ac2-scope-guard-development-20261029'
POOL=ROOT/'datasets/assessment-candidates-v1/pilot'

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def write(p,x):
    with p.open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def app_hashes():return {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def freeze():
    files=[POOL/f'CANDIDATE-{i:02d}.json' for i in range(1,11)]
    if not all(p.is_file() for p in files):raise ValueError('A fixed source file is missing')
    OUT.mkdir(parents=True,exist_ok=False,mode=0o700)
    protocol={'format':'ac2-source-supplement-freeze-v1','frozen_at_utc':datetime.now(timezone.utc).isoformat(),
      'selection':'All existing pilot source-only CANDIDATE-01 through CANDIDATE-10, sorted by ID; no outcome filtering.',
      'limitations':['Ten synthetic pilot sources, not randomly selected or certified novel; earlier project exposure is possible.',
       'They are separate from the already-frozen candidate-test CANDIDATE-11–20 and the previously analysed 30 histories.',
       'Automatically generated memories are provisional; no additional source fact or relationship is claimed as human-confirmed.',
       'The source supplement adds candidate statements and does not fabricate relationships. More candidate statements can add noise.'],
      'source_sha256':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in files},
      'baseline':'Current local RuleBasedMemoryExtractor and v36 RuleBasedTestGenerator, max four questions per history.',
      'candidate':'Same extractor plus source-backed provisional supplement, then the same v36 generator; same budget.',
      'scope_guard':'Frozen offline v2, using provisional automatically extracted relationship types; flags private to study.',
      'supplement_sha256':sha((DEV/'source_candidate_v1.py').read_bytes()),
      'guard_sha256':sha((DEV/'scope_guard_candidate_v2.py').read_bytes()),
      'runner_sha256':sha(Path(__file__).read_bytes()),'application_sha256':app_hashes(),
      'settings':{'test_budget':4,'temperature':0,'random_seed':42,'model_called':False},
      'review':'Two different reviewers independently check every question and its expected answer against source; no guard flags or arm labels shown. Preserve uncertainty, differences, and generated shortfall.',
      'analysis':'Compare human-agreed grounded and structurally executable question yield out of all 40 slots for each arm; separately retain missing slots, guarded outputs, reviewer disagreement and uncertainty. Report history-paired descriptive differences; no guaranteed generalisation or formal threshold.',
      'stop':'Use all ten fixed sources and all generated tests; no cherry-picking, no tuning on returned labels then claiming this set held out.'}
    write(OUT/'protocol.json',protocol);print('Frozen ten sources and all code; no questions generated.')

def prepare():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.schemas import Conversation,AuditRun,MemoryStatus
    from app.test_generator.rule_based import RuleBasedTestGenerator
    protocol=json.loads((OUT/'protocol.json').read_bytes())
    if (protocol['runner_sha256']!=sha(Path(__file__).read_bytes()) or protocol['application_sha256']!=app_hashes()
        or protocol['supplement_sha256']!=sha((DEV/'source_candidate_v1.py').read_bytes())
        or protocol['guard_sha256']!=sha((DEV/'scope_guard_candidate_v2.py').read_bytes())
        or any(sha((ROOT/name).read_bytes())!=digest for name,digest in protocol['source_sha256'].items())):
        raise ValueError('Frozen inputs or implementation changed')
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    supplement=load('source_supplement_frozen',DEV/'source_candidate_v1.py');guard=load('scope_guard_frozen',DEV/'scope_guard_candidate_v2.py')
    if RuleBasedTestGenerator.VERSION!='rule-based-v36':raise ValueError('Unexpected generator')
    now=datetime(2026,10,29,tzinfo=timezone.utc);histories=[];questions=[];key={};ledger=[]
    for name in protocol['source_sha256']:
        p=ROOT/name;src=json.loads(p.read_bytes());hid=p.stem
        conv=Conversation(conversation_id=hid,created_at=now,authorised=True,source_origin='synthetic',messages=src['messages'])
        histories.append({'history_id':hid,'source_messages':src['messages']})
        for arm in ('baseline','supplement'):
            mems=RuleBasedMemoryExtractor().extract(conv) if arm=='baseline' else supplement.extract(conv)
            byid={m.memory_id:m for m in mems}
            # Temporary execution fixture only: candidate status is preserved in the reviewer evidence description.
            for m in mems:m.status=MemoryStatus.CONFIRMED
            run=AuditRun(run_id=f'{hid}-{arm}',conversation_id=hid,status='CREATED',target_configuration='weak',provider='rule_based',model='local',temperature=0,random_seed=42,test_budget=4,prompt_template_version='rule-based-v36',created_at=now)
            suite=RuleBasedTestGenerator().generate(mems,run);types=[r.type.value for m in mems for r in m.relationships]
            ledger.append({'history_id':hid,'arm':arm,'generated':len(suite),'missing_slots':4-len(suite),'provisional_memory_count':len(mems),'provisional_relationship_count':len(types)})
            for test in suite:
                ident=secrets.token_hex(16)
                if ident in key:raise ValueError('Duplicate blind ID')
                evidence=[{'canonical_value':byid[mid].canonical_value,'source_message_ids':byid[mid].source_message_ids} for mid in test.supporting_memory_ids]
                questions.append({'blind_id':ident,'history_id':hid,'prompt':test.prompt,'expected_behavior':test.expected_behavior,'provisional_evidence':evidence})
                key[ident]={'arm':arm,'history_id':hid,'guard_warning':guard.issue(test.prompt,[m['content'] for m in src['messages']],types),'dimension':test.dimension.value}
    secrets.SystemRandom().shuffle(questions)
    material={'format':'ac2-source-supplement-blind-material-v1','histories':histories,'questions':questions};material_sha=sha(canonical(material))
    review=OUT/'human-review';review.mkdir(mode=0o700)
    for i in (1,2):
        packet={'format':'ac2-source-supplement-human-review-v1','reviewer_slot':i,'material_sha256':material_sha,
          'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'seen_other_review':None,'seen_automatic_flags_or_arm':None,'used_ai_assistance':None,'prior_source_exposure':None},
          'histories':histories,'questions':questions,'decisions':[{'blind_id':q['blind_id'],'grounded':None,'structurally_executable':None,'reason':''} for q in questions]}
        write(review/f'reviewer-{i}.json',packet)
    private=OUT/'private';private.mkdir(mode=0o700);write(private/'material.json',material)
    write(private/'key.json',{'format':'ac2-source-supplement-private-key-v1','protocol_sha256':sha((OUT/'protocol.json').read_bytes()),'material_sha256':material_sha,'identity':key,'ledger':ledger})
    counts={arm:sum(x['generated'] for x in ledger if x['arm']==arm) for arm in ('baseline','supplement')}
    print(json.dumps({'histories':len(histories),'scheduled_per_arm':40,'generated_by_arm':counts,'human_labels_created':False},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','prepare']);a=parser.parse_args();{'freeze':freeze,'prepare':prepare}[a.stage]()
