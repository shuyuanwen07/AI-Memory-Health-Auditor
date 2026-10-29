import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac3DevelopmentComparison, isAc3DevelopmentReport, isPairedDevelopment } from './Ac3DevelopmentComparison';

const metric=(n:number,d:number)=>({numerator:n,denominator:d,percentage:Math.round(1000*n/d)/10});
const condition=(id:string)=>({id,label:id,metrics:{failure_recall_conservative:metric(56,80),
  classification_accuracy_conservative:metric(46,56),decided_coverage:metric(88,120),false_positive_rate_decided:metric(0,32)}});
const report=()=>({format:'ac3-taxonomy-development-public-v1',sample_size:120,independent_retest:false,
  formal_acceptance_established:false,conditions:[condition('hybrid'),condition('provider_only')],limitations:['Not independent validation']});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('rejects claims of independent validation or inconsistent metric values',()=>{
  expect(isAc3DevelopmentReport(report())).toBe(true);
  expect(isAc3DevelopmentReport({...report(),independent_retest:true})).toBe(false);
  const bad=report();bad.conditions[0].metrics.decided_coverage.percentage=100;
  expect(isAc3DevelopmentReport(bad)).toBe(false);
  const invalid=report();invalid.conditions[0].metrics.false_positive_rate_decided=metric(0,41);
  expect(isAc3DevelopmentReport(invalid)).toBe(false);
});
it('labels the graph as development, keeping its denominators visible',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>report()}));
  render(<Ac3DevelopmentComparison/>);
  expect(await screen.findByText(/120 previously observed answers/)).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Development scorer comparison/})).toBeInTheDocument();
  expect(screen.getByText(/Decided-case false positives: 0\/32 vs 0\/32/)).toBeInTheDocument();
  expect(screen.getByText(/8 vs 8 were not decided/)).toBeInTheDocument();
  expect(screen.getAllByText('46/56 (82.1%)')).toHaveLength(2);
});
it('shows paired improvements and regressions without presenting abstentions as corrections',async()=>{
  const paired={format:'ac3-paired-development-public-v1',cases:120,independent_retest:false,
    run_sha256:'46c3670eafb67a2f6e3a5e40b08e5a6fa2f126a7cbd5e1aad14752c389eafdb1',rows:[
      {name:'False positives corrected',hybrid:0,provider:8}, {name:'False positives → uncertain',hybrid:8,provider:0},
      {name:'Failures newly detected',hybrid:0,provider:10}, {name:'Detected failures → pass',hybrid:0,provider:12},
      {name:'Detected failures → uncertain',hybrid:14,provider:2}]};
  expect(isPairedDevelopment(paired)).toBe(true);
  expect(isPairedDevelopment({...paired,independent_retest:true})).toBe(false);
  vi.stubGlobal('fetch',vi.fn().mockImplementation((url:string)=>Promise.resolve({ok:true,json:async()=>url.includes('paired')?paired:report()})));
  render(<Ac3DevelopmentComparison/>);
  expect(await screen.findByRole('img',{name:'Paired development changes from original judgments'})).toBeInTheDocument();
  expect(screen.getByText('Uncertain is not a correct verdict.',{exact:false})).toBeInTheDocument();
  expect(screen.getByText('Detected failures → pass')).toBeInTheDocument();
  expect(screen.getByText('12')).toBeInTheDocument();
});
