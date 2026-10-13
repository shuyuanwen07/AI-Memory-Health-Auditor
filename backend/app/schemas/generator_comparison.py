from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.schemas.domain import ReassessmentRequest


class GeneratorSelection(BaseModel):
    model_config = {'extra':'forbid'}
    provider: Literal['rule_based','openrouter','openai','deepseek','gemini']
    model: str | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def fixed_model(self):
        validated = ReassessmentRequest(evaluator_provider=self.provider, evaluator_model=self.model)
        self.model = validated.evaluator_model
        return self


class GeneratorComparisonRequest(BaseModel):
    model_config = {'extra':'forbid'}
    creation_request_key: str = Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    source_run_id: str = Field(min_length=1,max_length=40)
    generators: list[GeneratorSelection] = Field(min_length=2,max_length=5)

    @model_validator(mode='after')
    def distinct(self):
        identities = {(item.provider,item.model if item.provider != 'rule_based' else None) for item in self.generators}
        if len(identities) != len(self.generators):
            raise ValueError('Choose each test generator only once.')
        return self
