import { Steps } from 'antd';
const groundTruthHelp = 'The conversation-supported facts you confirm as the reference for checking audit answers.';
const steps = ['Conversation', 'Ground Truth', 'Configuration', 'Audit', 'Results'];
export function StepIndicator({ current }: { current: number }) {
  return <Steps size="small" current={current} items={steps.map((title) => ({
    title: title === 'Ground Truth'
      ? <span title={groundTruthHelp} aria-label={`Ground Truth. ${groundTruthHelp}`} tabIndex={0}>{title}</span>
      : title,
  }))} aria-label="Audit progress" />;
}
