import { Steps } from 'antd';
const steps = ['Conversation', 'Ground Truth', 'Configuration', 'Audit', 'Results'];
export function StepIndicator({ current }: { current: number }) {
  return <Steps size="small" current={current} items={steps.map(title => ({ title }))} aria-label="Audit progress" />;
}
