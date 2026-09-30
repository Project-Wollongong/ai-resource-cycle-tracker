"""Provider-neutral contracts used by ingestion and P03.

Concrete ASX/Yahoo providers may change without changing Announcement,
EvidenceDocument, PriceBar or CommodityBar consumers.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .base import RawAnnouncement


@dataclass
class DownloadResult:
    content: bytes
    content_type: str
    source_url: str
    fetched_at: datetime


class AnnouncementProvider(Protocol):
    def fetch(self, code: str, count: int = 20) -> list[RawAnnouncement]: ...


class EvidenceProvider(Protocol):
    def fetch_original_file(self, source_url: str) -> DownloadResult: ...


class MarketDataProvider(Protocol):
    def fetch_prices(self, code: str, start: datetime | None = None, end: datetime | None = None) -> list[dict]: ...


class CommodityProvider(Protocol):
    def fetch_commodity_prices(self, instrument: str, start: datetime | None = None, end: datetime | None = None) -> list[dict]: ...
