import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CompactExperimentResults } from './CompactExperimentResults';

vi.mock('./DynamicStudies',()=>({
  useDynamicStudies:()=>({data:{a:null,campaign:null,errors:[]},refresh:vi.fn()}),
  DynamicA:()=>null,
}));
afterEach(()=>vi.unstubAllGlobals());

it('shows the latest quality, paired policies and repair without duplicate historical quality studies',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
    if(path.includes('bc-astra-repeat-retest'))return {ok:false};
    try { const report=JSON.parse(readFileSync(resolve(process.cwd(),`public${path}`),'utf8'));if(path.includes('b-astra-four-strategy'))report.status='ai_only_human_confirmation_pending';if(path.includes('ac2-astra-ten-source')){delete report.ten_scene_retest;if(report.latest_repair_retest)report.latest_repair_retest.human_review='pending';}return {ok:true,json:async()=>report}; }
    catch { return {ok:false}; }
  }));
  render(<CompactExperimentResults/>);
  expect(await screen.findByLabelText('Four-history writer repair results')).toHaveTextContent('12/16 · 75.0% passed');
  expect(screen.getByLabelText('Four-history writer repair results')).toHaveTextContent('16/16 · 100.0% passed');
  expect(await screen.findByText('14 valid · 14 invalid · 0 unresolved · 12 not generated')).toBeInTheDocument();
  expect(await screen.findByLabelText('Latest generation repair retest')).toHaveTextContent('4/4 saved · two AI reviews: 4 valid · human confirmation pending');
  expect(await screen.findByLabelText('Astra four-strategy paired review')).toHaveTextContent('human confirmation pending');
  expect(screen.getByText('C · LongMemEval · GPT-6 Luna')).toBeInTheDocument();
  expect(screen.queryByText('120/120 · 100.0% valid')).not.toBeInTheDocument();
  expect(screen.queryByText('New sources · AC2 generation')).not.toBeInTheDocument();
  expect(screen.queryByText('B · Results by ability')).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Historical results, evidence and limitations →'})).toHaveAttribute('href','/research-results');
});

it('replaces the older B and C panels when the matched-size retest is available',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
    try {const report=JSON.parse(readFileSync(resolve(process.cwd(),`public${path}`),'utf8'));return {ok:true,json:async()=>report};}
    catch{return {ok:false};}
  }));
  render(<CompactExperimentResults/>);
  expect(await screen.findByText('B & C · Astra repeated comparison')).toBeInTheDocument();
  expect(screen.getByLabelText('B Astra repeated retest')).toBeInTheDocument();
  expect(screen.getByLabelText('C Astra repeated retest')).toBeInTheDocument();
  expect(await screen.findByLabelText('A Astra max audit-method retest')).toBeInTheDocument();
  expect(await screen.findByLabelText('AC3 Astra max paired retest')).toHaveTextContent('63/69 · 91.3%');
  expect(screen.queryByText('AC3 · Auditor before and after')).not.toBeInTheDocument();
  expect(screen.queryByText(/Reviewed historical study: each method found/)).not.toBeInTheDocument();
  expect(screen.queryByText('C · LongMemEval · GPT-6 Luna')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Astra four-strategy paired review')).not.toBeInTheDocument();
});
