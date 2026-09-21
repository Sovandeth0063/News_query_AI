import enum
from typing import List, Optional, Union, Any
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
    type: EntityType = EntityType.product
    role: EntityRole = EntityRole.mentioned
    confidence: float = Field(0.9, ge=0.0, le=1.0)
    evidence: str = Field("", max_length=200)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Entity name cannot be empty")
        return v

    @field_validator("type", mode="before")
    @classmethod
    def clean_type(cls, v: Any) -> EntityType:
        if isinstance(v, str):
            v_lower = v.lower().strip()
            for member in EntityType:
                if member.value == v_lower:
                    return member
            # Map common variations from LLMs
            if v_lower in ("company", "organization", "institution", "university", "group"):
                return EntityType.org
            if v_lower in ("tool", "library", "framework", "service", "system", "app", "application", "hardware"):
                return EntityType.product
            if v_lower in ("dataset", "eval", "evaluation", "metric", "leaderboard", "test"):
                return EntityType.benchmark
            if v_lower in ("llm", "foundation model", "weights", "checkpoint", "ai model", "agent"):
                return EntityType.model
            raise ValueError(f"Unknown entity type: {v}")
        return v

    @field_validator("role", mode="before")
    @classmethod
    def clean_role(cls, v: Any) -> EntityRole:
        if isinstance(v, str):
            v_lower = v.lower().strip()
            for member in EntityRole:
                if member.value == v_lower:
                    return member
        return EntityRole.mentioned

    @field_validator("confidence", mode="before")
    @classmethod
    def clean_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.9

    @field_validator("evidence", mode="before")
    @classmethod
    def truncate_or_validate_evidence(cls, v: str) -> str:
        v = str(v or "").strip()
        if len(v) > 200:
            return v[:197] + "..."
        return v


class ExtractedArticleItem(BaseModel):
    article_id: str
    event_type: EventType = EventType.other
    event_confidence: float = Field(0.85, ge=0.0, le=1.0)
    entities: List[ExtractedEntityItem] = Field(default_factory=list)
    takeaway: Optional[str] = Field(None, max_length=300)

    @field_validator("article_id", mode="before")
    @classmethod
    def coerce_article_id(cls, v: Union[int, str]) -> str:
        return str(v)

    @field_validator("event_type", mode="before")
    @classmethod
    def clean_event_type(cls, v: Any) -> EventType:
        if isinstance(v, str):
            v_lower = v.lower().strip().replace(" ", "_").replace("-", "_")
            for member in EventType:
                if member.value == v_lower:
                    return member
            if any(k in v_lower for k in ("release", "launch", "unveil", "introduce", "debut", "publish")):
                return EventType.model_release
            if any(k in v_lower for k in ("update", "upgrade", "fine_tun", "version", "patch")):
                return EventType.model_update
            if any(k in v_lower for k in ("benchmark", "eval", "score", "test")):
                return EventType.benchmark
            if any(k in v_lower for k in ("fund", "raise", "invest", "round")):
                return EventType.funding
            if any(k in v_lower for k in ("paper", "research", "study", "arxiv")):
                return EventType.research
            if any(k in v_lower for k in ("opinion", "analysis", "editorial", "perspective")):
                return EventType.opinion_analysis
            if any(k in v_lower for k in ("policy", "law", "regulation", "legal")):
                return EventType.policy
            raise ValueError(f"Unknown event type: {v}")
        return v

    @field_validator("event_confidence", mode="before")
    @classmethod
    def clean_event_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.85

    @field_validator("takeaway")
    @classmethod
    def clean_takeaway(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        words = v.split()
        if len(words) > 25:
            return " ".join(words[:25]) + "..."
        return v


class BatchExtractionResponse(BaseModel):
    results: List[ExtractedArticleItem] = Field(default_factory=list)
