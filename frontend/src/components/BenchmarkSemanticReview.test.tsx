import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { BenchmarkSemanticReview } from './BenchmarkSemanticReview';

const calls=vi.hoisted(()=>({importSemanticReview:vi.fn()}));
vi.mock('../services/api',()=>({api:calls}));
const source=[{question_id:'case_abs',question:'What year?',answer:'Unknown'}];
const evidence={conditions:[{strategy:'no_memory',cases:[]},{strategy:'full_context',cases:[]}]};
const row={question_id:'case_abs',hypothesis:'Insufficient information.',autoeval_label:{model:'contract-fixture',label:true}};
const report={version:'fixture',run_id:'hidden-system-id',strategy:'no_memory',evaluator_model:'contract-fixture',evaluator_revision:'0'.repeat(40),total:2,reviewed:1,correct:1,pending:1,percentage:null,lexical_disagreements:1,categories:[{category:'single-session-user',total:2,reviewed:1,correct:1,percentage:null}],cases:[{case_id:'hidden-question-id',category:'single-session-user',question:'What year?',expected_answer:'Unknown',response_text:'Insufficient information.',lexical_match:false,semantic_correct:true},{case_id:'hidden-other-id',category:'single-session-user',question:'Where?',expected_answer:'Perth',response_text:'Unknown.',lexical_match:false,semantic_correct:null}],notice:'Imported automated assessments, not independently verified.'};
beforeEach(()=>{vi.clearAllMocks();calls.importSemanticReview.mockResolvedValue(report);});
async function upload(kind:string,value:unknown,name:string){
  fireEvent.change(screen.getByLabelText(`Semantic review ${kind}`),{target:{files:[new File([typeof value==='string'?value:JSON.stringify(value)],name,{type:'application/json'})]}});
  await screen.findByText(name);
}
async function files(){await upload('source',source,'original.json');await upload('evidence',evidence,'saved.json');await upload('scores',JSON.stringify(row)+'\n','scores.jsonl');}

test('requires matching source evidence scores and declared revision, without starting model calls',async()=>{
  const user=userEvent.setup();render(<BenchmarkSemanticReview/>);
  expect(screen.getByRole('button',{name:'Validate & compare assessments'})).toBeDisabled();
  await files();expect(screen.getByRole('button',{name:'Validate & compare assessments'})).toBeDisabled();
  await user.type(screen.getByLabelText('Semantic review evaluator revision'),'0'.repeat(40));
  await user.click(screen.getByRole('button',{name:'Validate & compare assessments'}));
  await screen.findByText('Imported automated assessment summary');
  expect(calls.importSemanticReview).toHaveBeenCalledWith({source,evidence,rows:[row],strategy:'no_memory',evaluator_revision:'0'.repeat(40)});
  expect(screen.getByText('Assessment incomplete — no overall score is shown.')).toBeInTheDocument();
  expect(screen.getByText(/1 assessments differ/)).toBeInTheDocument();
  expect(screen.queryByText('50% labelled correct in this saved pilot')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Inspect answers and changed assessments'}));
  expect(screen.getByText('Word match: no · Imported semantic assessment: correct')).toBeInTheDocument();
  expect(screen.getByText('Word match: no · Imported semantic assessment: awaiting assessment')).toBeInTheDocument();
  expect(screen.queryByText('hidden-system-id')).not.toBeInTheDocument();
  expect(screen.queryByText('hidden-question-id')).not.toBeInTheDocument();
});

test('reports complete pilot separately and invalidates stale report on edits',async()=>{
  calls.importSemanticReview.mockResolvedValue({...report,reviewed:2,pending:0,percentage:50});
  const user=userEvent.setup();render(<BenchmarkSemanticReview/>);await files();
  await user.type(screen.getByLabelText('Semantic review evaluator revision'),'0'.repeat(40));await user.click(screen.getByRole('button',{name:'Validate & compare assessments'}));
  await screen.findByText('50% labelled correct in this saved pilot');
  expect(screen.getByText(/Complete pilot coverage is not an official full-benchmark score/)).toBeInTheDocument();
  await user.clear(screen.getByLabelText('Semantic review evaluator revision'));
  expect(screen.queryByText('Imported automated assessment summary')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Validate & compare assessments'})).toBeDisabled();
});

test('rejects malformed files and clears prior valid score file',async()=>{
  const user=userEvent.setup();render(<BenchmarkSemanticReview/>);await files();await user.type(screen.getByLabelText('Semantic review evaluator revision'),'0'.repeat(40));
  fireEvent.change(screen.getByLabelText('Semantic review scores'),{target:{files:[new File(['{"bad"}'],'bad.jsonl')]}});
  await screen.findByText('Choose a valid JSON file, or one complete JSON object per line for evaluation output.');
  expect(screen.getByRole('button',{name:'Validate & compare assessments'})).toBeDisabled();expect(calls.importSemanticReview).not.toHaveBeenCalled();
});

test('server rejects different saved reply and does not retain an old success report',async()=>{
  const user=userEvent.setup();render(<BenchmarkSemanticReview/>);await files();await user.type(screen.getByLabelText('Semantic review evaluator revision'),'0'.repeat(40));
  await user.click(screen.getByRole('button',{name:'Validate & compare assessments'}));await screen.findByText('Imported automated assessment summary');
  calls.importSemanticReview.mockRejectedValue(new Error('An evaluated hypothesis differs from the exact saved reply.'));
  await user.click(screen.getByRole('button',{name:'Validate & compare assessments'}));
  await screen.findByText('An evaluated hypothesis differs from the exact saved reply.');
  expect(screen.queryByText('Imported automated assessment summary')).not.toBeInTheDocument();
});
