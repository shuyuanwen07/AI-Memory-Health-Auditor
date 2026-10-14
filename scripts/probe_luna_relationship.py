"""Database-free relationship probe on the exact approved synthetic release."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from smoke_qwen_generation import ROOT, approved_memories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    source_path = ROOT / 'datasets/smoke/qwen-four-dimension-source-v1.json'
    memories, digest = approved_memories(
        source_path, ROOT / 'datasets/smoke/qwen-four-dimension-approval-v1.json')
    from app.extraction.llm import PipelineLLMClient
    from app.extraction.relationship_agent import RelationshipAnalysisAgent
    from app.schemas import Conversation

    class CapturingClient(PipelineLLMClient):
        raw_reply = None

        def complete_json(self, **kwargs):
            self.raw_reply = super().complete_json(**kwargs)
            return self.raw_reply

    source = json.loads(source_path.read_text())
    conversation = Conversation(
        conversation_id='SYN-QWEN-MAPLE', created_at=datetime.now(timezone.utc),
        authorised=True, source_origin='synthetic', messages=source['messages'])
    report = {'scope': 'approved_synthetic_relationship_probe_only',
              'research_evidence': False, 'database_writes': 0,
              'source_sha256': digest, 'planned_repetitions': args.repetitions,
              'trials': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(args.repetitions):
        client = CapturingClient('openrouter', 'openai/gpt-6-luna')
        agent = RelationshipAnalysisAgent(client)
        candidates = [m.model_copy(deep=True, update={'relationships': []}) for m in memories]
        trial = {'repetition': repeat + 1}
        try:
            trial['result'] = agent.analyze(conversation, candidates)
            trial['status'] = 'completed'
        except Exception as exc:
            trial.update(status='failed', error_code=type(exc).__name__)
        trial['raw_reply'] = client.raw_reply
        trial['observation'] = agent.last_observation
        report['trials'].append(trial)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'repetition': repeat + 1, 'status': trial['status']}), flush=True)


if __name__ == '__main__':
    main()
