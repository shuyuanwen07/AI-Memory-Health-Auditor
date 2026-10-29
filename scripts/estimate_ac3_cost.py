"""Estimate a future AC3 run from actual v7 accounting; no model/network calls."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads((root / 'frontend/public/reports/phase4-c-four-strategy-v7.json').read_text())
cost, answers, grades = report['estimated_cost_usd'], report['total_target_answers'], report['total_usable_grades']
if answers != 360 or grades != 360 or cost > 0.40:
    raise ValueError('Unexpected v7 cost/coverage; recheck assumptions.')
remaining = 0.40 - cost
estimate = cost / answers * 32
print(json.dumps({'basis': 'v7 combined target-plus-grader cost per answer; 32 new paired answers and grades, one policy', 'v7_estimated_usd': cost, 'cap_assumption_usd': 0.40, 'remaining_if_cumulative_usd': remaining, 'rough_32_pair_estimate_usd': estimate, 'includes_new_extraction_or_test_generation': False, 'estimate_is_upper_bound': False, 'warning': 'Token lengths and pricing vary; estimate excludes extraction, retries, and any additional policies. Do not start paid calls without a frozen protocol and an enforced authorised budget.'}, indent=2))
