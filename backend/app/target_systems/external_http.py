"""Backend-configured independent system; only authorised history and tasks cross the seam.

Remote implementations must guarantee namespace-scoped idempotency. This is a
contract adapter, not a claim that any vendor integration has been validated.
"""
import os
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx
from fastapi import HTTPException
from app.schemas import AuditRun, Conversation, TargetResponse, TestCase
from app.target_systems.interfaces import TargetSystemAdapter


class ExternalHttpTargetSystemAdapter(TargetSystemAdapter):
    adapter_id = "external-http"
    version = "external-http-v1"

    def __init__(self, db, audit: AuditRun):
        self.audit = audit
        self.endpoint = os.getenv("EXTERNAL_TARGET_URL", "").strip().rstrip("/")
        if not self.endpoint.startswith(("https://", "http://")):
            raise HTTPException(422, "The independent target service is not configured on the backend.")
        self._ready = False

    def _post(self, operation: str, payload: dict) -> dict:
        key = os.getenv("EXTERNAL_TARGET_API_KEY", "").strip()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                response = client.post(f"{self.endpoint}/{operation}", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("invalid contract")
            return data
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "The independent target service did not return a valid response. Check its contract and availability.") from None

    def ingest(self, conversation: Conversation) -> None:
        if not conversation.authorised:
            raise HTTPException(422, "Only authorised history may be sent to the target service.")
        result = self._post("ingest", {
            "namespace": self.audit.run_id,
            "messages": [message.model_dump(mode="json") for message in conversation.messages],
            "target": {"provider": self.audit.provider.value, "model": self.audit.model,
                       "temperature": self.audit.temperature},
            "memory_profile": self.audit.target_memory_profile.model_dump(),
            "memory_strategy": self.audit.memory_strategy.value,
        })
        if result.get("namespace") != self.audit.run_id or result.get("ready") is not True:
            raise HTTPException(502, "The independent target service did not confirm an isolated memory namespace.")
        self._ready = True

    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        if not self._ready:
            raise HTTPException(409, "Ingest authorised history before requesting an answer.")
        started = time.perf_counter()
        result = self._post("answer", {"namespace": audit.run_id, "request_id": test.test_id, "prompt": test.prompt})
        text = result.get("response_text")
        if result.get("namespace") != audit.run_id or result.get("request_id") != test.test_id or not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise HTTPException(502, "The independent target response did not match this question and memory namespace.")
        return TargetResponse(response_id=f"R{uuid4().hex.upper()}", run_id=audit.run_id,
                              test_id=test.test_id, model=audit.model, temperature=audit.temperature,
                              response_text=text.strip(), created_at=datetime.now(timezone.utc),
                              execution_metadata={"request_attempts": 1, "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                                                  "response_source": "external-http"})

    def trace(self) -> dict:
        # A remote success is not proof that the model received or used memory.
        return {"adapter_id": self.adapter_id, "adapter_version": self.version, "observability": "black_box"}

    def reset(self) -> None:
        # Release this local handle; do not delete the remote namespace during
        # partial retries. Its lifecycle is governed by the remote contract.
        self._ready = False
