# SMB4 MLB Ratings Framework

This workspace now includes a small Python tool that converts MLB-style player metrics into SMB4-style ratings using the framework defined in [smb4_player_reference.json](smb4_player_reference.json).

## What It Does

- Accepts player input records in JSON
- Supports weighted multi-season metrics using `current`, `previous`, and `two_years_ago`
- Weights multi-season metrics by both recency and season-specific volume when matching sample data is present
- Stabilizes noisy samples with regression toward league averages
- Blends underlying metrics with surface stats on a sample-based ramp, keeping underlying signals at 50-100% of each affected rating
- Treats raw-tool ratings more aggressively than skill ratings, allowing smaller samples and age-sensitive trend effects for `power`, `speed`, `arm`, `velocity`, and `junk`
- Suggests traits aggressively from component outliers, including negative traits that preserve weaknesses hidden by a blended rating
- Recommends a ranked list of SMB4 personality types per player using a personal-traits-first and team-traits-second blend
- Produces both a broad suggestion pool and a trimmed SMB4-realistic final trait assignment set
- Produces SMB4-style numeric ratings, overall grades, and manual-review flags

Personality ranking considers the full SMB4 trait catalog from [smb4_player_reference.json](smb4_player_reference.json). Suggested traits and any explicit player traits provided in `metadata.traits`, `metadata.existing_traits`, or `metadata.manual_traits` all contribute to chemistry ranking.

Trait inference now supports two full-catalog pathways:
- automatic metadata family rules for splits, pitch-type strengths, zone strengths, leverage, durability, volatility, running-game control, and two-way usage
- direct per-trait signals through `metadata.trait_hints`, `metadata.trait_signals`, `metadata.trait_scores`, or normalized per-trait keys in metadata

This means every SMB4 trait can be suggested automatically when the relevant source signal is present, even if that signal comes from custom preprocessing rather than the core metric set.

Final trait assignment uses priority and conflict rules so the engine can keep a broad discovery list in `suggested_traits` while also emitting a smaller `assigned_traits` list intended to be closer to an actual SMB4 roster build. The default final trait limit is 3, and can be overridden per player with `metadata.final_trait_limit` or `metadata.trait_limit`. If you call `rate_players(..., trim_final_traits=False)`, `assigned_traits` will return the full combined trait set instead.

## Files

- [smb4_player_reference.json](smb4_player_reference.json): SMB4 reference schema and trait catalog
- [smb4_mlb_ratings/engine.py](smb4_mlb_ratings/engine.py): rating engine and framework rules
- [smb4_mlb_ratings/models.py](smb4_mlb_ratings/models.py): input and output models
- [smb4_mlb_ratings/cli.py](smb4_mlb_ratings/cli.py): command-line entry point
- [smb4_mlb_ratings/ingest/savant.py](smb4_mlb_ratings/ingest/savant.py): Baseball Savant CSV ingestion and normalization
- [smb4_mlb_ratings/ingest/baseball_reference.py](smb4_mlb_ratings/ingest/baseball_reference.py): Baseball Reference CSV ingestion for result-based stats

## Input Format

The CLI reads either:

- a JSON array of player objects, or
- a JSON object with a top-level `players` array

Each player object can contain scalar metrics or season-window metrics.
If a metric uses season-window values, the engine will combine them using the recency weights and the matching sample volume for that rating context. For example, hitter batting metrics are volume-weighted by `weighted_pa`, pitcher command metrics by `weighted_bf`, and defensive metrics by `defensive_innings`.
For raw physical-tool ratings, the engine also reduces the dominance of old large samples and applies an age-sensitive trend adjustment so younger players can rise faster and older players can decline faster when current-year tool readings move.

Example:

```json
{
  "players": [
    {
      "name": "Example Hitter",
      "role": "hitter",
      "age": 23,
      "team": "Example Team",
      "primary_position": "CF",
      "bats": "R",
      "throws": "R",
      "metrics": {
        "iso": {"current": 0.210, "previous": 0.195, "two_years_ago": 0.180},
        "hr_per_pa": {"current": 0.051, "previous": 0.047, "two_years_ago": 0.042},
        "barrel_rate": 0.112,
        "slugging": 0.505,
        "avg_exit_velocity": 91.4,
        "strikeout_rate": 0.221,
        "contact_rate": 0.768,
        "batting_average": 0.281,
        "adjusted_obp": 0.352,
        "two_strike_contact_rate": 0.642,
        "sprint_speed": 28.7,
        "baserunning_value": 3.8,
        "sb_attempt_rate": 0.076,
        "sb_success_rate": 0.821,
        "triple_double_rate": 0.061,
        "oaa": 7,
        "drs": 5,
        "uzr": 3.9,
        "fielding_pct_proxy": 0.990,
        "position_difficulty": 0.82,
        "arm_strength": 88.6,
        "outfield_arm_runs": 3.1,
        "arm_position_baseline": 0.70
      },
      "samples": {
        "weighted_pa": {"current": 610, "previous": 590, "two_years_ago": 540},
        "baserunning_opportunities": 145,
        "defensive_innings": 1020
      }
    }
  ]
}
```

## Supported Metric Keys

Hitters:

- `iso`
- `hr_per_pa`
- `barrel_rate`
- `slugging`
- `avg_exit_velocity`
- `strikeout_rate`
- `contact_rate`
- `batting_average`
- `adjusted_obp`
- `two_strike_contact_rate`
- `sprint_speed`
- `baserunning_value`
- `sb_attempt_rate`
- `sb_success_rate`
- `triple_double_rate`
- `oaa`
- `drs`
- `uzr`
- `fielding_pct_proxy`
- `position_difficulty`
- `arm_strength`
- `catcher_throw_value`
- `outfield_arm_runs`
- `arm_position_baseline`

Pitchers:

- `avg_fastball_velocity`
- `peak_fastball_velocity`
- `fastball_usage`
- `swinging_strike_rate`
- `chase_rate`
- `movement_quality`
- `stuff_metric`
- `arsenal_diversity`
- `weak_contact_rate`
- `walk_rate`
- `strike_pct`
- `zone_pct`
- `first_pitch_strike_pct`
- `command_error_rate`

Samples:

- `weighted_pa`
- `weighted_bf`
- `baserunning_opportunities`
- `defensive_innings`
- `tracked_fastballs`
- `tracked_pitches`

## Running The Tool

```powershell
python -m smb4_mlb_ratings.cli players.json ratings_output.json
```

The legacy two-argument command still rates a prepared normalized JSON file.

New subcommands are also available:

```powershell
python -m smb4_mlb_ratings.cli rate players.json ratings_output.json
python -m smb4_mlb_ratings.cli ingest savant_manifest.json normalized_players.json
python -m smb4_mlb_ratings.cli ingest-rate savant_manifest.json ratings_output.json --normalized-output normalized_players.json
```

The `ingest` manifest can now target `baseball_savant`, `baseball_reference`, or `mixed`.

## Baseball Savant Ingestion

The new ingestion framework converts Baseball Savant or Statcast CSV exports into the same `PlayerInput` JSON shape the engine already understands.

### Supported Source Files

Each season entry can provide any combination of:

- `hitters`: batting and quality-of-contact summaries
- `pitchers`: pitching and arsenal summaries
- `fielding`: defensive leaderboards such as OAA, DRS, UZR, arm metrics, and innings
- `running`: sprint speed and baserunning tables
- `roster`: optional identity enrichment with age, handedness, team, and positions

The framework merges files by MLBAM player id first, then by player name.

### Manifest Format

Create a manifest JSON file that points at one or more season windows:

```json
{
  "source": "baseball_savant",
  "seasons": {
    "current": {
      "year": 2025,
      "files": {
        "roster": "exports/roster_2025.csv",
        "hitters": "exports/hitters_2025.csv",
        "pitchers": "exports/pitchers_2025.csv",
        "fielding": "exports/fielding_2025.csv",
        "running": "exports/running_2025.csv"
      }
    },
    "previous": {
      "year": 2024,
      "files": {
        "hitters": "exports/hitters_2024.csv",
        "pitchers": "exports/pitchers_2024.csv"
      }
    },
    "two_years_ago": {
      "year": 2023,
      "files": {
        "hitters": "exports/hitters_2023.csv",
        "pitchers": "exports/pitchers_2023.csv"
      }
    }
  }
}
```

Relative paths are resolved from the manifest file location.

### Output Behavior

- `ingest` writes a JSON object with a top-level `players` array
- hitter and pitcher rows are normalized into the engine's existing metric keys and sample keys
- when a metric is estimated rather than read directly, the metric name is recorded in `metadata.ingest.estimated_metrics`
- when optional files like `fielding` or `running` are missing, the omission is recorded in `metadata.ingest.missing_files`

### Current Mapping Notes

The first implementation is CSV-first and local-file-first. It supports both hitters and pitchers and maps the existing engine contract directly:

- hitters: power, contact, speed, fielding, and arm inputs
- pitchers: velocity, junk, and accuracy inputs
- season windows: `current`, `previous`, and `two_years_ago`
- samples: `weighted_pa`, `weighted_bf`, `baserunning_opportunities`, `defensive_innings`, `tracked_fastballs`, and `tracked_pitches`

Some source metrics are estimated when Savant does not provide them directly. Those estimates are intentionally surfaced in metadata so you can review them before trusting the final roster output.

## Baseball Reference Ingestion

The ingestion framework also supports Baseball Reference CSV exports for actual result-based performance data.

### Best Fit For This Source

Baseball Reference is the better source for actual outcomes such as batting line, walk and strikeout rates, stolen-base results, innings, and fielding results. It is not the right source for tool-driven inputs like exit velocity, sprint speed, arm strength, or pitch movement unless those are provided from another source.

### Supported Source Files

Each season entry can provide any combination of:

- `hitters`: batting result tables
- `pitchers`: pitching result tables
- `fielding`: fielding result tables
- `roster`: optional identity enrichment with age, handedness, team, and positions

### Manifest Format

```json
{
  "source": "baseball_reference",
  "seasons": {
    "current": {
      "year": 2025,
      "files": {
        "roster": "exports/br_roster_2025.csv",
        "hitters": "exports/br_hitters_2025.csv",
        "pitchers": "exports/br_pitchers_2025.csv",
        "fielding": "exports/br_fielding_2025.csv"
      }
    },
    "previous": {
      "year": 2024,
      "files": {
        "hitters": "exports/br_hitters_2024.csv",
        "pitchers": "exports/br_pitchers_2024.csv"
      }
    }
  }
}
```

### Current Mapping Notes

The first Baseball Reference implementation focuses on actual-result inputs:

- hitters: `iso`, `hr_per_pa`, `slugging`, `strikeout_rate`, `contact_rate`, `batting_average`, `adjusted_obp`, baserunning result metrics
- pitchers: `stuff_metric`, `weak_contact_rate`, `walk_rate`, `strike_pct`, `command_error_rate`
- fielding: `drs`, `uzr` when present, fielding percentage proxy, position difficulty, and arm-position baseline

If a Baseball Reference file does not provide a direct tool metric, the adapter either omits that metric or derives a conservative proxy and records that fact in `metadata.ingest.estimated_metrics`.

## Mixed-Source Ingestion

The mixed-source path merges Baseball Reference outcome data with Savant tool data for the same players.

### Merge Strategy

- Baseball Reference is preferred for result-based metrics such as batting line outcomes, walk rates, and baserunning results
- Baseball Savant is preferred for tool-oriented metrics such as barrel rate, exit velocity, sprint speed, and pitch-shape or velocity inputs
- If the preferred source is missing a season value, the other source fills the gap

### Mixed Manifest Format

```json
{
  "source": "mixed",
  "seasons": {
    "current": {
      "year": 2025,
      "sources": {
        "baseball_reference": {
          "files": {
            "hitters": "exports/br_hitters_2025.csv",
            "pitchers": "exports/br_pitchers_2025.csv",
            "fielding": "exports/br_fielding_2025.csv"
          }
        },
        "baseball_savant": {
          "files": {
            "hitters": "exports/savant_hitters_2025.csv",
            "pitchers": "exports/savant_pitchers_2025.csv",
            "fielding": "exports/savant_fielding_2025.csv",
            "running": "exports/savant_running_2025.csv"
          }
        }
      }
    }
  }
}
```

Merged outputs use `metadata.source = "mixed"` and preserve source-specific ingest audit details under `metadata.source_details`.

## Output Shape

Each output record includes:

- player identity fields
- generated ratings
- component percentiles
- numeric overall
- letter overall grade
- confidence level
- manual review flags
- suggested traits with chemistry type, polarity, confidence, and rationale
- assigned traits with SMB4-style trimming and conflict resolution
- recommended personality rankings with blended, personal, and team scores

## Current Scope

This implementation now includes local CSV ingestion frameworks for Baseball Savant and Baseball Reference exports in addition to the rating engine itself. It does not yet download live MLB data automatically from remote APIs.
