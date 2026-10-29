import '@testing-library/jest-dom/vitest';
import {useState} from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {TargetProfileEditor,defaultTargetProfile,supportsAnswerValidation,type TargetMemoryProfile} from './TargetProfileEditor';
import {RunSourceReview,RecordedCaseSourceReviews} from './StabilityStudyResults';
import type {StabilityRun,StabilitySplit} from '../services/stabilityStudyPackage';

afterEach(cleanup);

function Editor({initial=defaultTargetProfile,available=true,onChange}: {initial?:TargetMemoryProfile;available?:boolean;onChange:(value:TargetMemoryProfile)=>void}) {
  const [value,setValue]=useState(initial);
  return <TargetProfileEditor value={value} answerValidationAvailable={available} onChange={next=>{setValue(next);onChange(next);}}/>;
}

describe('optional answer fact check',()=>{
  it('keeps legacy defaults omitted until explicit opt in, then uses a separate8192 budget',async()=>{
    const user=userEvent.setup(),changed=vi.fn();
    expect(defaultTargetProfile).not.toHaveProperty('answer_validation');
    expect(defaultTargetProfile.output_token_limit).toBe(2048);
    render(<Editor onChange={changed}/>);
    expect(screen.getByRole('switch',{name:'Check answer facts before returning'})).not.toBeChecked();
    expect(screen.queryByRole('spinbutton',{name:'Answer check output limit'})).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox',{name:'Answer check reasoning effort'})).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox',{name:'Configuration name'}),'x');
    expect(changed.mock.calls.at(-1)![0]).not.toHaveProperty('answer_validation');
    await user.click(screen.getByRole('switch',{name:'Check answer facts before returning'}));
    expect(changed.mock.calls.at(-1)![0]).toMatchObject({answer_validation:'source_grounding',answer_validation_output_token_limit:8192,output_token_limit:2048});
    expect(changed.mock.calls.at(-1)![0]).not.toHaveProperty('answer_validation_reasoning_effort');
    expect(screen.getByRole('spinbutton',{name:'Answer check output limit'})).toHaveValue('8192');
    expect(screen.getByText(/Adds one model request/)).toBeInTheDocument();
    expect(screen.getByText(/A failed check stops the answer/)).toBeInTheDocument();
    expect(screen.getByText(/The check can still be wrong/)).toBeInTheDocument();
  });

  it.each(['low','medium'] as const)('stores explicit %s and really omits provider-default reasoning again',async effort=>{
    const user=userEvent.setup(),changed=vi.fn();
    render(<Editor initial={{...defaultTargetProfile,answer_validation:'source_grounding',answer_validation_output_token_limit:8192}} onChange={changed}/>);
    await user.click(screen.getByRole('combobox',{name:'Answer check reasoning effort'}));
    await user.click(screen.getByRole('option',{name:effort==='low'?'Low':'Medium'}));
    expect(changed.mock.calls.at(-1)![0].answer_validation_reasoning_effort).toBe(effort);
    await user.click(screen.getByRole('combobox',{name:'Answer check reasoning effort'}));
    await user.click(screen.getByRole('option',{name:'Provider default (not sent)'}));
    expect(changed.mock.calls.at(-1)![0]).not.toHaveProperty('answer_validation_reasoning_effort');
    await user.click(screen.getByRole('switch',{name:'Check answer facts before returning'}));
    expect(changed.mock.calls.at(-1)![0].answer_validation).toBe('off');
    expect(changed.mock.calls.at(-1)![0]).not.toHaveProperty('answer_validation_output_token_limit');
    expect(screen.queryByRole('combobox',{name:'Answer check reasoning effort'})).not.toBeInTheDocument();
  });

  it('does not enable unknown/unsupported targets or silently drop an existing saved opt in',async()=>{
    const changed=vi.fn();const user=userEvent.setup();
    const {rerender}=render(<TargetProfileEditor value={defaultTargetProfile} onChange={changed}/>);
    expect(screen.getByRole('switch',{name:'Check answer facts before returning'})).toBeDisabled();
    const saved={...defaultTargetProfile,answer_validation:'source_grounding' as const,answer_validation_reasoning_effort:'medium' as const};
    rerender(<TargetProfileEditor value={saved} onChange={changed}/>);
    expect(screen.getByRole('switch',{name:'Check answer facts before returning'})).toBeChecked();
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('will not be silently removed');
    expect(screen.getByRole('combobox',{name:'Answer check reasoning effort'})).toBeDisabled();
    await user.click(screen.getByRole('switch',{name:'Check answer facts before returning'}));
    expect(changed).toHaveBeenCalledWith(expect.objectContaining({answer_validation:'off'}));
  });

  it('supports only the exact controlled OpenRouter Luna target',()=>{
    expect(supportsAnswerValidation('openrouter','openai/gpt-6-luna','controlled-memory')).toBe(true);
    for(const [provider,model,system] of [['ollama','openai/gpt-6-luna','controlled-memory'],['openrouter','another-model','controlled-memory'],['openrouter','openai/gpt-6-luna','external-http'],['','','controlled-memory']]) {
      expect(supportsAnswerValidation(provider,model,system)).toBe(false);
    }
  });
});

function run(source_review:unknown):StabilityRun {
  return {round:2,arm:'strong_rule_based',status:'completed',grade_outcome:'correct',response_text:'The host placed the parcel.',semantic_grade:{correct:true,reason:'Original automated assessment.'},source_review};
}

describe('readable saved source evidence, separate from grades',()=>{
  it('shows a critical actor error and exact source beside an unchanged True grade',async()=>{
    const source={review_status:'reviewed',critical_errors:[{category:'material_source_contradiction',claim:'The host placed the parcel.',explanation:'The source assigns that action to the narrator.'}],claims:[{claim:'The host placed the parcel.',source_support:'unsupported',source_message_id:'SOURCE-Q',source_role:'user',source_observed_date:'2035-07-06',source_quote:'I placed the parcel beside the host.',supplied_quote_verified:true,explanation:'Actor direction differs.'}]};
    const saved=run(source),before=JSON.stringify(saved);
    render(<RunSourceReview run={saved}/>);
    expect(screen.getByText(/Original automatic grade:/).parentElement).toHaveTextContent('correct');
    expect(screen.getByRole('heading',{name:'Critical finding 1 · Source contradiction'})).toBeInTheDocument();
    const finding=screen.getByRole('heading',{name:'Critical finding 1 · Source contradiction'}).closest('article')!;
    expect(within(finding).getByText('The host placed the parcel.')).toBeInTheDocument();
    expect(within(finding).getByText('I placed the parcel beside the host.')).toBeInTheDocument();
    expect(within(finding).getByText(/SOURCE-Q · user · 2035-07-06/)).toBeInTheDocument();
    expect(within(finding).getByText('Present in supplied memories')).toBeInTheDocument();
    expect(screen.getByText('Source review technical record').closest('details')).not.toHaveAttribute('open');
    await userEvent.setup().click(screen.getByText('Source review technical record'));
    expect(screen.getByText((_,element)=>element?.tagName==='PRE' && element.textContent===JSON.stringify(source,null,2))).toBeInTheDocument();
    expect(JSON.stringify(saved)).toBe(before);
  });

  it.each([null,{}, {review_status:'pending',critical_errors:[]}, {review_status:'reviewed'}, {critical_errors:[]}, {review_status:'reviewed',critical_errors:'unknown'}])('does not turn missing/incomplete format into zero or safe: %j',review=>{
    render(<RunSourceReview run={run(review)}/>);
    expect(screen.getByText(/No zero-finding or safety conclusion is inferred/)).toBeInTheDocument();
    expect(screen.queryByText(/Reviewed; 0 critical findings recorded/)).not.toBeInTheDocument();
  });

  it('uses the guard agent review only, not automatic guard findings or an outer duplicate',()=>{
    render(<RunSourceReview run={run({critical_errors:['Outer automatic finding'],agent_review:{review_status:'reviewed',critical_errors:[]}})}/>);
    expect(screen.getByText(/Reviewed; 0 critical findings recorded/)).toBeInTheDocument();
    expect(screen.queryByText('Outer automatic finding')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading',{name:/Critical finding/})).not.toBeInTheDocument();
  });

  it('keeps missing claim/source details and unknown supply explicit even with a recorded finding',()=>{
    render(<RunSourceReview run={run({review_status:'reviewed',critical_errors:[{category:'unfamiliar_category',claim:'The host placed the parcel.'}]})}/>);
    expect(screen.getByText(/Exact source quotation not recorded. Inspect/)).toBeInTheDocument();
    expect(screen.getByText('Readable claim/source details not recorded.')).toBeInTheDocument();
    expect(screen.queryByText('Present in supplied memories')).not.toBeInTheDocument();
  });

  it('keeps split and condition counts separate and does not make missing groups zero-safe',()=>{
    const strong=run({review_status:'reviewed',critical_errors:[{category:'material_source_contradiction'}]});
    const weak={...run({review_status:'reviewed',critical_errors:[]}),arm:'weak_first_hit'};
    const splits:StabilitySplit[]=[
      {name:'development',planned_case_ids:['ANON-A'],rounds:[2],arms:[strong.arm,weak.arm],cases:[{case_id:'ANON-A',type:'synthetic',question:null,reference_answer:null,runs:[strong,weak]}]},
      {name:'evaluation',planned_case_ids:['ANON-B'],rounds:[2],arms:[strong.arm,weak.arm],cases:[{case_id:'ANON-B',type:'synthetic',question:null,reference_answer:null,runs:[run(null),{...run({critical_errors:[]}),arm:'weak_first_hit'}]}]},
    ];
    render(<RecordedCaseSourceReviews splits={splits}/>);
    const table=screen.getByLabelText('Source reviews by split and condition');
    const rows=within(table).getAllByRole('row');
    expect(rows).toHaveLength(5);
    const sourceRows=rows.slice(1).map(row=>row.textContent);
    expect(sourceRows).toEqual(expect.arrayContaining([
      expect.stringContaining('developmentRelationship-priority retrieval'),expect.stringContaining('developmentFirst-match retrieval'),
      expect.stringContaining('evaluationRelationship-priority retrieval'),expect.stringContaining('evaluationFirst-match retrieval'),
    ]));
    expect(within(table).getAllByText('Not assessed')).toHaveLength(2);
    expect(screen.getByText(/do not replace the package’s recorded acceptance gates or original grades/)).toBeInTheDocument();
  });
});
