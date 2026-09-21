import enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class EventType(str, enum.Enum):
    model_release = "model_release"
    model_update = "model_update"
    benchmark = "benchmark"
    funding = "funding"
    research = "research"
    opinion_analysis = "opinion_analysis"
    policy = "policy"
    other = "other"


class EntityType(str, enum.Enum):
    model = "model"
    org = "org"
    person = "person"
    benchmark = "benchmark"
    product = "product"


class EntityRole(str, enum.Enum):
    subject = "subject"
    mentioned = "mentioned"


class ExtractedEntityItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    type: EntityType
    role: EntityRole = EntityRole.mentioned
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = Field(..., max_length=200)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Entity name cannot be empty")
        return v

    @field_validator("evidence", mode="before")
    @classmethod
    def truncate_or_validate_evidence(cls, v: str) -> str:
        v = str(v or "").strip()
        if len(v) > 200:
            return v[:197] + "..."
        return v


class ExtractedArticleItem(BaseModel):
    article_id: str
    event_type: EventType
    event_confidence: float = Field(0.0, ge=0.0, le=1.0)
    entities: List[ExtractedEntityItem] = Field(default_factory=list)
    takeaway: Optional[str] = Field(None, max_length=300)

    @field_validator("article_id", mode="before")
    @classmethod
    def coerce_article_id(cls, v: Union[int, str]) -> str:
        return str(v)

    @field_validator("takeaway")
    @classmethod
    def clean_takeaway(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Max 25 words per spec, or enforce reasonable length
        words = v.split()
        if len(words) > 25:
            return " ".join(words[:25]) + "..."
        return v


class BatchExtractionResponse(BaseModel):
    results: List[ExtractedArticleItem] = Field(default_factory=list)
