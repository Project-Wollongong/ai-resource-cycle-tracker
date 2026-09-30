"""Stable, portable local storage for original announcement evidence."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from ..config import settings


def evidence_dir(ticker: str, announcement_id: str) -> Path:
    safe_ticker = "".join(c for c in ticker.upper() if c.isalnum() or c in "-_" ) or "UNKNOWN"
    safe_id = "".join(c for c in announcement_id if c.isalnum() or c in "-_" ) or "UNKNOWN"
    return Path(settings.evidence_root) / "asx" / safe_ticker / safe_id


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".download-", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_metadata(directory: Path, metadata: dict) -> None:
    atomic_write_bytes(directory / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
