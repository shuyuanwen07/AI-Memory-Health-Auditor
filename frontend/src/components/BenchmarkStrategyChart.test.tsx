import {render, screen} from '@testing-library/react';
import {test, expect} from 'vitest';
import {BenchmarkStrategyChart} from './BenchmarkStrategyChart';

test('shows a shared percentage scale and retains each condition denominator',()=>{
  const {container}=render(<BenchmarkStrategyChart conditions={[{strategy:'weak',lexical_matches:0,total:2,percentage:0},{strategy:'strong',lexical_matches:1,total:2,percentage:50}]} label={value=>value==='weak'?'Weak first-hit':'Scope-aware'}/>);
  expect(screen.getByRole('img',{name:/Weak first-hit 0\/2 lexical matches, 0%; Scope-aware 1\/2 lexical matches, 50%/})).toBeInTheDocument();
  const bars=container.querySelectorAll('rect');expect(bars).toHaveLength(2);expect(bars[0].getAttribute('height')).toBe('0');expect(Number(bars[1].getAttribute('height'))).toBeCloseTo(110);
  expect(bars[0].getAttribute('fill')).not.toBe(bars[1].getAttribute('fill'));
  expect(screen.getAllByText('2 answers')).toHaveLength(2);
});

test('a condition without answers is unmeasured rather than a failed score',()=>{
  const {container}=render(<BenchmarkStrategyChart conditions={[{strategy:'empty',lexical_matches:0,total:0,percentage:0}]} label={()=>'Empty condition'}/>);
  expect(screen.getByRole('img',{name:/Empty condition 0\/0 lexical matches, Not measured/})).toBeInTheDocument();
  expect(container.querySelectorAll('rect')).toHaveLength(0);
  expect(screen.getByText('Not measured')).toBeInTheDocument();
});
