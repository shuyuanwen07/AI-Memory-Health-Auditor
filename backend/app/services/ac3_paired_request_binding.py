"""Bind one paired-retest target request to its guarded budget ledger.

This observer does not release a staged audit. The caller must separately
hold source/audit locks, verify frozen inputs and save private retrieval
evidence before dispatch; no public route uses this bridge.
"""
from app.services.ac3_request_binding import AC3RequestBinding


class _LedgerFacade:
    def __init__(self,ledger,request_evidence):self.ledger,self.request_evidence=ledger,request_evidence

    def begin(self,scope,frozen_sha,request_key,contract_sha,test_id):
        if frozen_sha!=self.ledger.frozen_sha256:raise ValueError('Frozen study identity changed')
        receipt=self.ledger.begin(scope,test_id,'target',request_key,contract_sha,request_evidence=self.request_evidence)
        if receipt.get('status')!='reserved' or receipt.get('provider_called') is not False:
            raise ValueError('Paired reservation failed')
        return {'state':'dispatched','duplicate':False}


class PairedTargetRequestBinding(AC3RequestBinding):
    def __init__(self,ledger,scope,frozen_sha256,request_key,test,audit,*,frozen_test_id,frozen_question,request_evidence):
        if (not isinstance(frozen_question,dict) or frozen_question.get('test_id')!=frozen_test_id
                or frozen_question.get('question')!=test.prompt):
            raise ValueError('Target question differs from the frozen question')
        if (not isinstance(request_evidence,dict) or request_evidence.get('frozen_test_id')!=frozen_test_id
                or request_evidence.get('run_id')!=audit.run_id or request_evidence.get('target_memory_context')!=test.target_memory_context
                or test.expected_behavior or test.supporting_memory_ids):
            raise ValueError('Private target input or retrieval evidence differs')
        super().__init__(_LedgerFacade(ledger,request_evidence),scope,frozen_sha256,request_key,test,audit,frozen_test_id=frozen_test_id)
