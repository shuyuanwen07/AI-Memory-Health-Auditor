import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FourStrategyHumanResults, isFourStrategyHumanSummary } from './FourStrategyHumanResults';

class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const strategy = () => ({agreed_pass:40,agreed_fail:30,uncertain:15,disagreement:5,total:90,distinct_questions:30});
const report = () => ({format:'four-strategy-human-public-summary-v1',source_run_sha256:'a'.repeat(64),
  strategies:{weak_first_hit:strategy(),strong_rule_based:strategy(),scope_aware:strategy(),temporal_importance:strategy()},
  reviewer_procedure:Array.from({length:2},()=>({completed_by_human:true,completed_independently:true,
    has_seen_automated_or_aggregate_results:false,used_ai_assistance:true})),adjudicated:false,automatic_scores_replaced:false});

it('accepts only a complete summary for the same source run',()=>{
  expect(isFourStrategyHumanSummary(report(),'a'.repeat(64))).toBe(true);
  expect(isFourStrategyHumanSummary(report(),'b'.repeat(64))).toBe(false);
  const bad=report();bad.strategies.scope_aware.uncertain=14;
  expect(isFourStrategyHumanSummary(bad,'a'.repeat(64))).toBe(false);
  const incomplete=report();incomplete.reviewer_procedure[0].completed_by_human=false;
  expect(isFourStrategyHumanSummary(incomplete,'a'.repeat(64))).toBe(false);
});

it('shows received human counts separately and describes review exposure',async()=>{
  vi.stubGlobal('ResizeObserver',TestResizeObserver);
  vi.stubGlobal('fetch',vi.fn((url:string)=>Promise.resolve({ok:true,json:async()=>
    url.includes('human-review') ? report() : {run_sha256:'a'.repeat(64)}})));
  render(<FourStrategyHumanResults/>);
  expect(await screen.findByText('Four strategies · human review')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:'Human reviewer agreement by strategy'})).toBeInTheDocument();
  expect(screen.getByText(/automated scores are unchanged/)).toBeInTheDocument();
  expect(screen.getByText(/Both reviewers report independent review/)).toBeInTheDocument();
});

it('shows that human results are unavailable instead of silently hiding the section',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false}));
  render(<FourStrategyHumanResults/>);
  expect(await screen.findByText(/Human-review results are not available/)).toBeInTheDocument();
});
