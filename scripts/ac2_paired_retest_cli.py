"""Persist a reviewed AC2 freeze and invoke one no-model paired run.

This is an offline local research tool. A started marker is never overwritten;
an interrupted attempt must be inspected instead of silently repeated.
"""
import argparse
import base64
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.ac2_paired_retest_freeze import frozen_digest, prepare, sha
from scripts.ac2_paired_retest_adapter import adapt, review_source
from scripts.run_ac1_extraction import ROOT, exclusive_json, read_regular, source_code_sha

CONTAINER_RUNNER = '''import base64,json,sys
from scripts.ac2_paired_retest_run import run
x=json.load(sys.stdin)
raw=lambda name:base64.b64decode(x[name],validate=True)
result=run(x['frozen'],raw('source'),raw('plan'),[raw('review1'),raw('review2')],raw('archive'),raw('candidate'),raw('validator'))
print(json.dumps(result,ensure_ascii=False))
'''


def inputs(args):
    return {key: read_regular(getattr(args, key)) for key in
            ('source', 'plan', 'review1', 'review2', 'archive', 'candidate', 'validator')}


def freeze(args):
    x = inputs(args)
    record = prepare(x['source'], x['plan'], [x['review1'], x['review2']], x['archive'],
                     x['candidate'], x['validator'], source_code_sha())
    record['cli_implementation_sha256'] = sha(Path(__file__).read_bytes())
    # The underlying paired runner validates its own frozen input; the CLI hash
    # is kept in the outer envelope rather than changing that contract.
    inner = dict(record)
    del inner['cli_implementation_sha256']
    exclusive_json(args.output, {'format': 'ac2-paired-cli-freeze-v1', 'inputs': inner,
                   'inputs_sha256': frozen_digest(inner), 'cli_implementation_sha256': record['cli_implementation_sha256']})


def execute(args):
    envelope = json.loads(read_regular(args.protocol))
    if (envelope.get('format') != 'ac2-paired-cli-freeze-v1'
            or envelope.get('cli_implementation_sha256') != sha(Path(__file__).read_bytes())
            or envelope.get('inputs_sha256') != frozen_digest(envelope.get('inputs'))):
        raise ValueError('Frozen protocol or CLI changed')
    x = inputs(args)
    current = prepare(x['source'], x['plan'], [x['review1'], x['review2']], x['archive'],
                      x['candidate'], x['validator'], source_code_sha())
    current['frozen_at_utc'] = envelope['inputs']['frozen_at_utc']
    if current != envelope['inputs']:
        raise ValueError('Frozen materials, reviews or runtime changed')
    if Path(args.output).exists():
        raise FileExistsError('Output already exists')
    payload = {key: base64.b64encode(value).decode('ascii') for key, value in x.items()}
    payload['frozen'] = envelope['inputs']
    exclusive_json(args.started, {'format': 'ac2-paired-run-started-v1',
        'protocol_sha256': sha(read_regular(args.protocol)), 'inputs_sha256': envelope['inputs_sha256'],
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'model_called': False})
    proc = subprocess.run(['docker', 'compose', 'exec', '-T', 'backend', 'python', '-c', CONTAINER_RUNNER],
                          cwd=ROOT, input=json.dumps(payload), capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise RuntimeError('Paired run failed; started marker retained: ' + proc.stderr[-1000:])
    output = json.loads(proc.stdout)
    if output.get('frozen_protocol_sha256') != envelope['inputs_sha256']:
        raise ValueError('Paired result differs from the frozen inputs')
    exclusive_json(args.output, output)


def prepare_review(args):
    """Save separate reviewer packets and an allocation key; no labels are created."""
    envelope = json.loads(read_regular(args.protocol))
    frozen = envelope['inputs']
    if (envelope.get('format') != 'ac2-paired-cli-freeze-v1'
            or envelope.get('cli_implementation_sha256') != sha(Path(__file__).read_bytes())
            or envelope.get('inputs_sha256') != frozen_digest(frozen)):
        raise ValueError('Frozen protocol or CLI changed')
    source, plan = read_regular(args.source), read_regular(args.plan)
    output = json.loads(read_regular(args.raw_output))
    runs, ledger = adapt(source, frozen, output)
    reviewed_source = review_source(source, plan, frozen)
    module_path = ROOT / 'output/proposal-delivery/ac2-prospective-retest-draft-2026-10-28/blind_pairing.py'
    if sha(module_path.read_bytes()) != frozen.get('blind_pairing_implementation_sha256'):
        raise ValueError('Blind review and analysis implementation changed after freeze')
    spec = importlib.util.spec_from_file_location('ac2_pairing_review', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet, reviews, private = module.make_packets(reviewed_source, runs)
    private['raw_output_sha256'] = sha(read_regular(args.raw_output))
    private['protocol_sha256'] = sha(read_regular(args.protocol))
    private['blind_pairing_implementation_sha256'] = sha(module_path.read_bytes())
    private['generation_ledger'] = ledger
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    # The private key must not be included in either reviewer's handoff.
    for index, review in enumerate(reviews, 1):
        exclusive_json(destination / f'reviewer-{index}.json', review)
    exclusive_json(destination / 'blind-packet.json', packet)
    (destination / 'private').mkdir(mode=0o700)
    exclusive_json(destination / 'private' / 'allocation-key.json', private)


def compare_review(args):
    """Accept two completed blind reviews only if all evidence still matches."""
    protocol_raw, raw_output = read_regular(args.protocol), read_regular(args.raw_output)
    envelope = json.loads(protocol_raw)
    frozen = envelope['inputs']
    if (envelope.get('format') != 'ac2-paired-cli-freeze-v1'
            or envelope.get('cli_implementation_sha256') != sha(Path(__file__).read_bytes())
            or envelope.get('inputs_sha256') != frozen_digest(frozen)):
        raise ValueError('Frozen protocol or CLI changed')
    source, plan = read_regular(args.source), read_regular(args.plan)
    runs, ledger = adapt(source, frozen, json.loads(raw_output))
    reviewed_source = review_source(source, plan, frozen)
    packet = json.loads(read_regular(args.packet))
    private = json.loads(read_regular(args.private_key))
    module_path = ROOT / 'output/proposal-delivery/ac2-prospective-retest-draft-2026-10-28/blind_pairing.py'
    if (private.get('protocol_sha256') != sha(protocol_raw)
            or private.get('raw_output_sha256') != sha(raw_output)
            or frozen.get('blind_pairing_implementation_sha256') != sha(module_path.read_bytes())
            or private.get('blind_pairing_implementation_sha256') != sha(module_path.read_bytes())
            or private.get('generation_ledger') != ledger):
        raise ValueError('Private key or original evidence changed')
    spec = importlib.util.spec_from_file_location('ac2_pairing_compare', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    review_raws = [read_regular(args.review1), read_regular(args.review2)]
    result = module.compare(reviewed_source, packet, [json.loads(raw) for raw in review_raws], private, runs)
    result.update({'protocol_sha256': sha(protocol_raw), 'raw_output_sha256': sha(raw_output),
                   'review_sha256': [sha(raw) for raw in review_raws],
                   'packet_sha256': sha(read_regular(args.packet)),
                   'private_key_sha256': sha(read_regular(args.private_key)),
                   'generation_ledger': ledger, 'model_called': False})
    exclusive_json(args.output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('freeze', 'run'):
        child = sub.add_parser(action)
        for key in ('source', 'plan', 'review1', 'review2', 'archive', 'candidate', 'validator', 'output'):
            child.add_argument('--'+key, required=True)
        if action == 'run':
            child.add_argument('--protocol', required=True)
            child.add_argument('--started', required=True)
    review = sub.add_parser('review')
    for key in ('protocol', 'source', 'plan'):
        review.add_argument('--'+key, required=True)
    review.add_argument('--raw-output', required=True)
    review.add_argument('--output-dir', required=True)
    compare = sub.add_parser('compare')
    for key in ('protocol', 'source', 'plan', 'raw-output', 'packet', 'private-key', 'review1', 'review2', 'output'):
        compare.add_argument('--'+key, required=True)
    args = parser.parse_args()
    {'freeze': freeze, 'run': execute, 'review': prepare_review, 'compare': compare_review}[args.action](args)


if __name__ == '__main__':
    main()
