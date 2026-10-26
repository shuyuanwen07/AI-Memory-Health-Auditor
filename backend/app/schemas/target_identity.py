"""Target-private identity candidates, never audit labels or memory merges."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


IdentityLevel = Literal["explicit", "likely", "possible", "distinct"]
IdentityCue = Literal[
    "explicit_reference", "within_source_narrative", "shared_participant", "distinctive_detail",
    "incompatible_date", "incompatible_participant", "separate_occurrence",
    "generic_role_only", "shared_name_only", "shared_venue_only",
]


class _StrictIdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class IdentityQuoteDraft(_StrictIdentityModel):
    quote_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]{0,2}$")]
    record_index: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=800)
    occurrence: int = Field(ge=0, le=500)


class IdentityQuote(IdentityQuoteDraft):
    # Unicode code-point offsets into the supplied record's decoded content.
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)


class IdentityMention(_StrictIdentityModel):
    mention_id: Annotated[str, Field(pattern=r"^M[1-9][0-9]{0,2}$")]
    quote_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]{0,2}$",
                                   description="A quote used by exactly one mention. Reuse the mention_id across relations; do not duplicate a mention for the same quote.")]


class IdentityRelation(_StrictIdentityModel):
    """One relation per unordered mention pair, even with multiple cues.

    Reversed endpoints are the same pair. Use one calibrated level and this
    relation's existing cues list/caveat rather than parallel alternatives.
    """
    relation_id: Annotated[str, Field(pattern=r"^R[1-9][0-9]{0,2}$")]
    left_mention_id: Annotated[str, Field(pattern=r"^M[1-9][0-9]{0,2}$")]
    right_mention_id: Annotated[str, Field(pattern=r"^M[1-9][0-9]{0,2}$")]
    level: IdentityLevel
    evidence_quote_ids: list[str] = Field(min_length=2, max_length=6)
    cues: list[IdentityCue] = Field(min_length=1, max_length=6,
        description="Use each legal cue at most once. After full draft validation, duplicate legal enum cues may be removed in first-occurrence order with an explicit adjustment receipt; no other cue edit is permitted.")
    caveat: str = Field(min_length=1, max_length=600)


class IdentityEvidenceDraft(_StrictIdentityModel):
    quotes: list[IdentityQuoteDraft] = Field(max_length=40)
    mentions: list[IdentityMention] = Field(max_length=24)
    relations: list[IdentityRelation] = Field(max_length=24)
    limitations: str = Field(min_length=1, max_length=1000)


class QuoteBindingAdjustment(_StrictIdentityModel):
    quote_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]{0,2}$")]
    record_index: int = Field(ge=1)
    model_quote: str = Field(min_length=1, max_length=800)
    source_quote: str = Field(min_length=1, max_length=800)
    model_occurrence: int = Field(ge=0, le=500)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)
    reason_code: Literal["unique_ascii_case_insensitive_exact_substring"]


class RelationCueAdjustment(_StrictIdentityModel):
    relation_id: Annotated[str, Field(pattern=r"^R[1-9][0-9]{0,2}$")]
    model_cues: list[IdentityCue] = Field(min_length=1, max_length=6)
    canonical_cues: list[IdentityCue] = Field(min_length=1, max_length=6)
    reason_code: Literal["stable_duplicate_enum_cues_removed"]


class IdentityEvidenceResult(_StrictIdentityModel):
    version: str
    status: Literal["analyzed", "skipped_no_context"]
    validation_scope: Literal["exact_selected_content_provenance_only"] = "exact_selected_content_provenance_only"
    source_context_sha256: str
    question_sha256: str
    quotes: list[IdentityQuote] = Field(max_length=40)
    quote_binding_adjustments: list[QuoteBindingAdjustment] = Field(default_factory=list, max_length=40)
    relation_cue_adjustments: list[RelationCueAdjustment] = Field(default_factory=list, max_length=24)
    mentions: list[IdentityMention] = Field(max_length=24)
    relations: list[IdentityRelation] = Field(max_length=24)
    limitations: str = Field(min_length=1, max_length=1000)

    def to_advisory(self) -> dict:
        """Candidate data only. It does not assert semantic verification."""
        return self.model_dump(mode="json")

    def advisory_json(self) -> str:
        return json.dumps(self.to_advisory(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class CandidateQuoteReference(_StrictIdentityModel):
    quote_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]{0,2}$")]
    candidate_id: Annotated[str, Field(pattern=r"^C[1-9][0-9]{0,5}$")]


class IdentityCandidateSelectionDraft(_StrictIdentityModel):
    quotes: list[CandidateQuoteReference] = Field(max_length=40)
    mentions: list[IdentityMention] = Field(max_length=24)
    relations: list[IdentityRelation] = Field(max_length=24)
    limitations: str = Field(min_length=1, max_length=1000)


class QuoteCandidateBinding(_StrictIdentityModel):
    quote_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]{0,2}$")]
    candidate_id: Annotated[str, Field(pattern=r"^C[1-9][0-9]{0,5}$")]
    record_index: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)
    occurrence: int = Field(ge=0, le=500)
    content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    quote: str = Field(min_length=1, max_length=800)


class QuoteCandidateSelectionReceipt(_StrictIdentityModel):
    version: Literal["identity-candidate-selection-receipt-v1"]
    catalog_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    content_snapshot_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    selection_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    bindings: list[QuoteCandidateBinding] = Field(max_length=40)
