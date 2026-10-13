from pydantic import BaseModel, Field, model_validator
from app.schemas.generator_comparison import GeneratorSelection


class ExtractionComparisonRequest(BaseModel):
    model_config = {'extra':'forbid'}
    creation_request_key: str = Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    source_run_id: str = Field(min_length=1,max_length=40)
    extractors: list[GeneratorSelection] = Field(min_length=2,max_length=5)

    @model_validator(mode='after')
    def distinct(self):
        if len({(item.provider,item.model if item.provider!='rule_based' else None) for item in self.extractors}) != len(self.extractors):
            raise ValueError('Choose each memory extractor only once.')
        return self
