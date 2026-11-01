"""Read-only recovery export for the frozen v2 execution smoke.

The original optional export failed while encoding its Pydantic trace model.
This companion leaves all frozen helpers and original collection evidence
unchanged. It only reads already saved rows through the guarded inspector;
it never executes/evaluates a target or writes database rows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ac2_ten_execution_common import OUTPUT_RELATIVE, check_protocol, read, sha
from scripts.register_ac2_ten_execution_smoke_20261101 import inspect


def model_json_default(value):
    """Serialize actual Pydantic evidence, never stringify unknown objects."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json')
    raise TypeError(f'Unsupported read-only evidence type: {type(value).__name__}')


def export_saved(root, protocol_path, collection_summary_path):
    root, protocol_path = Path(root), Path(protocol_path)
    collection_summary_path = Path(collection_summary_path)
    protocol = read(protocol_path)
    check_protocol(root, protocol)  # Unchanged frozen guards, before SessionLocal imports.
    protocol_hash = sha(protocol_path)
    summary_hash = sha(collection_summary_path)
    snapshot = inspect(root, protocol_path)
    if sha(protocol_path) != protocol_hash or sha(collection_summary_path) != summary_hash:
        raise ValueError('Frozen protocol or original collection summary changed during read-only export.')
    snapshot.update(collection_summary_sha256=summary_hash,
                    recovery_export_script_sha256=sha(Path(__file__)),
                    recovery_note='Read-only JSON serialization recovery after the original optional trace export failed. No model dispatch or database mutation; original collection summary remains unchanged.')
    return json.dumps(snapshot, ensure_ascii=False, default=model_json_default)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=root / OUTPUT_RELATIVE / 'protocol.json')
    parser.add_argument('--collection-summary', type=Path)
    args = parser.parse_args()
    summary = args.collection_summary or args.protocol.parent / 'collection-summary.json'
    print(export_saved(root, args.protocol, summary), flush=True)


if __name__ == '__main__':
    main()
