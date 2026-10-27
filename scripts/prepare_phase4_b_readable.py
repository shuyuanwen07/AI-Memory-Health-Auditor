"""Readable copies of pending B review materials; original packets stay frozen."""
import hashlib,html,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];source=ROOT/'artifacts/local/phase4-20261027/blind-review';out=ROOT/'artifacts/local/phase4-followup-20261027/B-readable-review';out.mkdir(exist_ok=True)
def esc(x):return html.escape(str(x))
for index in [1,2]:
 dest=out/f'reviewer-{index}';dest.mkdir(exist_ok=True);origin=source/f'reviewer-{index}';material=json.loads((origin/'materials.json').read_text())
 for name in ['materials.json','labels-to-complete.json']:shutil.copyfile(origin/name,dest/name)
 page=['<!doctype html><meta charset="utf-8"><title>B source and answer review</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto;line-height:1.5}article{padding:20px;border:1px solid #bbb;margin:22px 0}pre{white-space:pre-wrap}</style><h1>B: pending independent source and answer review</h1><p>Read source evidence and complete labels-to-complete.json independently. This is a readable copy, with the same frozen JSON material and blank label template. No strategy name or automatic outcome is displayed. If you have seen automatic B results or discussed the AI analysis, disclose that in a separate note; do not describe the return as a blind review. Do not copy an AI draft as independently authored gold.</p><h2>72 actual answers</h2>']
 for x in material['responses']:
  page.append('<article><h3>'+esc(x['item_id'])+'</h3><details><summary>Original source</summary>'+''.join('<p>'+esc(m['message_id']+': '+m['content'])+'</p>' for m in x['source_messages'])+'</details><p><b>Question:</b> '+esc(x['question'])+'</p><p><b>Actual response:</b> '+esc(x['response'])+'</p><p>Record pass/fail/uncertain; actual failure dimension when failed; supporting source IDs; note.</p></article>')
 page.append('<h2>12 question-validity checks</h2>')
 for q in material['question_validity']:
  page.append('<article><h3>'+esc(q['item_id'])+'</h3><p>'+esc(q['question'])+'</p><p><b>Expected behaviour:</b> '+esc(q['expected_behavior'])+'</p><details><summary>Original source</summary>'+''.join('<p>'+esc(m['message_id']+': '+m['content'])+'</p>' for m in q['source_messages'])+'</details><p>Check grounding, clarity, temporal scope, answer leakage, and prompt/reference alignment.</p></article>')
 page.append('<h2>Three extraction and relationship histories</h2>')
 for x in material['extraction_and_relationships']:
  page.append('<article><h3>'+esc(x['item_id'])+'</h3>'+''.join('<p>'+esc(m['message_id']+': '+m['content'])+'</p>' for m in x['source_messages']))
  for candidate in x['candidates']:page.append('<pre>'+esc(json.dumps(candidate,indent=2))+'</pre>')
  page.append('<p>Review each candidate fact and proposed relationship, cite source evidence, and list missing facts and missing relationships. Free-text fact units need reconciliation before precision/recall is calculated.</p></article>')
 (dest/'review.html').write_text(''.join(page))
 (dest/'README.txt').write_text('Read review.html. Complete labels-to-complete.json independently; do not alter IDs or material_sha256. Leave unknown verdicts uncertain. Use your own reviewer pseudonym and set independently_completed only if genuinely completed. Return a separate note stating whether you saw automatic B results or the AI cross-check. This readable copy does not establish blinding. No reviewer labels have been filled for you.\n')
 with zipfile.ZipFile(out/f'reviewer-{index}.zip','w',zipfile.ZIP_DEFLATED) as z:
  for f in dest.iterdir():z.write(f,f.name)
 assert (dest/'materials.json').read_bytes()==(origin/'materials.json').read_bytes()
 assert (dest/'labels-to-complete.json').read_bytes()==(origin/'labels-to-complete.json').read_bytes()
(out/'manifest.json').write_text(json.dumps({'purpose':'Readable pending B review; no new labels','source_JSON_and_blank_templates_byte_identical':True,'packets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.zip')}},indent=2));print(out)
