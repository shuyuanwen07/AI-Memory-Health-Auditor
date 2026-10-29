#!/usr/bin/env python3
"""Publish only source-bound human-review declarations, no answer or decision text."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
folder = root / 'output/ac3-generated/AC3-ec20077e07ead83925fa38bb'
digest = hashlib.sha256((folder/'heldout-run.json').read_bytes()).hexdigest()
packet = json.loads((folder/'blind-review/blind-packet.json').read_bytes())
assert packet['format'] == 'ac3-heldout-blind-packet-v1' and packet['run_sha256'] == digest and len(packet['cases']) == 120
reviewers=[]
for i in (1,2):
    r=json.loads((folder/f'blind-review/reviewer-{i}.json').read_bytes())
    assert r['format']=='ac3-heldout-human-review-v1' and r['run_sha256']==digest and r['reviewer_slot']==i and len(r['decisions'])==120
    reviewers.append(r['reviewer_declaration']['completed_by_human'] is True)
out={'format':'ac3-review-progress-v1','questions':120,'reviewer_declarations_complete':sum(reviewers),'run_sha256':digest}
(root/'frontend/public/reports/ac3-review-progress-v1.json').write_text(json.dumps(out,indent=2)+'\n')
