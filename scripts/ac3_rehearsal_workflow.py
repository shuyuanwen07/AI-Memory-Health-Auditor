"""Offline AC3 lifecycle rehearsal: no provider, database, or real results.

All responses and review decisions are explicit test fixtures. The frozen package
is validated again at each state transition. Objects are ephemeral; this module
is not an execution API and cannot be used to substantiate study findings.
"""
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from scripts.ac3_fixed_suite_adapter import compile_mock


class Rehearsal:
    def __init__(self, frozen_path, frozen_sha256, reservation='0'):
        self.path, self.digest, self.reservation = frozen_path, frozen_sha256, reservation
        stage = self._validate()
        self.items = {x['test_id']: x for x in stage['items'] if x['grounding_review'] == 'valid'}
        if not self.items:
            raise ValueError('No eligible questions')
        self.state = 'awaiting_fixture_responses'
        self.responses = {}
        self._response_digest = None
        self.reviews = {}
        self._salt = secrets.token_bytes(32)
        self._blind = {hmac.new(self._salt, k.encode(), hashlib.sha256).hexdigest()[:24]: k for k in self.items}

    def _validate(self):
        return compile_mock(self.path, self.digest, self.reservation)

    def _validate_responses(self):
        encoded = json.dumps(self.responses, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        if hashlib.sha256(encoded).hexdigest() != self._response_digest:
            raise ValueError('Frozen fixture responses changed')

    def record_fixtures(self, responses):
        self._validate()
        if self.state != 'awaiting_fixture_responses':
            raise ValueError('Responses already frozen')
        if not isinstance(responses, dict) or set(responses) != set(self.items):
            raise ValueError('Exactly one fixture response for each eligible question is required')
        if any(not isinstance(v, str) or not v.strip() for v in responses.values()):
            raise ValueError('Empty or invalid fixture response')
        self.responses = dict(responses)
        encoded = json.dumps(self.responses, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        self._response_digest = hashlib.sha256(encoded).hexdigest()
        self.state = 'awaiting_independent_fixture_reviews'

    def review_packet(self):
        self._validate()
        if self.state != 'awaiting_independent_fixture_reviews':
            raise ValueError('Fixture responses are not frozen or review is closed')
        self._validate_responses()
        return {'purpose': 'synthetic rehearsal only', 'answers': [
            {'blind_id': blind, 'question': self.items[test]['question'],
             'expected_behavior': self.items[test]['expected_behavior'], 'response': self.responses[test],
             'decision': None}
            for blind, test in sorted(self._blind.items())]}

    def submit_fixture_review(self, reviewer, decisions):
        self._validate()
        if self.state != 'awaiting_independent_fixture_reviews':
            raise ValueError('Review is closed')
        self._validate_responses()
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError('Reviewer identity required')
        reviewer = reviewer.strip().casefold()
        if reviewer in self.reviews or len(self.reviews) >= 2:
            raise ValueError('Two different reviewers required')
        if not isinstance(decisions, dict) or set(decisions) != set(self._blind):
            raise ValueError('A decision is required for each blind answer')
        if any(v not in ('pass', 'fail', 'uncertain') for v in decisions.values()):
            raise ValueError('Invalid review decision')
        self.reviews[reviewer] = dict(decisions)
        if len(self.reviews) == 2:
            self.state = 'complete_fixture_review'

    def summary(self):
        self._validate()
        if self.state != 'complete_fixture_review':
            raise ValueError('Two fixture reviews are required')
        self._validate_responses()
        first, second = self.reviews.values()
        agreed = {key: first[key] for key in self._blind if first[key] == second[key]}
        return {'purpose': 'synthetic rehearsal only; not empirical evidence', 'model_called': False,
                'reviewers': 2, 'eligible': len(self.items), 'agreement_count': len(agreed),
                'disagreement_count': len(self.items) - len(agreed),
                'pass': sum(v == 'pass' for v in agreed.values()),
                'fail': sum(v == 'fail' for v in agreed.values()),
                'uncertain': sum(v == 'uncertain' for v in agreed.values())}

    def save_checkpoint(self, path):
        """Create an immutable rehearsal checkpoint; record returned digest separately."""
        self._validate()
        if self.state != 'awaiting_fixture_responses':
            self._validate_responses()
        checkpoint = {'format': 'ac3-synthetic-rehearsal-checkpoint-v1',
                      'warning': 'synthetic rehearsal only; not human evidence',
                      'frozen_sha256': self.digest, 'reservation': self.reservation,
                      'salt': self._salt.hex(), 'state': self.state,
                      'responses': self.responses, 'reviews': self.reviews}
        return _write_new_json(path, checkpoint)

    def export_review_packet(self, path):
        """Export a blind rehearsal packet without reviewer identities or labels."""
        return _write_new_json(path, self.review_packet())

    @classmethod
    def restore_checkpoint(cls, path, expected_checkpoint_sha256, frozen_path, expected_frozen_sha256):
        """Restore by replaying validated state transitions, never trusting stored state."""
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Checkpoint must be an existing regular file')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_checkpoint_sha256:
            raise ValueError('Checkpoint digest mismatch')
        saved = json.loads(raw)
        if saved.get('format') != 'ac3-synthetic-rehearsal-checkpoint-v1' or saved.get('warning') != 'synthetic rehearsal only; not human evidence' or saved.get('frozen_sha256') != expected_frozen_sha256:
            raise ValueError('Invalid checkpoint or frozen suite binding')
        run = cls(frozen_path, expected_frozen_sha256, saved['reservation'])
        try:
            salt = bytes.fromhex(saved['salt'])
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid checkpoint blinding salt') from exc
        if len(salt) != 32:
            raise ValueError('Invalid checkpoint blinding salt')
        run._salt = salt
        run._blind = {hmac.new(salt, k.encode(), hashlib.sha256).hexdigest()[:24]: k for k in run.items}
        if saved['state'] != 'awaiting_fixture_responses':
            run.record_fixtures(saved['responses'])
        elif saved['responses']:
            raise ValueError('Unexpected responses in checkpoint')
        if not isinstance(saved['reviews'], dict):
            raise ValueError('Invalid checkpoint reviews')
        for reviewer, decisions in saved['reviews'].items():
            run.submit_fixture_review(reviewer, decisions)
        if run.state != saved['state']:
            raise ValueError('Checkpoint state does not match its records')
        return run


def _write_new_json(path, value):
    """Publish complete JSON atomically without replacing an existing path."""
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    fd, temp_name = tempfile.mkstemp(prefix='.ac3-rehearsal-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Linking is atomic and fails if the destination exists, including symlinks.
        os.link(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        os.unlink(temp_name)
    return hashlib.sha256(raw).hexdigest()
