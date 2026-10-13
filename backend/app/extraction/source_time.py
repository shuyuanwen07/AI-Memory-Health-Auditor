"""Validate observation times against cited messages, not model-invented dates."""
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.extraction.llm import PipelineRequestError


def validate_source_time(memory: Any, messages: Iterable[Any]) -> None:
    """Unknown is allowed; a supplied time must identify a cited observation.

    Dates mentioned inside a fact belong in its text. They are not evidence
    of when the source message was observed. Offset-equivalent times compare
    equal. A historical source without a timezone may be copied exactly;
    never attach a guessed timezone or interpret it using server time.
    """
    value: datetime | None = memory.timestamp
    if value is None:
        return
    cited = set(memory.source_message_ids)
    supported = {message.timestamp for message in messages if message.message_id in cited}
    if value not in supported:
        raise PipelineRequestError(
            "The memory observation timestamp does not match a cited source message. "
            "Use the cited message timestamp or leave it unknown."
        )
