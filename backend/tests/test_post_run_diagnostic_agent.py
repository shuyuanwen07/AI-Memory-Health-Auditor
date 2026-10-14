import pytest

from app.extraction.llm import PipelineRequestError
from app.diagnostics.post_run_agent import PostRunDiagnosticAgent


def _case():
    return {
        "test_id": "T001",
        "question": "Which database is current?",
        "response": "MySQL",
        "automated_passed": False,
        "layer": "input_delivery_review",
        "explanation": "Inspect the recorded final input receipt.",
        "supporting_memory_ids": ["M001"],
    }


class FakeClient:
    provider = "ollama"
    model = "qwen3:1.7b"

    def __init__(self, memory_id="M001"):
        self.memory_id = memory_id
        self.last_execution = {
            "provider": "ollama", "model": "qwen3:1.7b", "reported_model": "qwen3:1.7b",
            "request_attempts": 1, "elapsed_ms": 37.0, "status": "parsed",
        }

    def complete_json(self, **request):
        assert request["agent_role"] == "post_run_diagnostic"
        assert request["prompt_template_version"] == PostRunDiagnosticAgent.VERSION
        return {
            "summary": "Review final input assembly before changing retrieval.",
            "findings": [{
                "test_id": "T001", "focus": "input_delivery",
                "evidence_memory_ids": [self.memory_id],
                "summary": "The exact record may not have reached the target input.",
                "next_check": "Inspect the saved memory input receipt.",
                "model_confidence": 0.65,
            }],
        }


def test_post_run_diagnostic_is_structured_and_keeps_its_limits_explicit():
    agent = PostRunDiagnosticAgent(FakeClient())
    result = agent.analyse([_case()], {"T001": [{"memory_id": "M001", "canonical_value": "Use PostgreSQL."}]})

    assert result["version"] == PostRunDiagnosticAgent.VERSION
    assert result["findings"][0]["evidence_memory_ids"] == ["M001"]
    assert "does not establish causality" in result["notice"]
    assert agent.last_observation["status"] == "completed"
    assert agent.last_observation["execution"]["reported_model"] == "qwen3:1.7b"
    assert "Use PostgreSQL" in agent.last_observation["prompt"]


def test_post_run_diagnostic_rejects_memory_citations_outside_the_case():
    agent = PostRunDiagnosticAgent(FakeClient("M999"))

    with pytest.raises(PipelineRequestError, match="outside the case evidence"):
        agent.analyse([_case()], {"T001": [{"memory_id": "M001", "canonical_value": "Use PostgreSQL."}]})

    assert agent.last_observation["status"] == "failed"
    assert agent.last_observation["error_code"] == "PipelineRequestError"


@pytest.mark.parametrize('count,limit',[(1,4096),(3,4096),(20,12000),(100,12000)])
def test_diagnostic_output_budget_is_bounded_with_space_for_reasoning(count,limit):
    class BudgetClient(FakeClient):
        def complete_json(self,**request):
            assert request['max_output_tokens']==limit
            return {'summary':'Inspect the cited records before selecting changes.','findings':[{'test_id':f'T{i:03d}','focus':'insufficient_evidence','evidence_memory_ids':[],'summary':'The record does not establish a cause.','next_check':'Inspect the recorded source and input delivery.','model_confidence':0.2} for i in range(count)]}
    cases=[{**_case(),'test_id':f'T{i:03d}'} for i in range(count)]
    assert len(PostRunDiagnosticAgent(BudgetClient()).analyse(cases,{})['findings'])==count
