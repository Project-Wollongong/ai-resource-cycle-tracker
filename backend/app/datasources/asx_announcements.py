import logging
import time
from datetime import datetime

import httpx

from ..config import settings
from .base import AnnouncementSource, RawAnnouncement, SourceBlockedError

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.asx.com.au/",
}

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)

# Verified against the live gateway on 2026-11-25: requests for 200 items still
# return five. This is a recent-announcements feed, not a historical archive.
RECENT_ANNOUNCEMENT_LIMIT = 5


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class AsxJsonAnnouncementSource(AnnouncementSource):
    """ASX announcements via the markitdigital gateway that powers asx.com.au.

    (The legacy www.asx.com.au/asx/1 API is dead — returns 404 as of 2026-07.)
    The access token is the public one shipped in the ASX website frontend; it
    is configurable in case it rotates. Dates come back in UTC. Known risk:
    bot protection / token rotation → SourceBlockedError, pipeline degrades
    gracefully to stored announcements.
    """

    recent_announcement_limit = RECENT_ANNOUNCEMENT_LIMIT

    def __init__(self, base_url: str | None = None, access_token: str | None = None,
                 timeout: float = 20.0):
        self.base_url = (base_url or settings.asx_api_base).rstrip("/")
        self.access_token = access_token or settings.asx_access_token
        self.timeout = timeout

    def file_url(self, document_key: str) -> str:
        return f"{self.base_url}/file/{document_key}?access_token={self.access_token}"

    def fetch(self, code: str, count: int = 20) -> list[RawAnnouncement]:
        url = f"{self.base_url}/companies/{code.lower()}/announcements"
        params = {"access_token": self.access_token, "itemsPerPage": count}
        last_error: Exception | None = None
        for attempt in range(settings.request_max_retries):
            try:
                resp = httpx.get(
                    url, params=params, headers=HEADERS, timeout=self.timeout, follow_redirects=True
                )
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue
            if resp.status_code in (401, 403, 429):
                raise SourceBlockedError(
                    f"ASX API returned {resp.status_code} for {code} "
                    "(bot protection or rotated access token — see ASX_ACCESS_TOKEN)"
                )
            if resp.status_code >= 500:
                last_error = RuntimeError(f"ASX 5xx ({resp.status_code}) for {code}")
                time.sleep(2**attempt)
                continue
            if resp.status_code == 404:
                logger.warning("ASX API has no announcements for %s", code)
                return []
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type:
                raise SourceBlockedError(f"ASX API returned non-JSON ({content_type}) for {code}")
            return self.parse_payload(resp.json(), count=count)
        raise SourceBlockedError(f"ASX API unreachable for {code}: {last_error}")

    def parse_payload(self, payload: dict, count: int | None = None) -> list[RawAnnouncement]:
        items = (payload.get("data") or {}).get("items") or []
        if count is not None:
            items = items[:count]
        out: list[RawAnnouncement] = []
        for item in items:
            headline = str(item.get("headline") or "").strip()
            ann_id = str(item.get("documentKey") or "").strip()
            ann_date = _parse_date(item.get("date"))
            if not headline or not ann_id or ann_date is None:
                logger.warning("skipping unparseable announcement item: %r", item)
                continue
            url = str(item.get("url") or "").strip() or self.file_url(ann_id)
            out.append(
                RawAnnouncement(
                    ann_id=ann_id,
                    headline=headline,
                    ann_date=ann_date,
                    url=url,
                    price_sensitive=bool(item.get("isPriceSensitive")),
                    raw=item,
                )
            )
        return out
