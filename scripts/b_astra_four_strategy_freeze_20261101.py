"""Freeze the source-bound four-strategy Astra follow-up before any calls."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/b-astra-four-strategy-20261101-v1'
OLD=ROOT/'output/proposal-delivery/astra-writer-four-prospective-20261101-v1/protocol.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads(OLD.read_text())
if len(old['histories'])!=4 or any(len(x['questions'])!=4 for x in old['histories']):raise SystemExit('Unexpected source suite')
OUT.mkdir(parents=True,exist_ok=False)
p={'format':'b-astra-four-strategy-v1','frozen_at_utc':datetime.now(timezone.utc).isoformat(),
   'prior_protocol_sha256':sha(OLD),'source_human_review_sha256':old['human_review_sha256'],
   'source_user_confirmation_sha256':old['user_confirmation_sha256'],'histories':old['histories'],
   'strategies':['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'],
   'target_provider':'openai','target_model':'gpt-6-astra','requested_reasoning_effort':'max',
   'shared_writer':'rule_based','repetitions':1,'planned_answers':64,
   'scripts_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'scripts/b_astra_four_strategy_fork_20261101.py',ROOT/'scripts/b_astra_four_strategy_execute_20261101.py')},
   'app_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))},
   'limits':['Previously observed, related synthetic histories; not independent real-user data.',
             'Questions were human-checked with AI assistance, as reported by user; identities and exposure not independently authenticated.',
             'One repetition per strategy and history does not measure repeat-run variability.',
             'Model uses provider-controlled sampling, not a fixed temperature or seed.',
             'Two separate AI answer reviews then user confirmation are required before human-reviewed results.',
             'Any timeout or unknown outcome is recorded; no automatic redispatch.']}
(OUT/'protocol.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
print('Frozen',len(p['histories']),'histories, 16 conditions and 64 planned answers; no model calls.')
