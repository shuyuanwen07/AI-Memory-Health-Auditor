"""Run one preregistered AC3 target answer once; never automatically retry."""
import argparse
import hashlib
import json
from pathlib import Path
from sqlalchemy import create_engine
from app.database.session import DATABASE_URL
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_runner import run_paired_target_step


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=int)
    parser.add_argument('--start',type=int)
    parser.add_argument('--stop',type=int)
    args=parser.parse_args()
    out=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen_path=out/'frozen-canonical.json';frozen=json.loads(frozen_path.read_bytes())
    staged=json.loads((out/'staged.json').read_text());sources=json.loads((out/'sources.json').read_text())
    source=Path(sources['source']).read_bytes();plan=Path(sources['plan']).read_bytes()
    reviews=[Path(p).read_bytes() for p in sources['reviews']]
    components={k:Path(p).read_bytes() for k,p in sources['components'].items()}
    questions=[q for case in frozen['suite']['cases'] for q in case['tests']]
    if args.index is not None:
        if args.start is not None or args.stop is not None:raise ValueError('Select one index or a range')
        indexes=range(args.index,args.index+1)
    else:
        if args.start is None or args.stop is None:raise ValueError('A bounded range is required')
        indexes=range(args.start,args.stop)
    if indexes.start<0 or indexes.stop>len(questions) or indexes.start>=indexes.stop:
        raise ValueError('Question index out of range')
    engine=create_engine(DATABASE_URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=1)
    try:
        budget=out/'budget-scope.json';ledger=PairedBudgetLedger(engine,frozen_path=frozen_path,
            frozen_sha256=staged['frozen_sha256'],source=source,plan=plan,reviews=reviews,components=components,
            budget_path=budget,budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),
            billing_path=out/'billing-scope.json')
        for index in indexes:
            ident=questions[index]['test_id']
            result=run_paired_target_step(engine,ledger=ledger,frozen=frozen,source=source,plan=plan,reviews=reviews,
                components=components,history_conversations=staged['history_conversations'],history_runs=staged['history_runs'],
                scope=staged['scope'],test_id=ident,request_key='target-'+ident)
            print(json.dumps({'index':index,'test_id':ident,**result}),flush=True)
            if result['status']!='settled':
                raise RuntimeError('Request requires investigation; remaining questions were not dispatched')
    finally:engine.dispose()


if __name__=='__main__':main()
