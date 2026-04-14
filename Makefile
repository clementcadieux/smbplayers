# SMBPlayers – quick layer triggers
#
# Default file paths used when the variables below are not overridden.
# Override any of them on the command line, e.g.:
#   make ingest MANIFEST=my_manifest.json
#   make process INPUT=normalized.json TEAM=TOR
#   make run-all MANIFEST=my_manifest.json

PYTHON        ?= python3 -m smb4_mlb_ratings.cli
MANIFEST      ?= manifest.json
NORMALIZED    ?= export/league_normalized.json
RATINGS       ?= export/league_ratings.json
REPORTS_DIR   ?= team_reports
ROSTER        ?= export/league_roster.json
TEAM          ?=

# Build the optional --team flag only when TEAM is set.
_TEAM_FLAG     = $(if $(TEAM),--team $(TEAM),)

.PHONY: ingest aggregate process generate rank run-all help

## ingest – normalise source CSVs into a player JSON file
ingest:
	$(PYTHON) ingest $(MANIFEST) $(NORMALIZED)

## aggregate – alias for ingest (same operation)
aggregate:
	$(PYTHON) aggregate $(MANIFEST) $(NORMALIZED)

## process – rate an existing normalised player JSON file
process:
	$(PYTHON) process $(NORMALIZED) $(RATINGS) $(_TEAM_FLAG)

## generate – write per-team hitter/pitcher CSVs from a ratings JSON file
generate:
	$(PYTHON) generate $(RATINGS) $(REPORTS_DIR)

## rank – rank rated players into a recommended 22-man roster
rank:
	$(PYTHON) rank $(RATINGS) $(ROSTER)

## run-all – run the full pipeline: ingest → process → generate → rank
run-all: ingest process generate rank

## help – display this message
help:
	@echo ""
	@echo "SMBPlayers pipeline layer triggers"
	@echo ""
	@echo "  make ingest     [MANIFEST=manifest.json]  [NORMALIZED=normalized_players.json]"
	@echo "  make aggregate  [MANIFEST=manifest.json]  [NORMALIZED=normalized_players.json]"
	@echo "  make process    [NORMALIZED=normalized_players.json] [RATINGS=ratings_output.json] [TEAM=TOR]"
	@echo "  make generate   [RATINGS=ratings_output.json]        [REPORTS_DIR=team_reports]"
	@echo "  make rank       [RATINGS=ratings_output.json]        [ROSTER=roster_output.json]"
	@echo "  make run-all    (runs ingest → process → generate → rank with defaults above)"
	@echo ""
