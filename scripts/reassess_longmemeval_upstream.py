"""Apply pinned upstream task rubrics to every saved pilot reply using Luna."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys

from longmemeval_grading import load_upstream_prompt, UPSTREAM_INSTRUCTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    output = root / 'upstream-reassessment.json'
    if output.exists():
        raise ValueError('Preserve the existing reassessment; use a new release directory.')
    prompt_for, binding = load_upstream_prompt(root / 'upstream-evaluator')
    os.environ['DATABASE_URL'] = 'sqlite://'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.extraction.llm import PipelineLLMClient

    manifest = json.loads((root / 'suite-manifest.json').read_text())
    tasks = []
    for entry in manifest['cases']:
        directory = root / entry['directory']
        report = json.loads((directory / 'pilot-report.json').read_text())
        raw = json.loads((directory / 'pilot-subset.json').read_text())[0]
        assert report['status'] == 'completed'
        assert hashlib.sha256((directory / 'pilot-subset.json').read_bytes()).hexdigest() == entry['subset_sha256']
        for condition in report['benchmark_result']['conditions']:
            case = condition['cases'][0]
            tasks.append({'strategy': condition['strategy'], 'case_id': case['case_id'],
                'category': entry['category'], 'question': case['question'],
                'reference': case['expected_answer'], 'response': case['response_text'],
                'prompt': prompt_for(raw['question_type'], raw['question'], raw['answer'],
                                     case['response_text'], abstention='_abs' in raw['question_id'])})
    report = {'scope': 'automated_upstream_rubric_reassessment_of_saved_pilot_only',
              'upstream': binding, 'target_model_calls': 0, 'planned_assessments': len(tasks),
              'status': 'running', 'assessments': [],
              'notice': 'Pinned upstream task rules with Luna and JSON adaptation; not the official scorer execution, independent human labels or new target trials. Original labels and replies retained.'}

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    def assess(task):
        client = PipelineLLMClient('openrouter', manifest['reader'])
        result = {k: task[k] for k in ('strategy', 'case_id', 'category', 'question', 'reference', 'response')}
        try:
            verdict = client.complete_json(
                instructions=UPSTREAM_INSTRUCTIONS,
                prompt=task['prompt'], schema_name='longmemeval_upstream_rubric_assessment',
                schema={'type': 'object', 'additionalProperties': False, 'required': ['correct', 'reason'],
                        'properties': {'correct': {'type': 'boolean'},
                                       'reason': {'type': 'string', 'minLength': 1, 'maxLength': 800}}},
                max_output_tokens=1024, agent_role='benchmark_upstream_rubric_assessment',
                prompt_template_version='longmemeval-upstream-rubric-json-v1')
            assert type(verdict.get('correct')) is bool and isinstance(verdict.get('reason'), str)
            result.update(status='completed', verdict=verdict)
        except Exception as exc:
            result.update(status='failed', error_code=type(exc).__name__)
        result['execution'] = client.last_execution
        return result

    save()
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(assess, task) for task in tasks]):
            result = future.result()
            report['assessments'].append(result)
            save()
            print(json.dumps({'event': 'rubric_assessment_finished', 'count': len(report['assessments']),
                              'planned': len(tasks), 'status': result['status']}), flush=True)
    report['status'] = 'completed' if all(r['status'] == 'completed' for r in report['assessments']) else 'partial_failure'
    save()
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
