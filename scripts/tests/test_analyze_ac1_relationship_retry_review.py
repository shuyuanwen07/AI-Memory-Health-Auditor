import copy

import pytest

from scripts.analyze_ac1_relationship_retry_review import analyze


def packets():
    blank = {'reviewer_label': None, 'completed_by_human': None,
             'completed_independently': None, 'used_ai_assistance': None}
    cases = [{'case_id': f'C{i}', 'source': 'source', 'review': {'correct': None, 'reason': ''}}
             for i in range(6)]
    templates = [{'reviewer_declaration': copy.deepcopy(blank), 'cases': copy.deepcopy(cases), 'slot': i}
                 for i in (1, 2)]
    reviews = copy.deepcopy(templates)
    for i, review in enumerate(reviews, 1):
        review['reviewer_declaration'] = {'reviewer_label': f'person {i}', 'completed_by_human': True,
            'completed_independently': True, 'used_ai_assistance': True}
        for case in review['cases']:
            case['review'] = {'correct': 'valid', 'reason': 'source supports the link'}
    return templates, reviews


def test_disagreement_remains_unresolved():
    templates, reviews = packets()
    reviews[1]['cases'][2]['review'] = {'correct': 'invalid', 'reason': 'different properties'}
    result = analyze(templates, reviews)
    assert [c['consensus'] for c in result['cases']] == ['valid', 'valid', 'unresolved', 'valid', 'valid', 'valid']


def test_rejects_changed_source_and_duplicate_reviewer():
    templates, reviews = packets()
    reviews[0]['cases'][0]['source'] = 'modified'
    with pytest.raises(ValueError, match='Frozen source'):
        analyze(templates, reviews)
    templates, reviews = packets()
    reviews[1]['reviewer_declaration']['reviewer_label'] = reviews[0]['reviewer_declaration']['reviewer_label']
    with pytest.raises(ValueError, match='distinct'):
        analyze(templates, reviews)
