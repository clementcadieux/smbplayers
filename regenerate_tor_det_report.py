#!/usr/bin/env python3
"""Regenerate TOR/DET combined report with updated roster."""
import json
import subprocess
import sys

# Run ingest-rate for Blue Jays
print("Ingesting Blue Jays data...")
result = subprocess.run([
    sys.executable, "-m", "smb4_mlb_ratings.cli",
    "ingest-rate",
    "examples/exports/bluejays_live_manifest.json",
    "examples/exports/bluejays_live_ratings_new.json"
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"Blue Jays ingest failed: {result.stderr}")
    sys.exit(1)
print("✓ Blue Jays ingest complete")

# Run ingest-rate for Tigers
print("Ingesting Tigers data...")
result = subprocess.run([
    sys.executable, "-m", "smb4_mlb_ratings.cli",
    "ingest-rate",
    "examples/exports/tigers_live_manifest.json",
    "examples/exports/tigers_live_ratings_new.json"
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"Tigers ingest failed: {result.stderr}")
    sys.exit(1)
print("✓ Tigers ingest complete")

# Load both rating files and combine
with open("examples/exports/bluejays_live_ratings_new.json") as f:
    tor_data = json.load(f)

with open("examples/exports/tigers_live_ratings_new.json") as f:
    det_data = json.load(f)

# Merge players - data is a list directly
tor_players = tor_data if isinstance(tor_data, list) else tor_data.get("players", [])
det_players = det_data if isinstance(det_data, list) else det_data.get("players", [])

combined = tor_players + det_players

# Write combined report
with open("examples/exports/tor_det_combined_report.json", "w") as f:
    json.dump(combined, f, indent=2)

print(f"✓ Combined report written: {len(combined)} total players")
print(f"  - Blue Jays: {len(tor_players)}")
print(f"  - Tigers: {len(det_players)}")
