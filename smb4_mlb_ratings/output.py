from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .models import RatingOutput


TEAM_DIVISIONS: dict[str, tuple[str, str]] = {
    "BAL": ("AL", "East"),
    "BOS": ("AL", "East"),
    "NYY": ("AL", "East"),
    "TB": ("AL", "East"),
    "TOR": ("AL", "East"),
    "CWS": ("AL", "Central"),
    "CLE": ("AL", "Central"),
    "DET": ("AL", "Central"),
    "KC": ("AL", "Central"),
    "MIN": ("AL", "Central"),
    "HOU": ("AL", "West"),
    "LAA": ("AL", "West"),
    "ATH": ("AL", "West"),
    "SEA": ("AL", "West"),
    "TEX": ("AL", "West"),
    "ATL": ("NL", "East"),
    "MIA": ("NL", "East"),
    "NYM": ("NL", "East"),
    "PHI": ("NL", "East"),
    "WSH": ("NL", "East"),
    "CHC": ("NL", "Central"),
    "CIN": ("NL", "Central"),
    "MIL": ("NL", "Central"),
    "PIT": ("NL", "Central"),
    "STL": ("NL", "Central"),
    "ARI": ("NL", "West"),
    "COL": ("NL", "West"),
    "LAD": ("NL", "West"),
    "SD": ("NL", "West"),
    "SF": ("NL", "West"),
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_structured_output(ratings: list[RatingOutput], output_dir: Path) -> None:
    grouped_ratings: dict[str, list[RatingOutput]] = defaultdict(list)
    missing_teams: list[str] = []
    unknown_teams: list[str] = []

    for rating in ratings:
        if rating.team is None:
            missing_teams.append(rating.name)
            continue

        team = rating.team.upper()
        if team not in TEAM_DIVISIONS:
            unknown_teams.append(f"{rating.name} ({team})")
            continue
        grouped_ratings[team].append(rating)

    if missing_teams or unknown_teams:
        problems: list[str] = []
        if missing_teams:
            problems.append("missing team for: " + ", ".join(sorted(missing_teams)))
        if unknown_teams:
            problems.append("unknown team mapping for: " + ", ".join(sorted(unknown_teams)))
        raise ValueError("Structured output requires valid MLB team abbreviations; " + "; ".join(problems))

    index_payload: dict[str, dict[str, list[dict[str, object]]]] = {
        "AL": {"East": [], "Central": [], "West": []},
        "NL": {"East": [], "Central": [], "West": []},
    }

    for team in sorted(grouped_ratings):
        league, division = TEAM_DIVISIONS[team]
        relative_path = Path(league) / division / f"{team}.json"
        team_ratings = sorted(grouped_ratings[team], key=lambda rating: rating.name)
        _write_json(output_dir / relative_path, [rating.to_dict() for rating in team_ratings])

        index_payload[league][division].append(
            {
                "team": team,
                "path": relative_path.as_posix(),
                "player_count": len(team_ratings),
            }
        )

    _write_json(output_dir / "index.json", index_payload)