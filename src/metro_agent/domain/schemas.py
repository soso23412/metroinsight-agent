"""Keep immutable source text separate from derived, explicitly versioned labels."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Relevance(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNCERTAIN = "uncertain"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Aspect(StrEnum):
    CROWDING = "拥挤客流"
    PUNCTUALITY = "延误准点"
    EQUIPMENT = "设施设备"
    CLEANLINESS = "卫生环境"
    SAFETY = "安检安全"
    TICKETING = "票务支付"
    STAFF = "服务态度"
    TRANSFER = "线路换乘"
    COMFORT = "舒适度噪音"
    ACCESSIBILITY = "无障碍"


class SourceRef(Contract):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_name: str = Field(min_length=1, max_length=255)
    row: int = Field(ge=1)


class Content(Contract):
    platform: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    content_id: str = Field(min_length=1, max_length=200)
    title: str = ""
    text: str = Field(min_length=1, max_length=200_000)
    url: str | None = None
    published_at: datetime | None = None
    collected_at: datetime | None = None
    city: str | None = None
    line: str | None = None
    source_keyword: str | None = None
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    synthetic: bool = False
    source: SourceRef
    warnings: list[str] = Field(default_factory=list)

    @field_validator("content_id", "text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank value")
        return value.strip()

    @field_validator("published_at", "collected_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        return value

    @property
    def key(self) -> str:
        # A digest avoids ambiguous delimiters when original IDs contain punctuation.
        return sha256(f"{self.platform}\0{self.content_id}".encode()).hexdigest()

    @property
    def text_sha256(self) -> str:
        return sha256(self.text.encode()).hexdigest()


class Comment(Contract):
    platform: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    comment_id: str = Field(min_length=1, max_length=200)
    content_id: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=100_000)
    media_count: int = Field(default=0, ge=0)
    text_status: Literal["present", "media_only", "empty"] = "present"
    created_at: datetime | None = None
    parent_comment_id: str | None = None
    source: SourceRef
    warnings: list[str] = Field(default_factory=list)

    @field_validator("comment_id", "content_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        return Content.nonblank(value)

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        return Content.timezone_required(value)

    @model_validator(mode="after")
    def text_state_matches(self) -> Comment:
        expected = "present" if self.text.strip() else "media_only" if self.media_count else "empty"
        if self.text_status != expected:
            raise ValueError("comment_text_status_mismatch")
        return self


class EvidenceSpan(Contract):
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def increasing(self) -> EvidenceSpan:
        if self.end <= self.start:
            raise ValueError("evidence span must have positive length")
        return self


class Analysis(Contract):
    relevance: Relevance
    sentiment: Sentiment
    aspects: list[Aspect] = Field(default_factory=list)
    event_candidate: bool = False
    event_type: str | None = Field(default=None, max_length=80)
    verification_status: Literal["unverified", "corroborated", "contradicted", "unknown"] = (
        "unverified"
    )
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    schema_version: Literal["1"] = "1"
    annotator: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    label_source: Literal["synthetic_rule", "model", "human", "legacy_prediction"]

    @model_validator(mode="after")
    def consistent(self) -> Analysis:
        if len(self.aspects) != len(set(self.aspects)):
            raise ValueError("duplicate aspects")
        if self.relevance == Relevance.IRRELEVANT and (self.aspects or self.event_candidate):
            raise ValueError("irrelevant content cannot have service aspects or events")
        if self.event_type and not self.event_candidate:
            raise ValueError("event type requires an event candidate")
        return self

    def verify_against(self, content: Content) -> None:
        for span in self.evidence:
            if content.text[span.start : span.end] != span.quote:
                raise ValueError("evidence does not match source text")
        if self.relevance == Relevance.RELEVANT and not self.evidence:
            raise ValueError("relevant annotation requires source evidence")
        if self.label_source == "synthetic_rule" and not content.synthetic:
            raise ValueError("synthetic rules cannot annotate real content")


class ImportIssue(Contract):
    source_name: str
    row: int = Field(ge=1)
    code: str


class ImportResult(Contract):
    input_rows: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    warning_rows: int = 0
    issues: list[ImportIssue] = Field(default_factory=list)
    # A report is bounded even when a file contains millions of bad rows.
    issue_limit: int = 100

    def issue(self, source_name: str, row: int, code: str) -> None:
        if len(self.issues) < self.issue_limit:
            self.issues.append(ImportIssue(source_name=source_name, row=row, code=code))

    def verify_counts(self) -> None:
        if self.input_rows != self.accepted + self.duplicates + self.rejected:
            raise ValueError("import accounting mismatch")
