"""Publish counts only from the private reviewer reconciliation and user confirmation."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
combined = root / 'output/proposal-delivery/reconciliation-combined-2026-10-28.json'
confirmation = root / 'output/proposal-delivery/human-review-user-confirmation-2026-10-28.json'
distinct_confirmation = root / 'output/proposal-delivery/human-review-distinct-reviewers-confirmation-2026-10-28.json'
independence_confirmation = root / 'output/proposal-delivery/human-review-independence-user-confirmation-2026-10-28.json'
data, full, declaration = (json.loads(p.read_text()) for p in (source, combined, confirmation))
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert data['format'] == full['format'] == 'multi-reviewer-private-reconciliation-v1'
assert declaration['reconciliation_sha256'] == digest(source)
assert declaration['user_statement'] == '确认 都是人工审核的 只是没有改过来'
distinct = json.loads(distinct_confirmation.read_text())
assert distinct['earlier_confirmation_sha256'] == digest(confirmation)
assert distinct['applies_to_return_sha256'] == declaration['applies_to_return_sha256']
assert distinct['user_statement'] == '是由不同的人的'
independence = json.loads(independence_confirmation.read_text())
assert independence['prior_confirmation_sha256'] == digest(distinct_confirmation)
assert independence['applies_to_return_sha256'] == declaration['applies_to_return_sha256']
counts = data['counts']
assert counts['item_count'] == counts['agreement_count'] + counts['unresolved_item_count']
v7 = full['queues']['four_strategy_v7_answers']['item_counts']
summary = {
    'format': 'human-review-summary-v1',
    'baseline_items': counts['item_count'],
    'agreement': counts['agreement_count'],
    'uncertain': counts['unresolved_item_count'] - counts['disagreement_count'],
    'disagreement': counts['disagreement_count'],
    'additional_fact_disagreements': counts['additional_missing_fact_disagreements'],
    'v7_items': v7['expected_items'],
    'v7_both_reviewed': v7['expected_items'] - v7['pair_unresolved'],
    'human_review_confirmed_by_user': True,
    'distinct_reviewers_confirmed_by_user': True,
    'independence_confirmed_by_user': True,
    'independence_declarations_in_original_files_conflict': True,
    'source_sha256': {'baseline': digest(source), 'combined': digest(combined), 'confirmation': digest(confirmation), 'distinct_confirmation': digest(distinct_confirmation), 'independence_confirmation': digest(independence_confirmation)},
}
destination = root / 'frontend/public/reports/human-review-summary-v1.json'
destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(summary, ensure_ascii=False))
