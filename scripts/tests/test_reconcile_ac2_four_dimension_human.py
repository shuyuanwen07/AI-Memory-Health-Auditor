import copy
import unittest

from scripts.reconcile_ac2_four_dimension_human_20261029 import reconcile


def templates():
    source={'source_sha256':'fixture','histories':[{'history_id':'H','source_messages':[{'id':'M','text':'Source'}],
       'facts':[{'id':'M','text':'Source','source_support':None,'reason':''}],
       'relationships':[{'source_id':'M','target_id':'M2','claimed_relation':'UPDATE','relation_validity':None,'reason':''}]}]}
    question={'source_ledger_sha256':'ledger','items':[{'review_item_id':'Q','history_id':'H','dimension':'accuracy',
       'source_messages':[{'text':'Source'}],'cited_facts':[{'fact':'Source'}],'question':'Question?',
       'reference_answer':'Answer','review':{'source_support':'','question_clarity':'','reference_answer_correctness':'','overall':'','notes':''}}]}
    sources=[copy.deepcopy(source),copy.deepcopy(source)];questions=[copy.deepcopy(question),copy.deepcopy(question)]
    for i in (0,1):sources[i]['reviewer']=questions[i]['reviewer_id']=f'reviewer-{i+1}'
    return sources,questions


def filled():
    st,qt=templates();sf=copy.deepcopy(st);qf=copy.deepcopy(qt)
    for source in sf:
        source['histories'][0]['facts'][0]['source_support']='valid'
        source['histories'][0]['relationships'][0]['relation_validity']='valid'
    for question in qf:
        for key in ('source_support','question_clarity','reference_answer_correctness','overall'):
            question['items'][0]['review'][key]='valid'
    return sf,qf,st,qt


class HumanReviewReconciliationTests(unittest.TestCase):
    def test_keeps_disagreement_and_uncertainty_unresolved(self):
        sf,qf,st,qt=filled();sf[1]['histories'][0]['relationships'][0]['relation_validity']='uncertain'
        qf[1]['items'][0]['review']['overall']='invalid'
        result=reconcile(sf,qf,st,qt)
        self.assertEqual(result['source_consensus'],{'valid':1,'unresolved':1})
        self.assertEqual(result['question_overall_consensus'],{'unresolved':1})
        self.assertEqual(result['question_rows'][0]['reviewer_2']['decisions']['overall'],'invalid')

    def test_missing_decisions_or_changed_source_and_questions_are_rejected(self):
        for kind in ('empty','source','answer','edge','contradictory','reviewer'):
            sf,qf,st,qt=filled()
            if kind=='empty':qf[0]['items'][0]['review']['overall']=''
            if kind=='source':sf[0]['histories'][0]['source_messages'][0]['text']='different'
            if kind=='answer':qf[0]['items'][0]['reference_answer']='different'
            if kind=='edge':sf[0]['histories'][0]['relationships'][0]['target_id']='different'
            if kind=='contradictory':qf[0]['items'][0]['review']['question_clarity']='invalid'
            if kind=='reviewer':qf[1]['reviewer_id']='reviewer-1'
            with self.subTest(kind=kind),self.assertRaises(ValueError):reconcile(sf,qf,st,qt)

if __name__=='__main__':unittest.main()
