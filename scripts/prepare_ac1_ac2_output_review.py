"""Prepare two empty AC1/AC2 source-review packets from saved system output.

This is an offline handoff; it never executes a model or supplies judgments.
The caller must independently verify that the output export came from the app.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from scripts.ac3_fixed_suite_adapter import compile_mock


def _read(path, digest):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Evidence must be a regular file')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Evidence digest mismatch')
    return json.loads(raw)


def _time(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.tzinfo is None: raise ValueError('A timezone-aware timestamp is required')
    return date.astimezone(timezone.utc)


def make_packets(frozen_path, frozen_sha, reservation, protocol_path, protocol_sha, predictions_path, predictions_sha):
    frozen=_read(frozen_path,frozen_sha); protocol=_read(protocol_path,protocol_sha); output=_read(predictions_path,predictions_sha)
    stage=compile_mock(Path(frozen_path),frozen_sha,reservation)
    if (protocol.get('format')!='ac1-ac2-validation-protocol-v1' or protocol.get('status')!='frozen' or
        protocol.get('source_frozen_sha256')!=frozen_sha or protocol.get('runtime_source_sha256')!=output.get('runtime_source_sha256')):
        raise ValueError('A separately frozen, runtime-bound AC1/AC2 protocol is required')
    if (output.get('format')!='ac1-ac2-system-output-v1' or output.get('protocol_sha256')!=protocol_sha or
        output.get('source_frozen_sha256')!=frozen_sha or _time(output['collection_started_at_utc'])<=_time(protocol['frozen_at_utc'])):
        raise ValueError('Output must bind to the protocol and begin after its recorded freeze')
    if output.get('extractor')!=protocol.get('extractor') or output.get('test_generator')!=protocol.get('test_generator'):
        raise ValueError('Saved extractor and generator must match the predeclared conditions')
    suite={case['history_id']:case for case in frozen['suite']['cases']}
    plan=stage.get('reviewed_fact_plan'); rows=output.get('histories')
    if not plan or not isinstance(rows,list) or len(rows)!=len(suite) or len({row['history_id'] for row in rows})!=len(rows) or {row['history_id'] for row in rows}!=set(suite):
        raise ValueError('Every reviewed source history must have one saved output')
    if protocol.get('history_count')!=len(suite): raise ValueError('Predeclared history count differs')
    packed=[]
    for row in rows:
        hid=row['history_id']; source=suite[hid]; references=plan['histories'][hid]
        if not isinstance(row.get('source_record_id'),str) or not row['source_record_id'].strip() or not isinstance(row.get('extraction_record_id'),str) or not row['extraction_record_id'].strip() or not isinstance(row.get('generator_record_id'),str) or not row['generator_record_id'].strip():
            raise ValueError('Each output needs application source/extraction/generator record IDs')
        if any(row.get(key) not in ('completed','failed','unknown') for key in ('extraction_status','generation_status')):
            raise ValueError('Each system stage needs an explicit completion or failure status')
        candidates=row.get('candidates'); edges=row.get('relationships'); tests=row.get('generated_tests')
        if not all(isinstance(x,list) for x in (candidates,edges,tests)):
            raise ValueError('Saved candidates, relationships and generated tests are required')
        def ids(items,key):
            values=[x.get(key) for x in items if isinstance(x,dict)]
            if len(values)!=len(items) or any(not isinstance(x,str) or not x.strip() for x in values) or len(set(values))!=len(values):
                raise ValueError('Saved output IDs must be nonempty and unique within their category')
        ids(candidates,'candidate_id'); ids(edges,'relationship_id'); ids(tests,'test_id')
        requested = protocol.get('generated_tests_per_history')
        if not isinstance(requested,int) or isinstance(requested,bool) or requested < 1:
            raise ValueError('Predeclared per-history test budget is required')
        if any(not isinstance(x.get('canonical_value'),str) or not x['canonical_value'].strip() or not isinstance(x.get('source_message_ids'),list) for x in candidates):
            raise ValueError('Candidate content and cited sources are required')
        if any(not isinstance(x.get('prompt'),str) or not x['prompt'].strip() or not isinstance(x.get('expected_behavior'),str) or not x['expected_behavior'].strip() or not isinstance(x.get('generator_version'),str) or not x['generator_version'].strip() or x.get('generator_version')=='ac3-quarantined-stage-v1' for x in tests):
            raise ValueError('Actual generated tests with expected behaviour are required; curated AC3 tests are not generator evidence')
        for e in edges:
            if e.get('relationship_type') not in ('UPDATE','CONFLICT','CONTEXTUAL_OVERRIDE') or any(not isinstance(e.get(k),str) or not e[k] for k in ('from_candidate_id','to_candidate_id')):
                raise ValueError('Saved relationship type and endpoints are required')
        packed.append({'history_id':hid,'source_messages':source['source_messages'],
            'reviewed_reference_facts':references['facts'],'reviewed_reference_relationships':references['relationships'],
            'saved_system_record_ids':{'source':row['source_record_id'],'extraction':row['extraction_record_id'],'generator':row['generator_record_id']},
            'saved_stage_status':{'extraction':row['extraction_status'],'generation':row['generation_status']},
            'requested_generated_test_count':requested,'saved_generated_test_count':len(tests),
            'missing_generated_test_count':max(0,requested-len(tests)),
            'candidates':[{'candidate':c,'review':{'supported':None,'matched_reference_fact_ids':[],'note':''}} for c in candidates],
            'relationships':[{'relationship':e,'review':{'correct':None,'note':''}} for e in edges],
            'generated_tests':[{'test':t,'review':{'grounded':None,'structurally_executable':None,'note':''}} for t in tests]})
    instructions=['请两人独立审核，不查看对方判断；如实声明是否使用 AI。',
        '逐条核对候选记忆：supported 填 valid、invalid 或 uncertain；valid 时将语义对应的已审参考事实编号放入 matched_reference_fact_ids。一个候选可对应多条事实，但不支持的内容不能因部分匹配而判 valid。',
        '逐条检查系统预测的关系：correct 填 valid、invalid 或 uncertain；来源不支持端点或方向也应标记。只审核已有预测关系不能证明不存在遗漏。',
        '逐条检查系统自动生成的题：grounded 和 structurally_executable 各填 valid、invalid 或 uncertain；题目及预期含无来源事实则 grounded=invalid。结构可执行不代表被测模型已作答。',
        'invalid 或 uncertain 请在 note 解释。不要删除条目或直接修改来源、参考、预测内容；未匹配的参考事实不应默认视为成功。']
    return [{'format':'ac1-ac2-output-human-review-v1','reviewer_slot':slot,
             'protocol_sha256':protocol_sha,'frozen_sha256':frozen_sha,'predictions_sha256':predictions_sha,
             'instructions':instructions,'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,
                'completed_independently':None,'used_ai_assistance':None,'note':''},'histories':packed}
            for slot in (1,2)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('frozen','protocol','predictions'):
        parser.add_argument('--'+name,type=Path,required=True); parser.add_argument('--'+name+'-sha256',required=True)
    parser.add_argument('--reservation',required=True); parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    packets=make_packets(args.frozen,args.frozen_sha256,args.reservation,args.protocol,args.protocol_sha256,args.predictions,args.predictions_sha256)
    if args.output_dir.exists(): raise FileExistsError('Review output already exists')
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.ac1-ac2-review-',dir=args.output_dir.parent))
    try:
        for i,packet in enumerate(packets,1):
            path=temp/f'reviewer-{i}.json'; fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as stream: json.dump(packet,stream,ensure_ascii=False,indent=2); stream.write('\n')
        os.rename(temp,args.output_dir)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True); raise
    print(json.dumps({'reviewer_packets':2,'histories':len(packets[0]['histories']),'model_called':False,'human_decisions_created':False}))


if __name__=='__main__': main()
