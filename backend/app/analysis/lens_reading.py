"""The shape every P05 lens returns, shared by engines that must not see each other.

This lives apart from any one engine on purpose: if the Catalyst lenses
imported their reading type from the Technical lenses, the import graph that
enforces analytical isolation would have a hole in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REPORTED = "reported"
NO_MATERIAL_CHANGE = "no_material_change"
INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class LensReading:
    """One lens's finding. `status` separates silence from absence."""

    lens: str
    status: str
    direction: str = "neutral"          # positive / negative / neutral
    magnitude: str = "minor"            # minor / moderate / strong / exceptional
    confidence: str = "medium"          # low / medium / high
    persistence: str = "short"          # short / medium / long / structural
    summary: str = ""
    drivers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)
