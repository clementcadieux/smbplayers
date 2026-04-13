from __future__ import annotations

from collections import defaultdict
from typing import Mapping

from .models import PersonalityRecommendation, PlayerInput, RatingOutput, TraitSuggestion
from .reference import load_processing_tuning_config, load_trait_catalog, load_trait_limit_config


CHEMISTRY_TYPES, TRAIT_CATALOG = load_trait_catalog()
TRAIT_LIMIT_CONFIG: dict[str, object] = {}

CONFIDENCE_WEIGHTS: dict[str, float] = {}

PERSONALITY_PERSONAL_WEIGHT = 0.70
PERSONALITY_TEAM_WEIGHT = 0.30
DEFAULT_FINAL_TRAIT_LIMIT = 2
DEFAULT_MAX_ELITE_PITCH_TRAITS = 1
TRAIT_CONFLICT_GROUPS: tuple[frozenset[str], ...] = ()


def refresh_runtime_tuning() -> None:
    global TRAIT_LIMIT_CONFIG
    global CONFIDENCE_WEIGHTS
    global PERSONALITY_PERSONAL_WEIGHT
    global PERSONALITY_TEAM_WEIGHT
    global TRAIT_CONFLICT_GROUPS

    TRAIT_LIMIT_CONFIG = load_trait_limit_config()
    tuning = load_processing_tuning_config()

    raw_confidence_weights = tuning.get("confidence_weights", {})
    parsed_confidence_weights: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.4}
    if isinstance(raw_confidence_weights, Mapping):
        for key in ("high", "medium", "low"):
            try:
                parsed_confidence_weights[key] = float(raw_confidence_weights.get(key, parsed_confidence_weights[key]))
            except (TypeError, ValueError):
                continue
    CONFIDENCE_WEIGHTS = parsed_confidence_weights

    raw_personality_weights = tuning.get("personality_weights", {})
    if isinstance(raw_personality_weights, Mapping):
        try:
            PERSONALITY_PERSONAL_WEIGHT = float(raw_personality_weights.get("personal", 0.70))
        except (TypeError, ValueError):
            PERSONALITY_PERSONAL_WEIGHT = 0.70
        try:
            PERSONALITY_TEAM_WEIGHT = float(raw_personality_weights.get("team", 0.30))
        except (TypeError, ValueError):
            PERSONALITY_TEAM_WEIGHT = 0.30
    else:
        PERSONALITY_PERSONAL_WEIGHT = 0.70
        PERSONALITY_TEAM_WEIGHT = 0.30

    raw_trait_conflicts = tuning.get("trait_conflict_groups", [])
    parsed_trait_conflicts: list[frozenset[str]] = []
    if isinstance(raw_trait_conflicts, list):
        for raw_group in raw_trait_conflicts:
            if not isinstance(raw_group, list):
                continue
            group_values = {
                str(item)
                for item in raw_group
                if isinstance(item, str) and str(item).strip()
            }
            if group_values:
                parsed_trait_conflicts.append(frozenset(group_values))
    TRAIT_CONFLICT_GROUPS = tuple(parsed_trait_conflicts)


refresh_runtime_tuning()

ELITE_FASTBALL_TRAIT_NAMES = frozenset({"Elite 4F", "Elite 2F", "Elite CF"})


def configured_chemistry_types() -> list[str]:
    return list(CHEMISTRY_TYPES)


def trait_metadata(trait_name: str) -> dict[str, str | bool | None] | None:
    return TRAIT_CATALOG.get(trait_name)


def trait_chemistry_type(trait_name: str) -> str | None:
    metadata = trait_metadata(trait_name)
    if metadata is None:
        return None
    chemistry_type = metadata.get("chemistry_type")
    return chemistry_type if isinstance(chemistry_type, str) else None


def catalog_trait_polarity(trait_name: str) -> str:
    metadata = trait_metadata(trait_name)
    polarity = metadata.get("polarity") if metadata else None
    return str(polarity or "unknown")


def trait_weight(trait: TraitSuggestion) -> float:
    base_weight = CONFIDENCE_WEIGHTS.get(trait.confidence, 0.4)
    if trait.polarity == "negative":
        return base_weight * 0.95
    return base_weight


def normalize_trait_key(name: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in name).strip("_")


def metadata_lookup(metadata: Mapping[str, object], dotted_key: str) -> object | None:
    current: object = metadata
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def explicit_player_traits(player: PlayerInput) -> list[TraitSuggestion]:
    trait_names: list[str] = []
    for key in ("traits", "existing_traits", "manual_traits"):
        raw_traits = player.metadata.get(key)
        if isinstance(raw_traits, list):
            trait_names.extend(str(item) for item in raw_traits if item)

    seen: set[str] = set()
    explicit_traits: list[TraitSuggestion] = []
    for trait_name in trait_names:
        if trait_name in seen:
            continue
        seen.add(trait_name)
        metadata = trait_metadata(trait_name)
        if metadata is None:
            explicit_traits.append(
                TraitSuggestion(
                    name=trait_name,
                    chemistry_type=None,
                    polarity="unknown",
                    confidence="medium",
                    reason="Provided explicitly in player metadata but not found in the SMB4 reference catalog.",
                )
            )
            continue
        explicit_traits.append(
            TraitSuggestion(
                name=trait_name,
                chemistry_type=trait_chemistry_type(trait_name),
                polarity=str(metadata.get("polarity") or "unknown"),
                confidence="high",
                reason="Provided explicitly in player metadata and counted directly for chemistry fit.",
            )
        )
    return explicit_traits


def hinted_catalog_traits(player: PlayerInput) -> list[TraitSuggestion]:
    metadata = player.metadata
    hinted: dict[str, TraitSuggestion] = {}
    sources = []
    for key in ("trait_hints", "trait_signals", "trait_scores"):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            sources.append(value)

    normalized_catalog = {normalize_trait_key(name): name for name in TRAIT_CATALOG}

    def register(trait_name: str, payload: object) -> None:
        if trait_name not in TRAIT_CATALOG:
            return
        score = None
        confidence = "medium"
        reason = "Suggested from player metadata trait signal."
        if isinstance(payload, (int, float)):
            score = float(payload)
        elif isinstance(payload, bool):
            score = 30.0 if payload else None
        elif isinstance(payload, Mapping):
            raw_score = payload.get("score")
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
            elif payload.get("enabled") is True:
                score = 30.0
            raw_confidence = payload.get("confidence")
            if isinstance(raw_confidence, str):
                confidence = raw_confidence
            raw_reason = payload.get("reason")
            if isinstance(raw_reason, str) and raw_reason:
                reason = raw_reason
        if score is None or score < 10:
            return
        hinted[trait_name] = TraitSuggestion(
            name=trait_name,
            chemistry_type=trait_chemistry_type(trait_name),
            polarity=catalog_trait_polarity(trait_name),
            confidence=confidence,
            reason=reason,
        )

    for source in sources:
        for raw_key, payload in source.items():
            key_name = str(raw_key)
            trait_name = key_name if key_name in TRAIT_CATALOG else normalized_catalog.get(normalize_trait_key(key_name))
            if trait_name:
                register(trait_name, payload)

    for trait_name in TRAIT_CATALOG:
        normalized_key = normalize_trait_key(trait_name)
        for candidate_key in (
            normalized_key,
            f"{normalized_key}_score",
            f"trait_metrics.{normalized_key}",
            f"trait_scores.{normalized_key}",
            f"trait_signals.{normalized_key}",
        ):
            value = metadata_lookup(metadata, candidate_key)
            if value is None:
                continue
            register(trait_name, value)
            break

    return list(hinted.values())


def all_player_traits(output: RatingOutput, player: PlayerInput) -> list[TraitSuggestion]:
    combined: dict[str, TraitSuggestion] = {}
    for trait in explicit_player_traits(player) + output.suggested_traits:
        existing = combined.get(trait.name)
        if existing is None:
            combined[trait.name] = trait
            continue
        rank = {"low": 1, "medium": 2, "high": 3}
        if rank.get(trait.confidence, 1) > rank.get(existing.confidence, 1):
            combined[trait.name] = trait
    return list(combined.values())


def explicit_trait_names(player: PlayerInput) -> set[str]:
    return {trait.name for trait in explicit_player_traits(player)}


def trait_conflicts(existing_names: set[str], candidate_name: str) -> bool:
    for conflict_group in TRAIT_CONFLICT_GROUPS:
        if candidate_name not in conflict_group:
            continue
        if existing_names.intersection(conflict_group):
            return True
    return False


def final_trait_limit(player: PlayerInput, explicit_count: int) -> int:
    raw_limit = metadata_lookup(player.metadata, "final_trait_limit")
    if not isinstance(raw_limit, int):
        raw_limit = metadata_lookup(player.metadata, "trait_limit")
    if not isinstance(raw_limit, int):
        raw_limit = int(TRAIT_LIMIT_CONFIG.get("max_traits_per_player", DEFAULT_FINAL_TRAIT_LIMIT))
    return max(raw_limit, explicit_count)


def elite_pitch_trait_names() -> set[str]:
    configured = TRAIT_LIMIT_CONFIG.get("elite_pitch_traits")
    if isinstance(configured, set) and configured:
        return set(configured)
    if isinstance(configured, list):
        return {str(item) for item in configured if isinstance(item, str) and str(item).strip()}
    return {
        trait_name
        for trait_name in TRAIT_CATALOG
        if isinstance(trait_name, str) and trait_name.startswith("Elite ")
    }


def top_personality_scores(output: RatingOutput) -> dict[str, float]:
    top_two = output.recommended_personalities[:2]
    return {item.chemistry_type: item.score for item in top_two}


def final_trait_priority(
    trait: TraitSuggestion,
    *,
    explicit_names: set[str],
    personality_scores: dict[str, float],
    player_role: str,
    elite_trait_names_set: set[str],
) -> float:
    score = CONFIDENCE_WEIGHTS.get(trait.confidence, 0.4) * 100.0
    if trait.name in explicit_names:
        score += 35.0
    if trait.chemistry_type is not None:
        score += personality_scores.get(trait.chemistry_type, 0.0) * 0.35
    if trait.polarity == "positive":
        score += 8.0
    elif trait.polarity == "negative":
        score += 4.0
    if "Provided explicitly" in trait.reason:
        score += 10.0
    if "metadata" in trait.reason.lower() or "preprocessing" in trait.reason.lower():
        score += 4.0
    if "Extreme usage override:" in trait.reason:
        score += 80.0
    if player_role in {"pitcher", "two_way"} and trait.name in elite_trait_names_set:
        score += 22.0
        if trait.name not in ELITE_FASTBALL_TRAIT_NAMES:
            score += 7.0
    return score


def trim_traits_for_output(output: RatingOutput, player: PlayerInput) -> list[TraitSuggestion]:
    merged_traits = all_player_traits(output, player)
    explicit_names = explicit_trait_names(player)
    limit = final_trait_limit(player, len(explicit_names))
    personality_scores = top_personality_scores(output)
    elite_names = elite_pitch_trait_names()
    max_elite_pitch_traits = int(TRAIT_LIMIT_CONFIG.get("max_elite_pitch_traits", DEFAULT_MAX_ELITE_PITCH_TRAITS))

    ordered_traits = sorted(
        merged_traits,
        key=lambda trait: (
            final_trait_priority(
                trait,
                explicit_names=explicit_names,
                personality_scores=personality_scores,
                player_role=player.role,
                elite_trait_names_set=elite_names,
            ),
            trait.name,
        ),
        reverse=True,
    )

    selected: list[TraitSuggestion] = []
    selected_names: set[str] = set()
    elite_pitch_count = 0
    for trait in ordered_traits:
        if len(selected) >= limit:
            break
        if trait_conflicts(selected_names, trait.name):
            continue
        if trait.name in elite_names:
            if elite_pitch_count >= max_elite_pitch_traits:
                continue
            elite_pitch_count += 1
        selected.append(trait)
        selected_names.add(trait.name)
    return selected


def chemistry_scores_from_traits(traits: list[TraitSuggestion]) -> dict[str, float]:
    scores = {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}
    for trait in traits:
        if trait.chemistry_type is None:
            continue
        scores[trait.chemistry_type] += trait_weight(trait)
    return scores


def normalized_scores(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}
    return {
        chemistry_type: score / total
        for chemistry_type, score in scores.items()
    }


def _normalized_identity_value(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def player_identity_key(player: PlayerInput) -> str:
    if isinstance(player.player_id, str) and player.player_id:
        return f"id:{player.player_id}"
    source_player_id = metadata_lookup(player.metadata, "source_player_id")
    if isinstance(source_player_id, str) and source_player_id:
        return f"id:{source_player_id}"
    roster_season = metadata_lookup(player.metadata, "source_years.current")
    return (
        "composite:"
        f"{_normalized_identity_value(player.name)}|"
        f"{_normalized_identity_value(player.team)}|"
        f"{_normalized_identity_value(player.primary_position)}|"
        f"{_normalized_identity_value(player.role)}|"
        f"{roster_season if roster_season is not None else ''}"
    )


def output_identity_key(output: RatingOutput) -> str:
    if isinstance(output.player_id, str) and output.player_id:
        return f"id:{output.player_id}"
    source_player_id = metadata_lookup(output.metadata, "source_player_id")
    if isinstance(source_player_id, str) and source_player_id:
        return f"id:{source_player_id}"
    roster_season = metadata_lookup(output.metadata, "source_years.current")
    return (
        "composite:"
        f"{_normalized_identity_value(output.name)}|"
        f"{_normalized_identity_value(output.team)}|"
        f"{_normalized_identity_value(output.primary_position)}|"
        f"{_normalized_identity_value(output.role)}|"
        f"{roster_season if roster_season is not None else ''}"
    )


def team_trait_scores(outputs: list[RatingOutput], players_by_identity: dict[str, PlayerInput]) -> dict[str, dict[str, float]]:
    totals_by_team: dict[str, dict[str, float]] = defaultdict(lambda: {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()})
    for output in outputs:
        if not output.team:
            continue
        player = players_by_identity.get(output_identity_key(output))
        if player is None:
            continue
        player_scores = chemistry_scores_from_traits(all_player_traits(output, player))
        for chemistry_type, score in player_scores.items():
            totals_by_team[output.team][chemistry_type] += score
    return dict(totals_by_team)


def personality_reason(
    chemistry_type: str,
    personal_share: float,
    team_share: float,
    player_traits: list[TraitSuggestion],
    team_scores: dict[str, float],
) -> str:
    personal_traits = [trait.name for trait in player_traits if trait.chemistry_type == chemistry_type]
    if personal_traits:
        return (
            f"Personal traits lean {chemistry_type} through {', '.join(personal_traits[:3])}; "
            f"team context adds a secondary {chemistry_type} push."
        )
    team_peak = max(team_scores, key=lambda key: team_scores[key]) if team_scores else chemistry_type
    if team_share > 0 and team_peak == chemistry_type:
        return f"Personal evidence is light, but the team trait mix most strongly supports {chemistry_type}."
    return f"Limited direct personal-trait evidence; {chemistry_type} remains a secondary fit from the combined roster context."


def recommend_personalities_for_output(
    output: RatingOutput,
    player: PlayerInput,
    team_scores: dict[str, float],
) -> list[PersonalityRecommendation]:
    personal_traits = all_player_traits(output, player)
    personal_raw = chemistry_scores_from_traits(personal_traits)
    team_minus_self = dict(team_scores)
    for chemistry_type, score in personal_raw.items():
        team_minus_self[chemistry_type] = max(0.0, team_minus_self.get(chemistry_type, 0.0) - score)

    personal_share = normalized_scores(personal_raw)
    team_share = normalized_scores(team_minus_self)

    recommendations: list[PersonalityRecommendation] = []
    for chemistry_type in configured_chemistry_types():
        blended_score = (
            PERSONALITY_PERSONAL_WEIGHT * personal_share[chemistry_type]
            + PERSONALITY_TEAM_WEIGHT * team_share[chemistry_type]
        ) * 100.0
        recommendations.append(
            PersonalityRecommendation(
                chemistry_type=chemistry_type,
                score=round(blended_score, 2),
                personal_score=round(personal_share[chemistry_type] * 100.0, 2),
                team_score=round(team_share[chemistry_type] * 100.0, 2),
                reason=personality_reason(
                    chemistry_type=chemistry_type,
                    personal_share=personal_share[chemistry_type],
                    team_share=team_share[chemistry_type],
                    player_traits=personal_traits,
                    team_scores=team_minus_self,
                ),
            )
        )

    return sorted(recommendations, key=lambda item: (item.score, item.personal_score, item.team_score), reverse=True)
