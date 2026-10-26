"""Synthetic planner budget regression; no provider requests."""
import json
import pytest
from app.test_generator.agent import AgentTestGenerator, coverage_plan_output_budget
from test_llm_pipeline import _audit, _coverage_memories


@pytest.mark.parametrize('count,expected',[(1,2048),(8,2048),(20,2048),(24,2304),(100,8192)])
def test_planner_budget_leaves_space_for_structured_notes_and_is_bounded(count,expected):
    assert coverage_plan_output_budget(count)==expected


def test_real_planner_call_uses_2048_for_eight_questions():
    captured=[]
    class Planner:
        def complete_json(self,**request):
            captured.append(request)
            payload=json.loads(request['prompt'].split('\n\n',1)[1])
            return {'selected_candidate_ids_by_dimension':{
                dimension:ids[:payload['required_available_quota_by_dimension'][dimension]]
                for dimension,ids in payload['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=Planner())
    generator._agent_observation={'semantic_reviews':[]}
    generator._build_coverage_plan(_coverage_memories(),_audit().model_copy(update={'test_budget':8}))
    assert len(captured)==1 and captured[0]['max_output_tokens']==2048
    assert captured[0]['prompt_template_version']=='coverage-planner-agent-v3'
