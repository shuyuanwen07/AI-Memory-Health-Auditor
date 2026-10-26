"""Prepare a metadata-only, source-disjoint LongMemEval study without viewing texts.

The scanner decodes only IDs/type/session IDs. Question, answer and session text
values are skipped as bytes; session arrays are hashed as bytes, never decoded.
No application imports, model calls, subset materialization or network access.
"""
import argparse
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path
import re

FIELDS = {'question_id', 'question_type', 'haystack_session_ids'}

def sha_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def space(buf,i):
    while i<len(buf) and buf[i] in b' \t\r\n':i+=1
    return i

def string_end(buf,i):
    assert buf[i]==34;i+=1
    while i<len(buf):
        if buf[i]==92:i+=2
        elif buf[i]==34:return i+1
        else:i+=1
    raise ValueError('Unterminated JSON string')

def value_end(buf,i):
    i=space(buf,i)
    if buf[i]==34:return string_end(buf,i)
    if buf[i] in (91,123):
        stack=[buf[i]];i+=1
        while stack:
            if buf[i]==34:i=string_end(buf,i);continue
            if buf[i] in (91,123):stack.append(buf[i])
            elif buf[i] in (93,125):
                assert (stack.pop(),buf[i]) in ((91,93),(123,125))
            i+=1
        return i
    while i<len(buf) and buf[i] not in b',]} \r\n\t':i+=1
    return i

def metadata(path):
    rows=[]
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as buf:
        i=space(buf,0);assert buf[i]==91;i=space(buf,i+1)
        while buf[i]!=93:
            start=i;assert buf[i]==123;i=space(buf,i+1);row={}
            while buf[i]!=125:
                e=string_end(buf,i);key=json.loads(buf[i:e]);i=space(buf,e);assert buf[i]==58;i=space(buf,i+1)
                if key=='haystack_sessions':
                    assert buf[i]==91;i=space(buf,i+1);hashes=[]
                    while buf[i]!=93:
                        e=value_end(buf,i);hashes.append(hashlib.sha256(buf[i:e]).hexdigest());i=space(buf,e)
                        if buf[i]==44:i=space(buf,i+1)
                    row['source_session_byte_hashes']=hashes;i+=1
                else:
                    e=value_end(buf,i)
                    if key in FIELDS:row[key]=json.loads(buf[i:e])
                    i=e
                i=space(buf,i)
                if buf[i]==44:i=space(buf,i+1)
            i+=1;row['raw_record_byte_offsets']=[start,i]
            assert all(k in row for k in FIELDS)
            assert len(row['haystack_session_ids'])==len(row['source_session_byte_hashes'])
            rows.append(row);i=space(buf,i)
            if buf[i]==44:i=space(buf,i+1)
    assert len({r['question_id'] for r in rows})==len(rows)
    return rows

def history_ids(root,excluded_root):
    # Read ID tokens only from already-materialized historical artifacts. Never
    # decode question/answer/source strings, and never scan the master dataset.
    ids=set();audit=[]
    token=re.compile(rb'"(?:question_id|case_id)"\s*:\s*"([^"\\]+)"')
    selected=re.compile(rb'"selected_ids"\s*:\s*\[([^]]*)\]')
    for path in sorted(root.rglob('*.json')):
        if path.is_relative_to(excluded_root) or path.name=='longmemeval_s_cleaned.json':continue
        if any(part in {'upstream-evaluator','node_modules'} for part in path.parts):continue
        # Exclusion catalogs contain IDs never inspected; do not turn their
        # metadata-only candidates into evaluated evidence. Use materialized
        # subsets, declared selected protocols/suites, and actual run reports.
        allowed=(path.name.endswith('subset.json') or path.name in {'pilot-report.json','confirmation-report.json','pilot-protocol.json','confirmation-protocol.json','suite-manifest.json','study-manifest.json','pilot-sample.json'})
        if not allowed:continue

        data=path.read_bytes();found={x.decode() for x in token.findall(data)}
        for group in selected.findall(data):found.update(x.decode() for x in re.findall(rb'"([^"\\]+)"',group))
        if found:
            ids.update(found);audit.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'ids':sorted(found)})
    return ids,audit

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--history',type=Path,default=Path('experiments'));ap.add_argument('--per-type',type=int,choices=[2,3],default=2);ap.add_argument('--seed',default='stability-study-20261021-preregistered-v1');a=ap.parse_args()
    root=a.root.resolve();root.mkdir(parents=True,exist_ok=True)
    if (root/'selected-metadata.json').exists():raise ValueError('Selection already committed: do not replace or rename an evaluated set.')
    rows=metadata(a.dataset);known,files=history_ids(a.history.resolve(),root);byid={r['question_id']:r for r in rows};known_source_ids=set();known_hashes=set()
    for qid in known&byid.keys():known_source_ids.update(byid[qid]['haystack_session_ids']);known_hashes.update(byid[qid]['source_session_byte_hashes'])
    order=lambda r:hashlib.sha256((a.seed+'\0'+r['question_type']+'\0'+r['question_id']).encode()).hexdigest()
    eligible=[];excluded=[]
    for r in rows:
        reasons=[]
        if r['question_id'] in known:reasons.append('previously_materialized_or_used_id')
        if set(r['haystack_session_ids'])&known_source_ids:reasons.append('source_session_id_overlap_historical')
        if set(r['source_session_byte_hashes'])&known_hashes:reasons.append('source_session_bytes_overlap_historical')
        if reasons:excluded.append({'question_id':r['question_id'],'question_type':r['question_type'],'reasons':reasons})
        else:eligible.append(r)
    types=sorted({r['question_type'] for r in rows});selected=[];used_ids=set();used_hashes=set();selection_exclusions=[]
    # Fixed round-robin across sorted types, within each type fixed ID hash order.
    # No question, answer, source text, labels, lengths or model outputs used.
    queues={t:sorted([r for r in eligible if r['question_type']==t],key=order) for t in types}
    for _ in range(a.per_type):
        for t in types:
            while queues[t]:
                r=queues[t].pop(0)
                if set(r['haystack_session_ids'])&used_ids or set(r['source_session_byte_hashes'])&used_hashes:
                    selection_exclusions.append({'question_id':r['question_id'],'reason':'source_overlap_an_already_selected_new_case'});continue
                selected.append(r);used_ids.update(r['haystack_session_ids']);used_hashes.update(r['source_session_byte_hashes']);break
    counts=Counter(r['question_type'] for r in selected);complete=all(counts[t]==a.per_type for t in types)
    manifest={'scope':'metadata_only_source_disjoint_new_case_selection_not_yet_materialized_or_evaluated','status':'selection_complete' if complete else 'BLOCKED_INSUFFICIENT_STRICT_SOURCE_DISJOINT_CANDIDATES','seed':a.seed,'dataset_path':str(a.dataset.resolve()),'dataset_sha256':sha_file(a.dataset),'dataset_records':len(rows),'types':types,'quota_per_type':a.per_type,'historical_known_dataset_ids':sorted(known&byid.keys()),'historical_unknown_ids_count':len(known-byid.keys()),'eligible_before_new_source_dedup':dict(Counter(r['question_type'] for r in eligible)),'selected_counts':dict(counts),'source_dedup':'No shared haystack session ID OR exact raw source-session byte hash with historical or other newly selected cases','selection_uses_question_answer_source_text':False,'model_calls':0,'network_calls':0,'selected_ids':[r['question_id'] for r in selected],'selected_metadata':selected,'history_artifact_count':len(files),'history_manifest_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),'no_subset_files_materialized':True,'failure_rule':'If quotas cannot be satisfied, report blocked; do not weaken source-disjointness or silently replace with easier questions.'}
    (root/'historical-id-audit.json').write_text(json.dumps({'known_ids':sorted(known),'artifacts':files},indent=2)+'\n')
    (root/'exclusion-audit.json').write_text(json.dumps({'historical_exclusions':excluded,'within_new_selection_exclusions':selection_exclusions},indent=2)+'\n')
    (root/'selected-metadata.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k not in {'selected_metadata','historical_known_dataset_ids'}},ensure_ascii=False))

if __name__=='__main__':main()
