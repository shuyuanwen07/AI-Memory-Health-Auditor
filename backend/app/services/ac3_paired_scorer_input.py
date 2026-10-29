"""Build a source-bound, label-blind taxonomy scorer request.

The caller must supply the archived scorer loaded from its verified snapshot,
and hold the study locks while validating source records and the saved answer.
This module builds a request only; it does not call a provider or score.
"""
import hashlib
from app.schemas import Dimension, MemoryStatus
from app.target_ai.openrouter import request_options, sampling_parameters
from app.target_ai.request_contracts import build_openrouter_request_contract


def build_scorer_input(judge, test, answer, memories, question, *, frozen_test_id, frozen_sha256, answer_sha256, model, output_token_limit):
    if model!='openai/gpt-6-luna' or type(output_token_limit) is not int or output_token_limit<=0:
        raise ValueError('A fixed supported scorer and positive output limit are required')
    if (not isinstance(frozen_test_id,str) or not frozen_test_id.strip()
            or not isinstance(frozen_sha256,str) or len(frozen_sha256)!=64 or any(c not in '0123456789abcdef' for c in frozen_sha256)
            or not isinstance(question,dict) or question.get('test_id')!=frozen_test_id or question.get('question')!=test.prompt
            or question.get('expected_behavior')!=test.expected_behavior
            or question.get('supporting_memory_ids')!=test.supporting_memory_ids
            or answer.test_id!=test.test_id or answer.run_id!=test.run_id
            or not isinstance(answer.response_text,str) or not answer.response_text.strip()
            or hashlib.sha256(answer.response_text.encode()).hexdigest()!=answer_sha256):
        raise ValueError('Question or saved answer differs from frozen evidence')
    local_id='AC3'+hashlib.sha256(f'{frozen_sha256}|{test.run_id}|{frozen_test_id}'.encode()).hexdigest()[:32].upper()
    if test.test_id!=local_id:
        raise ValueError('Question identity differs from the frozen study')
    expected_ids=test.supporting_memory_ids
    if not expected_ids or len(set(expected_ids))!=len(expected_ids):
        raise ValueError('Frozen supporting memories must be unique and nonempty')
    by_id={m.memory_id:m for m in memories}
    if len(by_id)!=len(memories) or any(i not in by_id for i in expected_ids):
        raise ValueError('Supporting memory is missing or duplicated')
    relevant=[by_id[i] for i in expected_ids]
    if any(m.status not in (MemoryStatus.CONFIRMED,MemoryStatus.EDITED) or m.conversation_id!=relevant[0].conversation_id for m in relevant):
        raise ValueError('Only reviewed memories from the same source may be scored')
    prompt=judge._judge_prompt(test,answer,relevant)
    # Verify this scorer does not inherit the preassigned question category or
    # expected answer. Two independent sentinels avoid assuming text formats.
    alternate=next(d for d in Dimension if d!=test.dimension)
    probe=test.model_copy(update={'expected_behavior':'AC3_PRIVATE_REFERENCE_SENTINEL','dimension':alternate})
    if not isinstance(prompt,str) or not prompt or judge._judge_prompt(probe,answer,relevant)!=prompt:
        raise ValueError('Scorer prompt depends on private labels or expected behavior')
    instruction=judge._system_instruction()
    schema=judge._openai_schema(set(expected_ids))
    payload={'model':model,**sampling_parameters(model,0),
             'messages':[{'role':'system','content':instruction},{'role':'user','content':prompt}],
             'response_format':{'type':'json_schema','json_schema':{k:v for k,v in schema.items() if k!='type'}},
             **request_options(),'max_tokens':output_token_limit}
    contract=build_openrouter_request_contract(url='https://openrouter.ai/api/v1/chat/completions',
                                               payload=payload,role='paired_scorer')
    return {'payload':payload,'request_contract':contract,'target_answer_sha256':answer_sha256,
            'model_called':False,'human_truth_evaluated':False}
