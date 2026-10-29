"""Test count-only progress snapshots with synthetic private payloads."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from scripts.publish_live_experiment_progress import ac1_snapshot, ac3_snapshot, PRIMARY, REPEAT


def write(path,obj): path.write_text(json.dumps(obj),encoding='utf8')


class ProgressTest(unittest.TestCase):
    def test_ac1_snapshot_is_count_only_and_preserves_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); frozen=d/'frozen.json'; journal=d/'journal';journal.mkdir()
            ids=[f'H{i:02d}' for i in range(30)]
            write(frozen,{'format':'ac1-extraction-prospective-frozen-v1','history_ids':ids,'runtime_source_sha256':'b'*64})
            digest=hashlib.sha256(frozen.read_bytes()).hexdigest()
            write(journal/'protocol.json',{'format':'ac1-extraction-ledger-v1','frozen_sha256':digest})
            for hid in ids[:3]:write(journal/f'{hid}.started.json',{'format':'ac1-extraction-start-v1','frozen_sha256':digest,'history_id':hid})
            for hid,status in zip(ids[:2],('completed','partial')):
                write(journal/f'{hid}.result.json',{'format':'ac1-extraction-result-v1','frozen_sha256':digest,'history_id':hid,'status':status,
                   'candidates':[{'private':'SECRET CANDIDATE'}],'agent_stages':[{'role':'memory_extraction','status':'completed',
                   'prompt':'SECRET PROMPT'},{'role':'relationship_analysis','status':'failed' if status=='partial' else 'completed'}]})
            out=ac1_snapshot(frozen,journal)
            self.assertEqual((out['result_histories'],out['started_without_result'],out['not_yet_observed']),(2,1,27))
            self.assertEqual(out['outcomes']['partial'],1)
            self.assertEqual(out['stage_outcomes']['relationship_analysis']['failed'],1)
            self.assertNotIn('SECRET',json.dumps(out))
            write(journal/f'{ids[1]}.result.json',{'format':'ac1-extraction-result-v1','frozen_sha256':'0'*64,'history_id':ids[1],'status':'completed'})
            with self.assertRaisesRegex(ValueError,'Invalid result evidence'):ac1_snapshot(frozen,journal)

    def test_frozen_primary_repeat_linkage(self):
        out=ac3_snapshot(PRIMARY,REPEAT)
        self.assertEqual((out['primary_histories'],out['primary_questions'],out['repeat_histories'],out['repeat_questions']),(30,120,10,40))
        with tempfile.TemporaryDirectory() as tmp:
            changed=Path(tmp)/'repeat.json'; doc=json.loads(REPEAT.read_text());doc['parent_frozen_sha256']='0'*64;write(changed,doc)
            with self.assertRaisesRegex(ValueError,'linkage'):ac3_snapshot(PRIMARY,changed)


if __name__=='__main__':unittest.main()
