"""Execute every predeclared pilot case in separate processes with bounded parallelism."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_bytes = (root / 'suite-manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    entries = manifest['cases']
    if len({e['case_id'] for e in entries}) != len(entries):
        raise ValueError('Duplicate planned cases.')
    for entry in entries:
        directory = (root / entry['directory']).resolve()
        if not directory.is_relative_to(root) or (directory / 'pilot-report.json').exists():
            raise ValueError('Use new directories; existing receipts must be preserved.')
        if hashlib.sha256((directory / 'pilot-subset.json').read_bytes()).hexdigest() != entry['subset_sha256']:
            raise ValueError('A predeclared source subset changed.')
    report = {'scope': manifest['scope'], 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'planned_cases': len(entries), 'workers': args.workers, 'status': 'running', 'cases': []}

    def save():
        (root / 'suite-execution.json').write_text(json.dumps(report, indent=2) + '\n')

    def execute(entry):
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name('run_longmemeval_pilot.py')),
                                    '--directory', str(root / entry['directory'])], capture_output=True, text=True)
        result = {'case_id': entry['case_id'], 'directory': entry['directory'],
                  'exit_code': completed.returncode, 'stdout': completed.stdout}
        # Script tracebacks contain local paths, but not request headers/body.
        if completed.returncode:
            result['error_type'] = 'case_process_failed'
        return result

    save()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, entry) for entry in entries]
        for future in as_completed(futures):
            result = future.result()
            report['cases'].append(result)
            save()
            print(json.dumps({'event': 'case_finished', 'case_id': result['case_id'],
                              'exit_code': result['exit_code'], 'completed': len(report['cases']),
                              'planned': len(entries)}), flush=True)
    report['status'] = 'completed' if all(r['exit_code'] == 0 for r in report['cases']) else 'partial_failure'
    save()
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
