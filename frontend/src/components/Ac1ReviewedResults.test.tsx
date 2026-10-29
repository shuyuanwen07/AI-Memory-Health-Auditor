import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac1ReviewedResults } from './Ac1ReviewedResults';

afterEach(()=>vi.unstubAllGlobals());
it('shows complete and partial sensitivity results with matching limitations', async()=>{
  const ratio=(n:number,d:number)=>({numerator:n,denominator:d,value:n/d});
  const make=(a:number,b:number,c:number,d:number)=>({supported_candidate_precision_decided:ratio(a,a),reference_fact_id_matched_coverage:ratio(b,c),relationship_precision_decided:ratio(61,62),reference_relationship_coverage_conservative:ratio(61,d)});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({format:'ac1-reviewed-aggregate-v2',primary_histories:29,partial_histories:1,primary:make(185,228,231,86),sensitivity:make(192,236,239,89),source_sha256:'test'})}));
  render(<Ac1ReviewedResults/>);
  expect(await screen.findByText('185/185 · 100.0%')).toBeTruthy();
  expect(screen.getByText(/Including observed partial output: 236\/239/)).toBeTruthy();
  expect(screen.getByText(/not strict recall/)).toBeTruthy();
  expect(screen.getByText(/unknown, not a confirmed omission/)).toBeTruthy();
});
