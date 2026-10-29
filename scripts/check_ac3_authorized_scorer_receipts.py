"""Check completed scorer response structure without revealing judgments."""
import json
from collections import Counter
from pathlib import Path
from sqlalchemy import text
from app.database.session import engine
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from scripts.ac3_retest_reference_stage import compile_reference_stage


def main():
    root=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen=json.loads((root/'frozen-canonical.json').read_bytes())
    paths=json.loads((root/'sources.json').read_text())
    source=Path(paths['source']).read_bytes();plan=Path(paths['plan']).read_bytes()
    reviews=[Path(p).read_bytes() for p in paths['reviews']]
    components={k:Path(p).read_bytes() for k,p in paths['components'].items()}
    questions={q['test_id']:q for q in compile_reference_stage(frozen,source,plan,reviews,components)['questions']}
    with engine.connect() as conn:
        rows=conn.execute(text("SELECT test_id,status,response_text FROM ac3_paired_budget_receipts "
            "WHERE scope_id=:scope AND role='scorer'"),{'scope':'ac3-authorized-retest-v1'}).mappings().all()
    counts=Counter()
    for row in rows:
        if row['status']!='settled':counts['unsettled']+=1;continue
        try:
            data=json.loads(row['response_text'])
            LLMBehaviourEvaluator._check_openrouter_completion(data)
            if data.get('model')!='openai/gpt-6-luna' or data['choices'][0].get('finish_reason')!='stop':
                raise ValueError('Unexpected model or incomplete output')
            parsed=LLMBehaviourEvaluator._parse_json(LLMBehaviourEvaluator._deepseek_text(data))
            passed,_,evidence=LLMBehaviourEvaluator._validated_result(parsed,set(questions[row['test_id']]['supporting_memory_ids']))
            if passed is not None and not evidence:raise ValueError('A decision requires source evidence')
            counts['valid_structure']+=1
        except (ValueError,KeyError,TypeError,IndexError):counts['invalid_structure']+=1
    print(json.dumps({'scorer_receipts':len(rows),'checks':dict(counts),'judgments_disclosed':False}))


if __name__=='__main__':main()
