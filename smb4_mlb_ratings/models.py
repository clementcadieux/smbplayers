from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SeasonValue = float | int | dict[str, float | int] | None


@dataclass(slots=True)
class PlayerInput:
    name: str
    role: str
    team: str | None = None
    age: int | None = None
    primary_position: str | None = None
    secondary_position: str | None = None
    bats: str | None = None
    throws: str | None = None
    metrics: dict[str, SeasonValue] = field(default_factory=dict)
    samples: dict[str, SeasonValue] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerInput":
        return cls(
            name=data["name"],
            role=data["role"],
            team=data.get("team"),
            age=data.get("age"),
            primary_position=data.get("primary_position"),
            secondary_position=data.get("secondary_position"),
            bats=data.get("bats"),
            throws=data.get("throws"),
            metrics=data.get("metrics", {}),
            samples=data.get("samples", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class TraitSuggestion:
    name: str
    chemistry_type: str | None
    polarity: str
    confidence: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "chemistry_type": self.chemistry_type,
            "polarity": self.polarity,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(slots=True)
class PersonalityRecommendation:
    chemistry_type: str
    score: float
    personal_score: float
    team_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chemistry_type": self.chemistry_type,
            "score": self.score,
            "personal_score": self.personal_score,
            "team_score": self.team_score,
            "reason": self.reason,
        }


@dataclass(slots=True)
class RatingOutput:
    name: str
    role: str
    team: str | None
    primary_position: str | None
    ratings: dict[str, int]
    percentiles: dict[str, float]
    overall_numeric: int | None
    overall_grade: str | None
    confidence: str
    review_flags: list[str]
    suggested_traits: list[TraitSuggestion]
    assigned_traits: list[TraitSuggestion]
    recommended_personalities: list[PersonalityRecommendation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "team": self.team,
            "primary_position": self.primary_position,
            "ratings": self.ratings,
            "percentiles": self.percentiles,
            "overall_numeric": self.overall_numeric,
            "overall_grade": self.overall_grade,
            "confidence": self.confidence,
            "review_flags": self.review_flags,
            "suggested_traits": [trait.to_dict() for trait in self.suggested_traits],
            "assigned_traits": [trait.to_dict() for trait in self.assigned_traits],
            "recommended_personalities": [item.to_dict() for item in self.recommended_personalities],
        }
