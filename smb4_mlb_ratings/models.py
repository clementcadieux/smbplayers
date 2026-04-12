from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SeasonValue = float | int | dict[str, float | int] | None


@dataclass(slots=True)
class PlayerInput:
    name: str
    role: str
    active: bool = True
    team: str | None = None
    age: int | None = None
    primary_position: str | None = None
    secondary_position: str | None = None
    bats: str | None = None
    throws: str | None = None
    projected_pa: float | None = None
    projected_ip: float | None = None
    days_on_roster: dict[str, float] = field(default_factory=dict)
    pitch_mix: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, SeasonValue] = field(default_factory=dict)
    samples: dict[str, SeasonValue] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerInput":
        return cls(
            name=data["name"],
            role=data["role"],
            active=bool(data.get("active", True)),
            team=data.get("team"),
            age=data.get("age"),
            primary_position=data.get("primary_position"),
            secondary_position=data.get("secondary_position"),
            bats=data.get("bats"),
            throws=data.get("throws"),
            projected_pa=data.get("projected_pa"),
            projected_ip=data.get("projected_ip"),
            days_on_roster={str(key): float(value) for key, value in data.get("days_on_roster", {}).items()},
            pitch_mix={str(key): float(value) for key, value in data.get("pitch_mix", {}).items()},
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraitSuggestion":
        return cls(
            name=data["name"],
            chemistry_type=data.get("chemistry_type"),
            polarity=data.get("polarity", "unknown"),
            confidence=data.get("confidence", "medium"),
            reason=data.get("reason", ""),
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityRecommendation":
        return cls(
            chemistry_type=data["chemistry_type"],
            score=float(data.get("score", 0.0)),
            personal_score=float(data.get("personal_score", 0.0)),
            team_score=float(data.get("team_score", 0.0)),
            reason=data.get("reason", ""),
        )


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
    secondary_position: str | None = None
    age: int | None = None
    projected_pa: float | None = None
    projected_ip: float | None = None
    recommended_pitches: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "team": self.team,
            "primary_position": self.primary_position,
            "secondary_position": self.secondary_position,
            "age": self.age,
            "projected_pa": self.projected_pa,
            "projected_ip": self.projected_ip,
            "recommended_pitches": self.recommended_pitches,
            "ratings": self.ratings,
            "percentiles": self.percentiles,
            "overall_numeric": self.overall_numeric,
            "overall_grade": self.overall_grade,
            "confidence": self.confidence,
            "review_flags": self.review_flags,
            "suggested_traits": [trait.to_dict() for trait in self.suggested_traits],
            "assigned_traits": [trait.to_dict() for trait in self.assigned_traits],
            "recommended_personalities": [item.to_dict() for item in self.recommended_personalities],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RatingOutput":
        return cls(
            name=data["name"],
            role=data["role"],
            team=data.get("team"),
            primary_position=data.get("primary_position"),
            ratings={str(key): int(value) for key, value in data.get("ratings", {}).items()},
            percentiles={str(key): float(value) for key, value in data.get("percentiles", {}).items()},
            overall_numeric=data.get("overall_numeric"),
            overall_grade=data.get("overall_grade"),
            confidence=data.get("confidence", "medium"),
            review_flags=[str(flag) for flag in data.get("review_flags", [])],
            suggested_traits=[TraitSuggestion.from_dict(item) for item in data.get("suggested_traits", [])],
            assigned_traits=[TraitSuggestion.from_dict(item) for item in data.get("assigned_traits", [])],
            recommended_personalities=[PersonalityRecommendation.from_dict(item) for item in data.get("recommended_personalities", [])],
            secondary_position=data.get("secondary_position"),
            age=data.get("age"),
            projected_pa=float(data["projected_pa"]) if data.get("projected_pa") is not None else None,
            projected_ip=float(data["projected_ip"]) if data.get("projected_ip") is not None else None,
            recommended_pitches=[str(item) for item in data.get("recommended_pitches", [])],
            metadata=data.get("metadata", {}),
        )
