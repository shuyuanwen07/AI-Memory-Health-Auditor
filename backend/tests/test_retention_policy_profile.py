"""An explicit prospective retention choice preserves legacy configuration bytes."""
import pytest
from pydantic import ValidationError

from app.schemas.target_profile import TargetMemoryProfile


def test_legacy_default_does_not_add_a_retention_key_to_saved_profile():
    profile = TargetMemoryProfile()
    assert profile.retention_policy == "scope_recency"
    assert "retention_policy" not in profile.model_dump(mode="json")


def test_explicit_coverage_choice_is_saved_and_restored():
    profile = TargetMemoryProfile(retention_policy="source_coverage")
    saved = profile.model_dump(mode="json")
    assert saved["retention_policy"] == "source_coverage"
    assert TargetMemoryProfile(**saved).retention_policy == "source_coverage"


@pytest.mark.parametrize("value", [None, "automatic", "SOURCE_COVERAGE", 1, False, {}, []])
def test_unknown_retention_choice_is_rejected(value):
    with pytest.raises(ValidationError):
        TargetMemoryProfile(retention_policy=value)
