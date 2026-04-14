"""
Integer lookup tables for the SMB4 SQLite save format.

Ported from xblbaseball/xbl-roster-importer src/shared/models/mappings.ts.
SMB4 .sav files are DEFLATE-compressed SQLite databases.  The constants here
map human-readable attribute values to the integer/key values stored in:

    t_baseball_players          – power/contact/speed/fielding/arm/velocity/junk/accuracy columns
    t_baseball_player_options   – key/value option rows
    t_baseball_player_traits    – (trait, subType) integer pairs
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Position mappings  (t_baseball_player_options, optionKey PRIMARY_POSITION / SECONDARY_POSITION)
# ---------------------------------------------------------------------------

POSITION_TO_INT: dict[str, int] = {
    "":       0,   # None
    "P":      1,   # Pitcher
    "C":      2,   # Catcher
    "1B":     3,
    "2B":     4,
    "3B":     5,
    "SS":     6,
    "LF":     7,
    "CF":     8,
    "RF":     9,
    "IF":     10,
    "OF":     11,
    "1B/OF":  12,
    "IF/OF":  13,
}

INT_TO_POSITION: dict[int, str] = {v: k for k, v in POSITION_TO_INT.items() if k}

# ---------------------------------------------------------------------------
# Pitcher role (t_baseball_player_options, optionKey PITCH_POSITION)
# ---------------------------------------------------------------------------

PITCH_ROLE_TO_INT: dict[str, int] = {
    "SP":    1,
    "SP/RP": 2,
    "RP":    3,
    "CP":    4,
}

INT_TO_PITCH_ROLE: dict[int, str] = {v: k for k, v in PITCH_ROLE_TO_INT.items()}

PITCHER_ROLES: frozenset[str] = frozenset(PITCH_ROLE_TO_INT)

# ---------------------------------------------------------------------------
# Batting / throwing hand
# ---------------------------------------------------------------------------

BATTING_HAND_TO_INT: dict[str, int] = {"L": 0, "R": 1, "S": 2}
INT_TO_BATTING_HAND: dict[int, str] = {v: k for k, v in BATTING_HAND_TO_INT.items()}

THROWING_HAND_TO_INT: dict[str, int] = {"L": 0, "R": 1}
INT_TO_THROWING_HAND: dict[int, str] = {v: k for k, v in THROWING_HAND_TO_INT.items()}

# ---------------------------------------------------------------------------
# Chemistry (personality type)
# ---------------------------------------------------------------------------

CHEMISTRY_TO_INT: dict[str, int] = {
    "Competitive": 0,
    "Spirited":    1,
    "Disciplined": 2,
    "Scholarly":   3,
    "Crafty":      4,
}

INT_TO_CHEMISTRY: dict[int, str] = {v: k for k, v in CHEMISTRY_TO_INT.items()}

# Aliases used in encoder_plan attribute values
_CHEMISTRY_ALIASES: dict[str, str] = {
    "competitive": "Competitive",
    "spirited":    "Spirited",
    "disciplined": "Disciplined",
    "scholarly":   "Scholarly",
    "crafty":      "Crafty",
}

# ---------------------------------------------------------------------------
# Arm angle
# ---------------------------------------------------------------------------

ARM_ANGLE_TO_INT: dict[str, int] = {"Sub": 0, "Low": 1, "Mid": 2, "High": 3}
INT_TO_ARM_ANGLE: dict[int, str] = {v: k for k, v in ARM_ANGLE_TO_INT.items()}

DEFAULT_ARM_ANGLE = 2  # Mid

# ---------------------------------------------------------------------------
# Option keys  (t_baseball_player_options.optionKey)
# ---------------------------------------------------------------------------

OPTION_KEYS: dict[str, int] = {
    "THROWING_HAND":      4,
    "BATTING_HAND":       5,
    "ARM_ANGLE":          49,
    "PRIMARY_POSITION":   54,
    "SECONDARY_POSITION": 55,
    "PITCH_POSITION":     57,
    "FOUR_SEAM":          58,
    "TWO_SEAM":           59,
    "SCREWBALL":          60,
    "CHANGEUP":           61,
    "FORK":               62,
    "CURVEBALL":          63,
    "SLIDER":             64,
    "CUTTER":             65,
    "CHEMISTRY":          107,
}

# optionType value for each key  (0 = general, 5 = positional/pitch/chemistry/arm)
OPTION_TYPES: dict[int, int] = {
    4:   0,   # THROWING_HAND
    5:   0,   # BATTING_HAND
    49:  5,   # ARM_ANGLE
    54:  5,   # PRIMARY_POSITION
    55:  5,   # SECONDARY_POSITION
    57:  5,   # PITCH_POSITION
    58:  5,   # FOUR_SEAM
    59:  5,   # TWO_SEAM
    60:  5,   # SCREWBALL
    61:  5,   # CHANGEUP
    62:  5,   # FORK
    63:  5,   # CURVEBALL
    64:  5,   # SLIDER
    65:  5,   # CUTTER
    107: 5,   # CHEMISTRY
}

# ---------------------------------------------------------------------------
# Arsenal / pitch-type name → option key
# Multiple common name variants are included to handle both display strings
# from encoder_plan.json ("4-Seam Fastball") and SMB4 short names ("4F").
# ---------------------------------------------------------------------------

PITCH_NAME_TO_OPTION_KEY: dict[str, int] = {
    # Four-seam fastball
    "4-seam fastball":  OPTION_KEYS["FOUR_SEAM"],
    "four-seam":        OPTION_KEYS["FOUR_SEAM"],
    "4-seam":           OPTION_KEYS["FOUR_SEAM"],
    "fourseam":         OPTION_KEYS["FOUR_SEAM"],
    "4f":               OPTION_KEYS["FOUR_SEAM"],
    # Two-seam fastball
    "2-seam fastball":  OPTION_KEYS["TWO_SEAM"],
    "two-seam":         OPTION_KEYS["TWO_SEAM"],
    "2-seam":           OPTION_KEYS["TWO_SEAM"],
    "twoseam":          OPTION_KEYS["TWO_SEAM"],
    "2f":               OPTION_KEYS["TWO_SEAM"],
    "sinker":           OPTION_KEYS["TWO_SEAM"],
    # Screwball
    "screwball":        OPTION_KEYS["SCREWBALL"],
    "sb":               OPTION_KEYS["SCREWBALL"],
    "screw":            OPTION_KEYS["SCREWBALL"],
    # Changeup
    "changeup":         OPTION_KEYS["CHANGEUP"],
    "change-up":        OPTION_KEYS["CHANGEUP"],
    "ch":               OPTION_KEYS["CHANGEUP"],
    "change":           OPTION_KEYS["CHANGEUP"],
    "splitter":         OPTION_KEYS["CHANGEUP"],
    "split-finger":     OPTION_KEYS["CHANGEUP"],
    # Fork
    "forkball":         OPTION_KEYS["FORK"],
    "fork":             OPTION_KEYS["FORK"],
    "fk":               OPTION_KEYS["FORK"],
    # Curveball
    "curveball":        OPTION_KEYS["CURVEBALL"],
    "curve":            OPTION_KEYS["CURVEBALL"],
    "cb":               OPTION_KEYS["CURVEBALL"],
    "knuckle curve":    OPTION_KEYS["CURVEBALL"],
    "knucklecurve":     OPTION_KEYS["CURVEBALL"],
    "kc":               OPTION_KEYS["CURVEBALL"],
    # Slider
    "slider":           OPTION_KEYS["SLIDER"],
    "sl":               OPTION_KEYS["SLIDER"],
    "sweeper":          OPTION_KEYS["SLIDER"],
    # Cutter
    "cut fastball":     OPTION_KEYS["CUTTER"],
    "cutter":           OPTION_KEYS["CUTTER"],
    "cf":               OPTION_KEYS["CUTTER"],
    "ct":               OPTION_KEYS["CUTTER"],
}

# ---------------------------------------------------------------------------
# Trait map  (traitId-subtypeId → display name)
# Ported verbatim from mappings.ts TRAIT_MAP.
# ---------------------------------------------------------------------------

_TRAIT_MAP_RAW: dict[str, str] = {
    "0-0":   "POW vs RHP (+)",
    "0-1":   "POW vs LHP (+)",
    "1-0":   "CON vs RHP (+)",
    "1-1":   "CON vs LHP (+)",
    "2-6":   "RBI Hero (+)",
    "2-7":   "RBI Zero (-)",
    "3-2":   "High Pitch (+)",
    "3-3":   "Low Pitch (+)",
    "3-4":   "Inside Pitch (+)",
    "3-5":   "Outside Pitch (+)",
    "4-6":   "Tough Out (+)",
    "4-7":   "Whiffer (-)",
    "5-12":  "Specialist (+)",
    "5-13":  "Reverse Splits (+)",
    "6-6":   "Composed (+)",
    "6-7":   "BB Prone (-)",
    "7-6":   "K Collector (+)",
    "7-7":   "K Neglector (-)",
    "8-6":   "Stealer (+)",
    "8-7":   "Bad Jumps (-)",
    "9-6":   "Utility (+)",
    "10-8":  "Fastball Hitter (+)",
    "10-9":  "Off-Speed Hitter (+)",
    "11-6":  "Bad Ball Hitter (+)",
    "12-10": "Big Hack (+)",
    "12-11": "Little Hack (+)",
    "13-6":  "Rally Starter (+)",
    "14-6":  "First Pitch Slayer (+)",
    "14-7":  "First Pitch Prayer (-)",
    "15-6":  "Pinch Perfect (+)",
    "16-6":  "Ace Exterminator (+)",
    "17-6":  "Mind Gamer (+)",
    "17-7":  "Easy Target (-)",
    "18-6":  "Pick Officer (+)",
    "18-7":  "Easy Jumps (-)",
    "19-6":  "Gets Ahead (+)",
    "19-7":  "Falls Behind (-)",
    "20-6":  "Rally Stopper (+)",
    "20-7":  "Surrounded (-)",
    "21-7":  "Crossed Up (-)",
    "22-14": "Elite 4F (+)",
    "22-15": "Elite 2F (+)",
    "22-16": "Elite CF (+)",
    "22-17": "Elite CB (+)",
    "22-18": "Elite SL (+)",
    "22-19": "Elite CH (+)",
    "22-20": "Elite SB (+)",
    "22-21": "Elite FK (+)",
    "23-6":  "Workhorse (+)",
    "24-22": "Two Way (OF) (+)",
    "24-23": "Two Way (IF) (+)",
    "24-24": "Two Way (C) (+)",
    "25-6":  "Metal Head (+)",
    "26-6":  "Sprinter (+)",
    "26-7":  "Slow Poke (-)",
    "27-6":  "Base Rounder (+)",
    "27-7":  "Base Jogger (-)",
    "28-6":  "Distractor (+)",
    "29-6":  "Magic Hands (+)",
    "29-7":  "Butter Fingers (-)",
    "30-7":  "Wild Thrower (-)",
    "31-7":  "Wild Thing (-)",
    "32-6":  "Clutch (+)",
    "32-7":  "Choker (-)",
    "33-25": "Consistent (+)",
    "33-26": "Volatile (+)",
    "34-6":  "Durable (+)",
    "34-7":  "Injury Prone (-)",
    "35-6":  "Stimulated (+)",
    "36-6":  "Cannon Arm (+)",
    "36-7":  "Noodle Arm (-)",
    "37-6":  "Dive Wizard (+)",
    "38-6":  "Sign Stealer (+)",
    "39-7":  "Meltdown (-)",
    "40-6":  "Bunter (+)",
}

TRAIT_ID_TO_NAME: dict[tuple[int, int], str] = {
    tuple(int(x) for x in k.split("-")): v  # type: ignore[misc]
    for k, v in _TRAIT_MAP_RAW.items()
}


def _trait_display_to_bare_name(display_name: str) -> str:
    if display_name.endswith(" (+)") or display_name.endswith(" (-)"):
        return display_name[:-4].strip()
    return display_name.strip()

# Reverse: bare name (no suffix) AND full display name → (traitId, subtypeId)
# e.g. "Workhorse" and "Workhorse (+)" both map to (23, 6)
_TRAIT_NAME_TO_IDS: dict[str, tuple[int, int]] = {}
for _key, _display in _TRAIT_MAP_RAW.items():
    _ids = tuple(int(x) for x in _key.split("-"))
    _bare = _trait_display_to_bare_name(_display)
    _TRAIT_NAME_TO_IDS[_display.lower()] = _ids  # type: ignore[assignment]
    _TRAIT_NAME_TO_IDS[_bare.lower()] = _ids      # type: ignore[assignment]

TRAIT_NAME_TO_IDS: dict[str, tuple[int, int]] = _TRAIT_NAME_TO_IDS

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def position_to_int(position: str) -> int:
    """Return the integer stored in t_baseball_player_options for the given position string."""
    return POSITION_TO_INT.get(position.strip() if position else "", 0)


def int_to_position(value: int) -> str:
    return INT_TO_POSITION.get(value, "")


def pitch_role_to_int(role: str) -> int:
    """Return PITCH_POSITION integer for SP / RP / CP / SP/RP, or 0 if not a pitcher role."""
    return PITCH_ROLE_TO_INT.get((role or "").strip(), 0)


def is_pitcher_role(role: str | None) -> bool:
    return (role or "").strip() in PITCHER_ROLES


def batting_hand_to_int(hand: str) -> int:
    return BATTING_HAND_TO_INT.get((hand or "R").strip().upper(), 1)


def throwing_hand_to_int(hand: str) -> int:
    return THROWING_HAND_TO_INT.get((hand or "R").strip().upper(), 1)


def chemistry_to_int(chemistry: str) -> int:
    """Convert a chemistry/personality string to its integer value (case-insensitive)."""
    key = (chemistry or "").strip()
    if key in CHEMISTRY_TO_INT:
        return CHEMISTRY_TO_INT[key]
    return CHEMISTRY_TO_INT.get(_CHEMISTRY_ALIASES.get(key.lower(), ""), 0)


def arm_angle_to_int(angle: str) -> int:
    return ARM_ANGLE_TO_INT.get((angle or "").strip(), DEFAULT_ARM_ANGLE)


def option_type_for_key(option_key: int) -> int:
    return OPTION_TYPES.get(option_key, 0)


def parse_arsenal(arsenal_str: str) -> list[int]:
    """
    Parse a comma-separated pitch list string from encoder_plan attributes into
    a list of option key integers.

    Example: "4-Seam Fastball, Changeup, Slider" → [58, 61, 64]
    Unknown pitch names are silently skipped.
    """
    if not arsenal_str:
        return []
    result: list[int] = []
    for part in arsenal_str.split(","):
        normalized = part.strip().lower()
        key = PITCH_NAME_TO_OPTION_KEY.get(normalized)
        if key is not None and key not in result:
            result.append(key)
    return result


def trait_name_to_ids(name: str) -> tuple[int, int] | None:
    """
    Convert a trait display name (with or without the (+)/(-) suffix) to
    (traitId, subtypeId).  Returns None if the name is not recognised.
    """
    if not name or name == "--":
        return None
    return TRAIT_NAME_TO_IDS.get(name.strip().lower())


def all_pitch_option_keys() -> list[int]:
    """Return all option keys that correspond to pitch-type toggles."""
    return [
        OPTION_KEYS["FOUR_SEAM"],
        OPTION_KEYS["TWO_SEAM"],
        OPTION_KEYS["SCREWBALL"],
        OPTION_KEYS["CHANGEUP"],
        OPTION_KEYS["FORK"],
        OPTION_KEYS["CURVEBALL"],
        OPTION_KEYS["SLIDER"],
        OPTION_KEYS["CUTTER"],
    ]
