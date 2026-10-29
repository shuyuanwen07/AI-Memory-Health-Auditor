import hashlib
import json
import pytest
from sqlalchemy import create_engine
from app.services.ac3_retest_budget_bridge import PairedBudgetBridge
from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests


def test_bridge_checks_combined_budget_but_never_dispatches(tmp_path):
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    engine=create_engine('sqlite://')
    try:
        helper.cfg['budget']['max_usd']=.4
        raw=json.dumps(helper.freeze()).encode();path=tmp_path/'frozen.json';path.write_bytes(raw)
        def bridge(prior,scorer):
            return PairedBudgetBridge(engine,path,hashlib.sha256(raw).hexdigest(),'.001',
                source=helper.source,plan=helper.plan,reviews=helper.reviews,components=helper.components,
                prior_upper_bound_usd=prior,scorer_reserved_usd=scorer)
        within=bridge('.20','.05').preview()
        assert within['combined']['status']=='within_planning_cap'
        assert not within['execution_supported'] and not within['billing_reconciled']
        assert bridge(None,'.05').preview()['combined']['status']=='unresolved'
        assert bridge('.30','.05').preview()['combined']['status']=='over_planning_cap'
        for method in ('register','begin','record_pending_response'):
            with pytest.raises(ValueError,match='disabled'):getattr(bridge('.20','.05'),method)()
    finally:engine.dispose();helper.doCleanups()
