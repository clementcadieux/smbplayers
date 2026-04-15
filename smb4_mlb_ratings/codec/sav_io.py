"""
Low-level I/O for SMB4 .sav files.

SMB4 save files are DEFLATE-compressed SQLite databases.
A well-formed .sav file begins with one of the zlib DEFLATE magic bytes:
    0x78 0x01  (low compression)
    0x78 0x9C  (default compression)
    0x78 0xDA  (best compression)

Only the standard library (zlib, pathlib, tempfile) is used.
"""

from __future__ import annotations

import tempfile
import zlib
from pathlib import Path

# zlib magic byte that indicates DEFLATE format
_ZLIB_MAGIC = 0x78

# Sibling file extensions deleted when overwriting a .sav to keep SMB4 from
# rejecting a modified file (matches xblbaseball/xbl-roster-importer behaviour)
_STALE_EXTENSIONS = (".sav.bak", ".hash")


def decompress_sav(sav_path: Path) -> bytes:
    """
    Read *sav_path* and return the raw SQLite database bytes.

    Raises
    ------
    ValueError
        If the file does not start with a zlib DEFLATE header.
    OSError
        If the file cannot be read.
    zlib.error
        If decompression fails (file is corrupt or not a valid zlib stream).
    """
    data = sav_path.read_bytes()
    if not data:
        raise ValueError(
            f"{sav_path.name!r} does not appear to be a DEFLATE-compressed .sav file "
            "(file is empty)"
        )
    if data[0] != _ZLIB_MAGIC:
        raise ValueError(
            f"{sav_path.name!r} does not appear to be a DEFLATE-compressed .sav file "
            f"(expected first byte 0x78, got 0x{data[0]:02X})"
        )
    return zlib.decompress(data)


def compress_sav(db_bytes: bytes, sav_path: Path) -> None:
    """
    Compress *db_bytes* using DEFLATE and write the result to *sav_path*.

    Before writing, any sibling `.sav.bak` and `.hash` files with the same
    stem are deleted so SMB4 does not reject the modified save on next load.

    Parameters
    ----------
    db_bytes:
        Raw SQLite database bytes (as returned by ``decompress_sav``).
    sav_path:
        Destination path.  Parent directory must already exist.
    """
    compressed = zlib.compress(db_bytes)

    # Delete stale companion files so the game accepts the modified save
    stem = sav_path.stem.lower()
    parent = sav_path.parent
    for entry in parent.iterdir():
        lower = entry.name.lower()
        if lower.startswith(stem) and any(lower.endswith(ext) for ext in _STALE_EXTENSIONS):
            try:
                entry.unlink()
            except OSError:
                pass  # best-effort

    sav_path.write_bytes(compressed)


def sav_to_temp_sqlite(sav_path: Path) -> tuple[Path, bytes]:
    """
    Decompress *sav_path* and write the SQLite bytes to a temporary file.

    Returns
    -------
    (temp_path, db_bytes)
        *temp_path* is a ``Path`` pointing to the temporary ``.sqlite`` file.
        *db_bytes* are the raw decompressed bytes (kept so the caller can
        recompress without re-reading the temp file if it was not modified).

    The caller is responsible for deleting the temporary file.
    """
    db_bytes = decompress_sav(sav_path)
    suffix = sav_path.stem + ".sqlite"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    import os
    os.close(fd)
    tmp_path = Path(tmp)
    tmp_path.write_bytes(db_bytes)
    return tmp_path, db_bytes
