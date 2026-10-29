import {render, screen} from '@testing-library/react';
import {expect, test} from 'vitest';
import {ExperimentAMethodChart} from './ExperimentAMethodChart';

const condition=(label:string,value:number|null)=>({label,category_coverage:{covered_dimensions:value===null?0:2,total_dimensions:4,value},response_level:{true_positives:1,false_negatives:1,false_positives:0,true_negatives:2,failure_detection_recall:value,false_positive_rate:value},failure_discovery_rate:{discovered_distinct_failures:value===null?null:1,known_distinct_failures:value===null?null:2,value}});

test('plots measured Experiment A rates with their denominators',()=>{
  const {container}=render(<ExperimentAMethodChart conditions={[condition('Direct questions',0.5),condition('Fixed templates',1)]}/>);
  expect(screen.getByRole('img',{name:/Category Coverage by test method.*Direct questions: 50.0%, 2\/4 dimensions/})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Response-level Failure Detection Recall by test method.*Direct questions: 50\.0%, 1\/2 labelled failures; Fixed templates: 100\.0%, 1\/2 labelled failures/})).toBeInTheDocument();
  expect(container.querySelectorAll('rect')).toHaveLength(8);
});

test('renders missing Experiment A metrics as unmeasured, without a zero bar',()=>{
  const {container}=render(<ExperimentAMethodChart conditions={[condition('Awaiting labels',null)]}/>);
  expect(screen.getAllByText(/Not measured/).length).toBeGreaterThan(0);
  expect(container.querySelectorAll('rect')).toHaveLength(0);
});

test('explains that discovery uses researcher-mapped frozen defect IDs',()=>{
  render(<ExperimentAMethodChart conditions={[condition('Fixed templates',0.5)]}/>);
  const chart = screen.getByRole('img', {name:/Failure Discovery Rate by test method.*frozen defect IDs mapped by a researcher to responses marked Fail/});
  expect(chart).toBeInTheDocument();
  expect(chart.closest('figure')?.querySelector('figcaption')).toHaveTextContent(/mapping and reviewer identity are self-declared/);
});
