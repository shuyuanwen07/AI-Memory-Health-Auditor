"""Export private AC3 answers as two blind-review JSON files; no model calls."""
import hashlib
import json
import os
from pathlib import Path
from sqlalchemy import create_engine
from app.database.session import DATABASE_URL
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_export import collect_paired_targets
from scripts.ac3_paired_blind_review import make_packets
from scripts.ac3_retest_reference_stage import compile_reference_stage


def main():
    out=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen_path=out/'frozen-canonical.json';frozen=json.loads(frozen_path.read_bytes())
    staged=json.loads((out/'staged.json').read_text());sources=json.loads((out/'sources.json').read_text())
    source=Path(sources['source']).read_bytes();plan=Path(sources['plan']).read_bytes()
    reviews=[Path(p).read_bytes() for p in sources['reviews']]
    components={k:Path(p).read_bytes() for k,p in sources['components'].items()}
    engine=create_engine(DATABASE_URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=1)
    try:
        budget=out/'budget-scope.json';ledger=PairedBudgetLedger(engine,frozen_path=frozen_path,
            frozen_sha256=staged['frozen_sha256'],source=source,plan=plan,reviews=reviews,components=components,
            budget_path=budget,budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),billing_path=out/'billing-scope.json')
        targets=collect_paired_targets(engine,ledger=ledger,frozen=frozen,source=source,plan=plan,reviews=reviews,
            components=components,history_conversations=staged['history_conversations'],history_runs=staged['history_runs'],scope=staged['scope'])
        stage=compile_reference_stage(frozen,source,plan,reviews,components)
        packet,reviewers,key=make_packets(frozen,stage['questions'],targets)
        directory=out/'blind-review';directory.mkdir(mode=0o700,exist_ok=False)
        for name,document in [('private-target-export.json',targets),('private-blind-packet.json',packet),
                              ('private-mapping.json',key),('reviewer-1.json',reviewers[0]),('reviewer-2.json',reviewers[1])]:
            fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(document,f,ensure_ascii=False,indent=2);f.write('\n')
        print(json.dumps({'question_count':len(packet['items']),'output':str(directory),'model_called':False}))
    finally:engine.dispose()


if __name__=='__main__':main()
