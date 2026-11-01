"""Descriptive paired/cluster summaries for the frozen source-aware retest."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2'
POLICIES = ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance']


def quantile(values, p):
    return sorted(values)[round((len(values)-1)*p)]


def interval(values):
    rng = random.Random(20261101)
    draws = [sum(rng.choices(values, k=len(values)))/len(values) for _ in range(5000)]
    return [quantile(draws, .025), quantile(draws, .975)]


def main():
    review_path = BASE/'review/consensus.json'
    review = json.loads(review_path.read_text())
    progress = json.loads((ROOT/'frontend/public/reports/bc-astra-repeat-retest-v2.json').read_text())
    report = {'format': 'bc-clustered-descriptive-analysis-v2', 'human_confirmation_pending': True,
        'review_sha256': hashlib.sha256(review_path.read_bytes()).hexdigest(), 'studies': [],
        'method': 'Verified pass/planned slots; source-cluster bootstrap,5000draws,seed20261101. Unresolved is not a model failure. Intervals describe this selected cohort, not population generalisation.'}
    raw_agreement = sum(len(set(x['answer_judgments'])) == 1 for x in review['items'])
    c_sources = json.loads((BASE/'C/selected-source.json').read_text())
    c_strata = {s['question_id']: ('abstention' if '_abs' in s['question_id'] else s['question_type']) for s in c_sources}
    report['answer_label_agreement'] = {'agreed': raw_agreement, 'reviewed': len(review['items'])}
    for sid in ('B', 'C'):
        study_progress = next(s for s in progress['studies'] if s['id'] == sid)
        rows = [x for x in review['items'] if x['study'] == sid]
        cluster_key = 'history_id' if sid == 'B' else 'case_id'
        cluster_ids = [f'FS0{i}' for i in range(1, 5)] if sid == 'B' else [x['question_id'] for x in json.loads((BASE/'C/selected-source.json').read_text())]
        slots_per_cluster = 12 if sid == 'B' else 3
        study = {'id': sid, 'independent_source_units_at_most': len(cluster_ids), 'questions': 16, 'repetitions': 3,
            'planned_per_policy': 48, 'policies': [], 'paired_policy_differences': []}
        cluster_scores = {}
        complete = all(c['remaining'] == 0 and c['reviewed'] == c['saved'] for c in study_progress['conditions'])
        for policy in POLICIES:
            selected = [x for x in rows if x['strategy'] == policy]
            counts = Counter(x['verdict'] for x in selected)
            collected = next(c for c in study_progress['conditions'] if c['strategy'] == policy)
            scores = [sum(x['verdict'] == 'pass' for x in selected if x[cluster_key] == cid)/slots_per_cluster for cid in cluster_ids]
            cluster_scores[policy] = scores
            p = {'id': policy, 'planned': 48, 'saved': collected['saved'], 'reviewed': len(selected),
                'pass': counts['pass'], 'fail': counts['fail'], 'unresolved': counts['uncertain'],
                'missing': collected['errors'], 'not_yet_dispatched_or_returned': collected['remaining'],
                'unreviewed_answers': collected['saved']-len(selected),
                'verified_pass_coverage': counts['pass']/48,
                'decided_accuracy': counts['pass']/(counts['pass']+counts['fail']) if counts['pass']+counts['fail'] else None,
                'per_repeat': [dict(repeat=r, planned=16, **dict(Counter(x['verdict'] for x in selected if x['repeat'] == r))) for r in (1,2,3)],
                'source_cluster_interval': interval(scores) if complete else None}
            if sid == 'B':
                p['by_ability'] = {d: dict(Counter(x['verdict'] for x in selected if x.get('dimension') == d)) for d in ('accuracy','freshness','conflict_resolution','appropriate_use')}
                matched = [x for x in selected if x['history_id'] in ('FS01', 'FS02', 'FS03')]
                old = {'weak_first_hit': 3, 'strong_rule_based': 3, 'scope_aware': 0, 'temporal_importance': 0}[policy]
                p['historical_overlap'] = {'old_pass': old, 'old_questions': 12, 'old_repetitions': 1,
                    'new_pass': sum(x['verdict'] == 'pass' for x in matched), 'new_planned_answers': 36,
                    'new_questions': 12, 'new_repetitions': 3,
                    'interpretation': 'Same source questions, bundled reader configuration change; not paired independent samples or isolated delivery effect.'}
            else:
                p['by_stratum'] = {d: dict(Counter(x['verdict'] for x in selected if c_strata[x['case_id']] == d)) for d in sorted(set(c_strata.values()))}
                anchors = [x for x in selected if x['case_id'] in ('affe2881','ba61f0b9')]
                p['historical_anchors'] = {'old_luna_pass': {'weak_first_hit':0,'strong_rule_based':3,'scope_aware':0,'temporal_importance':1}[policy],
                    'old_planned':6,'new_astra_planned':6,'new_reviewed':len(anchors),
                    'new_judgments':dict(Counter(x['verdict'] for x in anchors)),
                    'interpretation':'Same two cases; changed model and output budget. Different review collection; descriptive comparison, not isolated model causation.'}
            study['policies'].append(p)
        if complete:
            for i, left in enumerate(POLICIES):
                for right in POLICIES[i+1:]:
                    differences = [a-b for a,b in zip(cluster_scores[left], cluster_scores[right])]
                    study['paired_policy_differences'].append({'left': left, 'right': right,
                        'mean_verified_coverage_difference': sum(differences)/len(differences),
                        'source_cluster_interval': interval(differences)})
        study['collection_and_review_complete'] = complete
        report['studies'].append(study)
    report['source_review'] = {'total_question_references': len(review['sources']),
        'accepted_by_both_ai': sum(s['accepted_by_both_ai'] for s in review['sources']),
        'flagged': [s for s in review['sources'] if not s['accepted_by_both_ai']]}
    output = BASE/'analysis.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'reviewed': len(review['items']), 'source_flags': len(report['source_review']['flagged']), 'complete': [s['collection_and_review_complete'] for s in report['studies']]}))


if __name__ == '__main__':
    main()
