"""Validate human-reviewed multiple facts and relationships per source message.

This is an offline validator, not a generator of facts or a claim of human
review. The separate plan must be included in the prospective freeze and
reviewed independently before a future importer may use this result.
"""
import hashlib
import json


def validate_fact_plan(suite, plan, reviews, snapshot=None):
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise ValueError('Two independent reviewed fact plans are required')
    labels = set()
    for review in reviews:
        label = review.get('reviewer_label')
        if not isinstance(label, str) or not label.strip():
            raise ValueError('Review identity required')
        labels.add(label.strip().casefold())
        if review.get('completed_by_human') is not True or review.get('completed_independently') is not True or review.get('reviewed_fact_and_relation_semantics') is not True or review.get('fact_plan_sha256') != digest:
            raise ValueError('Human review of this exact fact and relation plan is required')
    if len(labels) != 2:
        raise ValueError('Reviewers must be different people')
    checked_database = snapshot is not None
    if snapshot is None:
        # This projection only validates the plan structure. It is not evidence
        # that any confirmed memories or relationships exist in the database.
        snapshot = {'histories': {history: {
            'memories': [{'memory_id': item['memory_id'], 'status': 'confirmed',
                'canonical_value': item['canonical_value'], 'source_message_ids': [item['source_message_id']]}
                for item in section['facts']],
            'relationships': section['relationships']}
            for history, section in plan['histories'].items()}}
    cases = {c['history_id']: c for c in suite['cases']}
    if len(cases) != len(suite['cases']) or set(plan.get('histories', {})) != set(cases) or set(snapshot.get('histories', {})) != set(cases):
        raise ValueError('Each frozen history must have one reviewed plan and database snapshot')
    for history_id, case in cases.items():
        sources = {m['message_id']: m['text'] for m in case['source_messages']}
        mapping = plan['histories'][history_id]
        facts, relationships = mapping.get('facts'), mapping.get('relationships')
        if not isinstance(facts, list) or not isinstance(relationships, list) or not facts:
            raise ValueError('Facts and relationships are required')
        ids, per_source = {}, {key: [] for key in sources}
        for fact in facts:
            ident, source, span, normalized = fact.get('memory_id'), fact.get('source_message_id'), fact.get('source_span'), fact.get('canonical_value')
            if not isinstance(ident, str) or not ident.strip() or ident in ids or source not in sources or not isinstance(span, str) or not span.strip() or span not in sources[source] or not isinstance(normalized, str) or not normalized.strip():
                raise ValueError('Every reviewed fact must be unique and quote its actual source')
            ids[ident] = fact; per_source[source].append(ident)
        if any(not members for members in per_source.values()):
            raise ValueError('Every source message needs reviewed facts')
        saved = snapshot['histories'][history_id]
        memories = {x['memory_id']: x for x in saved['memories']}
        if len(memories) != len(saved['memories']) or set(memories) != set(ids):
            raise ValueError('Saved confirmed memories do not match reviewed facts')
        for ident, fact in ids.items():
            memory = memories[ident]
            if memory.get('status') not in ('confirmed', 'edited') or memory.get('canonical_value') != fact['canonical_value'] or memory.get('source_message_ids') != [fact['source_message_id']]:
                raise ValueError('Saved memory content, source or confirmation differs from reviewed fact')
        checked = set()
        for edge in relationships:
            left, right, kind, evidence = edge.get('memory_id'), edge.get('target_memory_id'), edge.get('relationship_type'), edge.get('evidence_message_ids')
            if left not in ids or right not in ids or left == right or kind not in ('UPDATE', 'CONFLICT', 'CONTEXTUAL_OVERRIDE') or not isinstance(evidence, list) or not evidence or len(set(evidence)) != len(evidence) or not set(evidence) <= set(sources):
                raise ValueError('Invalid reviewed relationship')
            key = (left, kind, right, tuple(sorted(evidence)))
            if key in checked: raise ValueError('Duplicate reviewed relationship')
            checked.add(key)
        # Bind each relationship-based test to its reviewed supporting facts,
        # not to arbitrary message numbers. Evidence may be in a third message;
        # all endpoint sources and relation-evidence sources must
        # occur in that test's explicitly reviewed source set. This permits
        # different message counts, order and cross-message relationships.
        # Appropriate use can also be grounded directly in a source fact (for
        # example, not overgeneralising an optional scoped offer). It does not
        # universally require a CONTEXTUAL_OVERRIDE edge. Never invent a hard
        # override solely to make that question pass a structural check.
        kinds_by_dimension = {'freshness': 'UPDATE', 'conflict_resolution': 'CONFLICT'}
        tests = case.get('tests')
        if not isinstance(tests, list) or not tests:
            raise ValueError('Every reviewed history needs its source-linked tests')
        for question in tests:
            kind = kinds_by_dimension.get(question.get('dimension'))
            if not kind:
                continue
            supporting = question.get('supporting_source_message_ids')
            if (not isinstance(supporting, list) or not supporting or
                    len(set(supporting)) != len(supporting) or not set(supporting) <= set(sources)):
                raise ValueError('Question supporting source IDs are incomplete or invalid')
            source_set = set(supporting)
            if not any(edge[1] == kind and
                       {ids[edge[0]]['source_message_id'], ids[edge[2]]['source_message_id']} <= source_set and
                       set(edge[3]) <= source_set for edge in checked):
                raise ValueError('Question lacks its reviewed source-backed relationship')
        actual_edges = {(x['memory_id'], x['relationship_type'], x['target_memory_id'], tuple(sorted(x['evidence_message_ids']))) for x in saved['relationships']}
        if actual_edges != checked or len(actual_edges) != len(saved['relationships']):
            raise ValueError('Saved relationships differ from reviewed plan')
    return {'fact_plan_sha256': digest, 'history_count': len(cases), 'semantic_review_declared': True,
            'database_snapshot_checked': checked_database,
            'execution_authorized': False, 'warning': 'Declaration and exact-source checks do not themselves prove human review.'}
