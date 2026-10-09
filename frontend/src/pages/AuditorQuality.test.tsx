import '@testing-library/jest-dom/vitest';
import { render,screen } from '@testing-library/react';
import { it,expect,vi } from 'vitest';
import { AuditorQualityPage } from './AuditorQuality';
import { api } from '../services/api';
vi.mock('../services/api',()=>({api:{auditorQuality:vi.fn()}}));
it('does not display fabricated reliability percentages without human labels',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  vi.mocked(api.auditorQuality).mockResolvedValue({evaluated:8,decided:8,uncertain:0,resolved_reference_count:0,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'not_calibrated',notice:'Human references required.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:metric,decided_reference_count:0,labelled_abstention_rate:metric,failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[]});
  render(<AuditorQualityPage/>);
  expect(await screen.findByText(/Not yet calibrated:/)).toBeInTheDocument();
  expect(screen.getAllByText('Not measured')).toHaveLength(6);
  expect(screen.queryByText('100.0%')).toBeNull();
});
