import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_ac4_intake_confirmation import build, sha


class ConfirmationSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.receipt, self.returns = root / 'receipt', root / 'returns'
        self.receipt.mkdir(); self.returns.mkdir()
        self.reconciliation, self.independence = root / 'reconciliation.json', root / 'independence.json'
        self.reconciliation.write_text(json.dumps({'source_integrity': {'reviewer_a_return_source_sha256': 'a', 'reviewer_b_return_source_sha256': 'b'}}))
        self.independence.write_text(json.dumps({'format': 'human-review-independence-confirmation-v1', 'applies_to_return_sha256': ['a', 'b'], 'user_statement': '彼此独立，且审核前未看自动评分'}))
        before = []
        for i in range(14):
            rel = [{'relationship_id': f'R{i}', 'evidence_message_ids': [f'S{i}']}] if i < 4 else []
            before.append({'memory_id': f'M{i}', 'status': 'candidate', 'canonical_value': f'private memory {i}', 'source_message_ids': [f'S{i}'], 'relationships': rel})
        after = [dict(row, status='confirmed') for row in before]
        files = {'current-conversation.json': {'private': 'source'}, 'current-memories.json': before, 'confirmed-ground-truth-response.json': after}
        for name, value in files.items():
            (self.receipt / name).write_text(json.dumps(value))
        returns_sha = {}
        for n in (1, 2):
            items = []
            for row in before:
                items.append({'candidate_id': row['memory_id'], 'proposed_memory': row['canonical_value'], 'source_message_ids': row['source_message_ids'],
                              'review': {'decision': 'accept', 'relationship_review': [{'relationship_id': rel['relationship_id'], 'decision': 'accept', 'supporting_source_message_ids': rel['evidence_message_ids']} for rel in row['relationships']]}})
            path = self.returns / f'reviewer-{n}-with-previous-progress.json'
            path.write_text(json.dumps({'queues': [{'queue_id': 'current_source_intake_candidates_14', 'items': items}]})); returns_sha[f'reviewer-{n}'] = sha(path)
        manifest = {'format': 'ac4-human-confirmation-application-v1', 'response_status': 200, 'model_calls': 0,
                    'confirmed_count': 14, 'returns_sha256': returns_sha,
                    'reconciliation_sha256': sha(self.reconciliation),
                    'files': {name: sha(self.receipt / name) for name in files}}
        (self.receipt / 'manifest.json').write_text(json.dumps(manifest))

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregate_omits_private_values(self):
        result = build(self.receipt, self.returns, self.independence, self.reconciliation)
        self.assertEqual((result['candidate_count'], result['human_confirmed_count'], result['relationships_reviewed']), (14, 14, 4))
        self.assertFalse(result['target_audit_at_confirmation'])
        self.assertNotIn('private memory', json.dumps(result))

    def test_refuses_changed_confirmation_and_review(self):
        p = self.receipt / 'confirmed-ground-truth-response.json'
        original = p.read_text()
        p.write_text('[]')
        with self.assertRaises(ValueError):
            build(self.receipt, self.returns, self.independence, self.reconciliation)
        p.write_text(original)
        p = self.returns / 'reviewer-2-with-previous-progress.json'
        p.write_text('{}')
        with self.assertRaises(ValueError):
            build(self.receipt, self.returns, self.independence, self.reconciliation)

    def test_refuses_unbound_independence_statement(self):
        self.independence.write_text('{}')
        with self.assertRaises(ValueError):
            build(self.receipt, self.returns, self.independence, self.reconciliation)


if __name__ == '__main__':
    unittest.main()
