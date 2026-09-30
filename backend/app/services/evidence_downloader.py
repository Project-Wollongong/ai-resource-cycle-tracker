"""Download and validate an ASX evidence file without trusting the external URL."""
from dataclasses import dataclass
import httpx


@dataclass
class DownloadedFile:
    content: bytes
    content_type: str


def download_file(url: str, timeout: float = 30.0) -> DownloadedFile:
    if not url:
        raise ValueError("source URL is empty")
    response = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "AI-Resource-Cycle-Tracker/0.1"})
    response.raise_for_status()
    body = response.content
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not body:
        raise ValueError("downloaded file is empty")
    if body[:5] != b"%PDF-":
        raise ValueError(f"download is not a PDF (content-type={content_type or 'unknown'})")
    return DownloadedFile(content=body, content_type=content_type or "application/pdf")
