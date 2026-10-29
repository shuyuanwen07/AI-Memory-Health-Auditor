"""Run fixed AC3 candidate scorer once per saved answer; no retries."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from app.database.session import DATABASE_URL
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_scorer_runner import run_paired_scorer_step


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',type=int,required=True);parser.add_argument('--stop',type=int,required=True)
    args=parser.parse_args()
    out=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen_path=out/'frozen-canonical.json';frozen=json.loads(frozen_path.read_bytes())
    staged=json.loads((out/'staged.json').read_text());sources=json.loads((out/'sources.json').read_text())
    source=Path(sources['source']).read_bytes();plan=Path(sources['plan']).read_bytes()
    reviews=[Path(p).read_bytes() for p in sources['reviews']]
    components={k:Path(p).read_bytes() for k,p in sources['components'].items()}
    questions=[q for case in frozen['suite']['cases'] for q in case['tests']]
    if args.start<0 or args.stop>len(questions) or args.start>=args.stop:raise ValueError('Invalid bounded range')
    api_key=os.getenv('OPENROUTER_API_KEY')
    if not api_key:raise ValueError('OpenRouter credential unavailable')
    sys.path.insert(0,'/output/proposal-delivery/ac3-taxonomy-development-tools-2026-10-28')
    from taxonomy_candidate import TaxonomyCandidate
    judge=TaxonomyCandidate('openrouter',model='openai/gpt-6-luna')
    engine=create_engine(DATABASE_URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=1)
    try:
        budget=out/'budget-scope.json';ledger=PairedBudgetLedger(engine,frozen_path=frozen_path,
            frozen_sha256=staged['frozen_sha256'],source=source,plan=plan,reviews=reviews,components=components,
            budget_path=budget,budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),billing_path=out/'billing-scope.json')
        for index in range(args.start,args.stop):
            ident=questions[index]['test_id']
            result=run_paired_scorer_step(engine,ledger=ledger,frozen=frozen,source=source,plan=plan,reviews=reviews,
                components=components,history_conversations=staged['history_conversations'],history_runs=staged['history_runs'],
                scope=staged['scope'],test_id=ident,request_key='score-'+ident,judge=judge,
                headers={'Authorization':'Bearer '+api_key})
            # Do not print provider content, credentials, or scoring decisions.
            print(json.dumps({'index':index,'test_id':ident,'status':result['status']}),flush=True)
            if result['status']!='settled':raise RuntimeError('Scorer request requires investigation; remaining items not dispatched')
    finally:engine.dispose()


if __name__=='__main__':main()
