"""Stage the frozen AC3 retest in the product database, without model calls."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from app.database.session import DATABASE_URL
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_retest_prepare import prepare_paired_retest
from scripts.ac3_retest_paired_freeze import canonical


def main():
    out=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen_path=out/'frozen-canonical.json'; raw=frozen_path.read_bytes(); frozen=json.loads(raw)
    if raw!=canonical(frozen):raise ValueError('Frozen file is not canonical')
    sha=hashlib.sha256(raw).hexdigest()
    sources=json.loads((out/'sources.json').read_text())
    source=Path(sources['source']).read_bytes();plan=Path(sources['plan']).read_bytes()
    reviews=[Path(path).read_bytes() for path in sources['reviews']]
    components={k:Path(v).read_bytes() for k,v in sources['components'].items()}
    setup=json.loads((out/'audit-setup.json').read_text())
    engine=create_engine(DATABASE_URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=1)
    try:
        names=set(inspect(engine).get_table_names())
        tables={'ac3_paired_budget_scopes','ac3_paired_budget_receipts'}
        if names & tables:
            raise ValueError('Existing research budget tables require inspection; none will be replaced')
        prepared=prepare_paired_retest(engine,frozen,source,plan,reviews,components,setup)
        with engine.begin() as conn:
            for statement in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
                if statement.strip():conn.execute(text(statement))
        billing=out/'billing-scope.json'
        billing.write_text(json.dumps({'historical_billing_status':'unreconciled',
            'prior_cost_not_assumed_zero':True,'user_authorized_no_spending_cap':True},ensure_ascii=False)+'\n')
        record={'format':'ac3-paired-tracking-only-v1','frozen_sha256':sha,
            'fixed_before_target_results':True,'historical_billing_status':'unreconciled',
            'billing_sha256':hashlib.sha256(billing.read_bytes()).hexdigest(),
            'target_reservation_usd':'.001','scorer_reservation_usd':'.001'}
        budget=out/'budget-scope.json';budget.write_text(json.dumps(record,indent=2)+'\n')
        ledger=PairedBudgetLedger(engine,frozen_path=frozen_path,frozen_sha256=sha,source=source,plan=plan,
            reviews=reviews,components=components,budget_path=budget,
            budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),billing_path=billing)
        ledger.register('ac3-authorized-retest-v1')
        ids=[case['history_id'] for case in frozen['suite']['cases']]
        conv={hid:'AC3C'+hashlib.sha256(f'{sha}|{hid}'.encode()).hexdigest()[:32].upper() for hid in ids}
        runs={hid:'AC3R'+hashlib.sha256(f'{sha}|{hid}'.encode()).hexdigest()[:32].upper() for hid in ids}
        result={'format':'ac3-authorized-staging-v1','frozen_sha256':sha,'history_conversations':conv,
            'history_runs':runs,'scope':'ac3-authorized-retest-v1','preparation':prepared,
            'model_called':False,'historical_billing_status':'unreconciled'}
        with (out/'staged.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps({'history_count':len(ids),'test_count':prepared['test_count'],'model_called':False}))
    finally:engine.dispose()


if __name__=='__main__':main()
