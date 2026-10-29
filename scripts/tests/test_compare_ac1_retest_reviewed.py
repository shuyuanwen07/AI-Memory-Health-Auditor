import copy
import json
import pytest
from scripts.compare_ac1_retest_reviewed import compare


def summary():
    def h(name,status):
        return {'history_id':name,'status':status,'supported':2,'invalid':0,'undecided':0,
                'reviewed_reference_facts':3,'covered_reference_facts':2,'valid_edges':1,'invalid_edges':0,
                'undecided_edges':0,'reference_edges':2,'matched_reference_edges':1}
    return {'format':'ac1-extraction-reviewed-summary-v1','reviewer_labels':['one','two'],
            'source_hashes':{'source':'same'},'histories':{'completed':[h('a','completed'),h('b','completed')],
            'partial':[h('c','partial')],'other':[]}}


def raw(x):return json.dumps(x).encode()


def test_comparison_uses_only_histories_complete_in_both():
    old=summary();new=copy.deepcopy(old)
    new['histories']['partial'].append(new['histories']['completed'].pop())
    new['histories']['completed'][0]['matched_reference_edges']=2
    result=compare(raw(old),raw(new),iterations=100)
    assert result['paired_history_ids']==['a']
    assert result['old']['reference_relationship_coverage']['value']==.5
    assert result['new']['reference_relationship_coverage']['value']==1
    assert set(result['excluded_new_incomplete'])=={'b','c'}


def test_rejects_different_sources_and_changed_reference_denominators():
    old=summary();new=copy.deepcopy(old)
    new['source_hashes']['source']='different'
    with pytest.raises(ValueError,match='different reviewed sources'):compare(raw(old),raw(new),iterations=100)
    new=copy.deepcopy(old);new['histories']['completed'][0]['reference_edges']=3
    with pytest.raises(ValueError,match='denominators differ'):compare(raw(old),raw(new),iterations=100)
