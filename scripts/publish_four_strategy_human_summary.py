"""Publish only source-verified aggregate review counts, no reviewer text."""
import argparse
from scripts.prepare_v7_focused_reviews import ROOT, TEMPLATES, strategy_summary
from scripts.run_ac1_extraction import exclusive_json, read_regular


def build(raw1,raw2):
    result=strategy_summary(raw1,raw2,TEMPLATES/'PRIVATE-v7-identity-key.json',
        ROOT/'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm')
    return {'format':'four-strategy-human-public-summary-v1','source_run_sha256':result['source_run_sha256'],
            'review_sha256':result['review_sha256'],'overall_counts':result['overall_counts'],
            'strategies':result['strategies'],'adjudicated':False,'automatic_scores_replaced':False,
            'reviewer_procedure':[{'completed_by_human':d['completed_by_human'],
                'completed_independently':d['completed_independently'],
                'has_seen_automated_or_aggregate_results':d['has_seen_automated_or_aggregate_results'],
                'used_ai_assistance':d['used_ai_assistance']} for d in result['reviewer_declarations']],
            'limitations':result['limitations']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--return-1',required=True);p.add_argument('--return-2',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();exclusive_json(a.output,build(read_regular(a.return_1),read_regular(a.return_2)))


if __name__=='__main__':main()
