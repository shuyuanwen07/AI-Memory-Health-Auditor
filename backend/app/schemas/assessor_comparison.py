from pydantic import BaseModel, Field, model_validator
from app.schemas.domain import ReassessmentRequest


class AssessorComparisonRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    creation_request_key: str = Field(min_length=1, max_length=100)
    source_run_id: str = Field(min_length=1, max_length=40)
    assessors: list[ReassessmentRequest] = Field(min_length=2, max_length=5)

    @model_validator(mode='after')
    def distinct_assessors(self):
        identities = [(item.evaluator_provider, item.evaluator_model if item.evaluator_provider != 'rule_based' else None)
                      for item in self.assessors]
        if len(set(identities)) != len(identities):
            raise ValueError('Choose each assessor only once.')
        return self
