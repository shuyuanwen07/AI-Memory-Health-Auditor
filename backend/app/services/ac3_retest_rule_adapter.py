"""Adapt a local evaluator result to the paired retest scoring contract.

The caller must select and verify the isolated baseline snapshot, exact saved
answer and frozen inputs. This helper does not authorize a live study.
"""
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator


def score_rule(test, response, memories):
    result=RuleBasedBehaviourEvaluator().evaluate(test,response,memories)
    verdict='uncertain' if result.passed is None else ('pass' if result.passed else 'fail')
    classification=result.failure_classification
    # Legacy test-dimension labels are not observed failure diagnoses.
    failure_type=(result.failure_type.value if verdict=='fail' and result.failure_type is not None
                  and classification.status=='classified' else None)
    return {'verdict':verdict,'failure_type':failure_type,'reason':result.reason,
            'evidence_memory_ids':result.evidence_memory_ids,
            'classification_status':classification.status,'evaluator':result.evaluator}
