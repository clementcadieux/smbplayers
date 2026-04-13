from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import RatingOutput


def _markdown_escape(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Unknown"
    return value.replace("|", "\\|").strip()


def _trait_lines(player: RatingOutput) -> list[str]:
    if not player.assigned_traits:
        return ["- None"]
    return [
        f"- **{trait.name}** ({trait.chemistry_type or 'Unaligned'}, {trait.confidence})"
        for trait in player.assigned_traits
    ]


def _personality_lines(player: RatingOutput) -> list[str]:
    if not player.recommended_personalities:
        return ["- None"]
    return [
        f"- {item.chemistry_type} ({item.score:.2f}%)"
        for item in player.recommended_personalities[:3]
    ]


def _review_flag_lines(player: RatingOutput) -> list[str]:
    if not player.review_flags:
        return ["- None"]
    return [f"- {flag}" for flag in player.review_flags]


def generate_player_report(player: RatingOutput) -> str:
    title = f"# {_markdown_escape(player.name)} - {_markdown_escape(player.primary_position)} | {_markdown_escape(player.team)}"
    overall_grade = player.overall_grade or "N/A"
    overall_numeric = player.overall_numeric if player.overall_numeric is not None else "N/A"

    rating_rows = ["| Category | Rating | Percentile |", "|---|---:|---:|"]
    categories = sorted(set(player.ratings) | set(player.percentiles))
    for category in categories:
        rating_value = player.ratings.get(category, "-")
        percentile_value = player.percentiles.get(category)
        percentile_text = "-" if percentile_value is None else f"{percentile_value:.2f}"
        rating_rows.append(f"| {category} | {rating_value} | {percentile_text} |")

    sections = [
        title,
        f"**Overall:** {overall_grade} ({overall_numeric}) | Confidence: {_markdown_escape(player.confidence)}",
        "",
        "## Ratings",
        *rating_rows,
        "",
        "## Assigned Traits",
        *_trait_lines(player),
        "",
        "## Recommended Personalities",
        *_personality_lines(player),
        "",
        "## Review Flags",
        *_review_flag_lines(player),
    ]
    return "\n".join(sections)


def generate_team_report(team: str, players: list[RatingOutput]) -> str:
    sorted_players = sorted(players, key=lambda player: (player.overall_numeric or 0, player.name), reverse=True)
    chunks = [f"# Team {_markdown_escape(team)} Report", ""]
    for index, player in enumerate(sorted_players):
        if index > 0:
            chunks.append("\n---\n")
        chunks.append(generate_player_report(player))
    return "\n".join(chunks)


def generate_output(ratings: list[RatingOutput], output_path: Path) -> None:
    output_path.mkdir(parents=True, exist_ok=True)

    players_by_team: dict[str, list[RatingOutput]] = defaultdict(list)
    for player in ratings:
        team = player.team or "UNASSIGNED"
        players_by_team[team].append(player)

    for team, players in sorted(players_by_team.items()):
        report = generate_team_report(team, players)
        report_path = output_path / f"{team}.md"
        report_path.write_text(report + "\n", encoding="utf-8")
