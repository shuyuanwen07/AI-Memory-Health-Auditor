import { render, screen } from '@testing-library/react';
import { StepIndicator } from './StepIndicator';

test('keeps the Ground Truth step name and exposes its plain-language meaning', () => {
  render(<StepIndicator current={1} />);
  const label = screen.getByText('Ground Truth');
  expect(label).toHaveAttribute('title', 'The conversation-supported facts you confirm as the reference for checking audit answers.');
  expect(label).toHaveAttribute('aria-label', 'Ground Truth. The conversation-supported facts you confirm as the reference for checking audit answers.');
});
