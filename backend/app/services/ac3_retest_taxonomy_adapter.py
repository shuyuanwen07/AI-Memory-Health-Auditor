"""Preserve validated semantic and rule-gated results as distinct observations.

No provider is called here. A caller must separately freeze both observation
definitions and enforce durable budget and request accounting before scoring.
"""
from scripts.ac3_retest_paired_integrity import FAILURE_TYPES


def _verdict(value):
    if value is not None and type(value) is not bool:raise ValueError('Verdict must be boolean or null')
    return 'uncertain' if value is None else ('pass' if value else 'fail')


def adapt_taxonomy(result, validated_provider, allowed_memory_ids):
    """Do not force a category when either verdict or classification is unknown."""
    allowed=set(allowed_memory_ids)
    hybrid_verdict=_verdict(result.passed)
    classification=result.failure_classification
    hybrid_category=(result.failure_type.value if hybrid_verdict=='fail' and result.failure_type is not None
                     and classification.status=='classified' else None)
    if hybrid_category is not None and hybrid_category not in FAILURE_TYPES:raise ValueError('Unknown hybrid category')
    hybrid={'verdict':hybrid_verdict,'failure_type':hybrid_category,'reason':result.reason,
            'classification_status':classification.status,'evidence_memory_ids':list(result.evidence_memory_ids)}
    if not set(hybrid['evidence_memory_ids']).issubset(allowed):raise ValueError('Unknown hybrid evidence')
    if validated_provider is None:
        provider={'verdict':'error','failure_type':None,'reason':'No validated provider judgment.'}
    else:
        if not isinstance(validated_provider,dict):raise ValueError('Invalid provider judgment')
        p=validated_provider
        verdict=_verdict(p.get('passed'))
        category=p.get('failure_type')
        if category is not None and (verdict!='fail' or category not in FAILURE_TYPES):raise ValueError('Invalid provider category')
        evidence=p.get('evidence_memory_ids')
        if (not isinstance(evidence,list) or any(not isinstance(x,str) for x in evidence)
                or not set(evidence).issubset(allowed) or (verdict!='uncertain' and not evidence)):
            raise ValueError('Provider evidence is invalid')
        if not isinstance(p.get('reason'),str) or not isinstance(p.get('classification_reason'),str):
            raise ValueError('Provider explanation is missing')
        provider={'verdict':verdict,'failure_type':category,'reason':p['reason'],
                  'classification_reason':p['classification_reason'],'evidence_memory_ids':evidence}
    meter=result.judge_execution.model_dump(mode='json') if result.judge_execution is not None else None
    return {'hybrid':hybrid,'provider_only':provider,'judge_execution':meter,
            'human_truth_evaluated':False,'live_runner_authorized':False}
