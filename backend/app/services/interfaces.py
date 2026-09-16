from abc import ABC, abstractmethod
from app.schemas import (
    AuditRun, Conversation, EvaluationResult, Memory, MemoryStrategy,
    TargetMemoryIngestionResult, TargetMemoryRetrievalResult, TargetResponse,
    TestCase, TestQualityAssessment,
)

class MemoryExtractor(ABC):
    @abstractmethod
    def extract(self, conversation: Conversation) -> list[Memory]: ...
class TestGenerator(ABC):
    @abstractmethod
    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]: ...
class TestQualityValidator(ABC):
    """Replaceable gate for research-quality test-suite controls."""
    @abstractmethod
    def validate(self, test: TestCase, memories: list[Memory]) -> TestQualityAssessment: ...
class TargetAIConnector(ABC):
    @abstractmethod
    def execute(self, test: TestCase, audit: AuditRun) -> TargetResponse: ...
class BehaviourEvaluator(ABC):
    @abstractmethod
    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult: ...


class TargetMemoryStore(ABC):
    """Boundary for the controlled target agent's private memory lifecycle.

    Implementations may later use a vector store or a remote agent runtime,
    while route/API and target connector contracts remain unchanged.
    """

    @abstractmethod
    def ingest(self, run_id: str, conversation: Conversation) -> TargetMemoryIngestionResult: ...

    @abstractmethod
    def retrieve(
        self, run_id: str, conversation: Conversation, test: TestCase,
        strategy: MemoryStrategy,
    ) -> TargetMemoryRetrievalResult: ...
