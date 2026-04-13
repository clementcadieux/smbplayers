from __future__ import annotations

from pathlib import Path

from ..aggregation import aggregate_from_manifest
from .savant import IngestManifest, RosterFilter, load_manifest


def ingest_from_manifest(manifest: IngestManifest | Path):
    # Compatibility wrapper for existing callers.
    return aggregate_from_manifest(manifest)


__all__ = ["IngestManifest", "RosterFilter", "load_manifest", "ingest_from_manifest"]
