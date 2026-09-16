const steps=['Conversation','Ground Truth','Configuration','Audit','Results'];
export function StepIndicator({current}:{current:number}) { return <ol className="steps" aria-label="Audit progress">{steps.map((step,i)=><li key={step} className={i<=current?'active':''}><span>{i+1}</span>{step}</li>)}</ol>; }
