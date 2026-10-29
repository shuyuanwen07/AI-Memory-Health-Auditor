"""Read-only paired-retest budget bridge; live dispatch remains disabled.

It checks target and scorer allocations together. Caller-supplied prior cost
is an assumption until independently reconciled with provider billing.
"""
from pathlib import Path
from app.services.ac3_budget_guard import BudgetedDispatchLedger
from scripts.ac3_retest_budget_plan import budget_plan, combined_budget_preflight


class PairedBudgetBridge(BudgetedDispatchLedger):
    def __init__(self, engine, frozen_path, frozen_sha256, reservation, *, source, plan, reviews, components,
                 prior_upper_bound_usd, scorer_reserved_usd):
        super().__init__(engine,frozen_path,frozen_sha256,reservation)
        self.source,self.plan,self.reviews,self.components=source,plan,reviews,components
        self.prior,self.scorer=prior_upper_bound_usd,scorer_reserved_usd

    def preview(self):
        path=Path(self.frozen_path)
        if path.is_symlink() or not path.is_file():raise ValueError('Expected a regular frozen study file')
        target=budget_plan(path.read_bytes(),self.frozen_sha256,self.source,self.plan,self.reviews,
                           self.components,str(self.reservation))
        combined=combined_budget_preflight(prior_upper_bound_usd=self.prior,
            target_reserved_usd=target['planned_target_reservations_usd'],scorer_reserved_usd=self.scorer,
            max_usd=target['max_usd'])
        return {'format':'ac3-paired-budget-bridge-preview-v1','target':target,'combined':combined,
                'billing_reconciled':False,'execution_supported':False,
                'limitation':'No scope registration, provider dispatch or settlement is enabled.'}

    def register(self,*args,**kwargs):
        raise ValueError('Paired budget registration remains disabled until atomic settlement is integrated')

    def begin(self,*args,**kwargs):
        raise ValueError('Paired target dispatch remains disabled until atomic settlement is integrated')

    def record_pending_response(self,*args,**kwargs):
        raise ValueError('Paired settlement remains disabled until atomic settlement is integrated')
