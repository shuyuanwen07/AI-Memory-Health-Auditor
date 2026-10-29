import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac2ReviewedResults } from './Ac2ReviewedResults';
afterEach(()=>vi.unstubAllGlobals());
it('keeps uncertain outcomes separate from valid and invalid',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({format:'ac2-reviewed-aggregate-v1',results:{grounded:{valid:105,invalid:11,unresolved:4,denominator:120},structurally_executable:{valid:8,invalid:11,unresolved:101,denominator:120}},source_sha256:'test'})}));
  render(<Ac2ReviewedResults/>);
  expect(await screen.findByText('Valid 105 · Invalid 11 · Unresolved 4')).toBeTruthy();
  expect(screen.getByText('Valid 8 · Invalid 11 · Unresolved 101')).toBeTruthy();
  expect(screen.getByText(/neither a pass nor a fail/)).toBeTruthy();
});
