"""Compile reviewed AC3 questions and reference facts without database writes.

This is a read-only bridge, not a product importer or live execution path.
"""
from scripts.ac3_retest_paired_freeze import compile_isolated


def compile_reference_stage(frozen, source_raw, plan_raw, review_raws, components):
    stage = compile_isolated(frozen, source_raw, plan_raw, review_raws, components)
    plan = frozen['reviewed_fact_plan']['histories']
    cases = frozen['suite']['cases']
    if set(plan) != {case['history_id'] for case in cases}:
        raise ValueError('Reference histories differ from the frozen suite')
    histories, questions = [], []
    for case in cases:
        hid = case['history_id']
        source_ids = {row['message_id'] for row in case['source_messages']}
        facts, relations = plan[hid]['facts'], plan[hid]['relationships']
        fact_ids = [fact['memory_id'] for fact in facts]
        if len(fact_ids) != len(set(fact_ids)) or any(fact['source_message_id'] not in source_ids for fact in facts):
            raise ValueError('Reference fact identities or sources are invalid')
        for relation in relations:
            if (relation['memory_id'] not in fact_ids or relation['target_memory_id'] not in fact_ids
                    or not set(relation['evidence_message_ids']).issubset(source_ids)):
                raise ValueError('Reference relationship is not local to its history')
        histories.append({'history_id':hid, 'source_messages':case['source_messages'],
                          'reviewed_facts':facts, 'reviewed_relationships':relations})
        for question in case['tests']:
            support = question['supporting_source_message_ids']
            if not support or len(support) != len(set(support)) or not set(support).issubset(source_ids):
                raise ValueError('Question source references are missing or invalid')
            memory_ids = [fact['memory_id'] for fact in facts if fact['source_message_id'] in support]
            if not memory_ids:
                raise ValueError('Question has no reviewed reference memories')
            questions.append({'history_id':hid, **question, 'supporting_memory_ids':memory_ids})
    if [row['test_id'] for row in questions] != stage['test_ids']:
        raise ValueError('Question order or identity differs from the frozen stage')
    return {'format':'ac3-retest-reviewed-reference-stage-v1', 'protocol_sha256':stage['protocol_sha256'],
            'histories':histories, 'questions':questions, 'model_called':False,
            'database_written':False, 'execution_supported':False,
            'limitation':'Read-only mapping only; database binding, concurrency and live budget checks remain required.'}
