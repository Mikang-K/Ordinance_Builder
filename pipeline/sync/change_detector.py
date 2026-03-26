"""
Change detector: compares enforcement_date between the API and Neo4j
to identify statutes/ordinances that need to be re-loaded.

Logic:
  - API enforcement_date > Neo4j stored date → changed (re-load)
  - Not found in Neo4j                       → new (load)
  - API enforcement_date == Neo4j date        → unchanged (skip)
"""

import logging
from dataclasses import dataclass
from enum import Enum

from pipeline.api.law_api_client import OrdinanceSummary, StatuteSummary
from pipeline.loaders.neo4j_loader import Neo4jLoader

logger = logging.getLogger(__name__)


class ChangeStatus(Enum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass
class StatuteChangeResult:
    summary: StatuteSummary
    status: ChangeStatus


@dataclass
class OrdinanceChangeResult:
    summary: OrdinanceSummary
    status: ChangeStatus


class ChangeDetector:
    """
    Compares API-returned summaries against Neo4j stored enforcement_dates.

    Usage:
        detector = ChangeDetector(loader)
        results = detector.detect_statute_changes(summaries)
        to_reload = [r for r in results if r.status != ChangeStatus.UNCHANGED]
    """

    def __init__(self, loader: Neo4jLoader):
        self._loader = loader

    def detect_statute_changes(
        self,
        summaries: list[StatuteSummary],
    ) -> list[StatuteChangeResult]:
        """
        For each statute summary from the API, determine if it is
        new, changed, or unchanged compared to Neo4j.
        """
        results: list[StatuteChangeResult] = []

        for s in summaries:
            stored_date = self._loader.get_statute_enforcement_date(s.mst)
            api_date = _normalize_date(s.enforcement_date)

            if stored_date is None:
                status = ChangeStatus.NEW
            elif api_date > stored_date:
                status = ChangeStatus.CHANGED
            else:
                status = ChangeStatus.UNCHANGED

            if status != ChangeStatus.UNCHANGED:
                logger.info(
                    "statute '%s' [%s]: %s (stored=%s, api=%s)",
                    s.title, s.mst, status.value, stored_date, api_date,
                )

            results.append(StatuteChangeResult(summary=s, status=status))

        unchanged = sum(1 for r in results if r.status == ChangeStatus.UNCHANGED)
        logger.info(
            "statute change detection: %d total, %d unchanged, %d to reload",
            len(results), unchanged, len(results) - unchanged,
        )
        return results

    def detect_ordinance_changes(
        self,
        summaries: list[OrdinanceSummary],
    ) -> list[OrdinanceChangeResult]:
        """Same logic as detect_statute_changes, but for ordinances."""
        results: list[OrdinanceChangeResult] = []

        for o in summaries:
            stored_date = self._loader.get_ordinance_enforcement_date(o.mst)
            api_date = _normalize_date(o.enforcement_date)

            if stored_date is None:
                status = ChangeStatus.NEW
            elif api_date > stored_date:
                status = ChangeStatus.CHANGED
            else:
                status = ChangeStatus.UNCHANGED

            results.append(OrdinanceChangeResult(summary=o, status=status))

        unchanged = sum(1 for r in results if r.status == ChangeStatus.UNCHANGED)
        logger.info(
            "ordinance change detection: %d total, %d unchanged, %d to reload",
            len(results), unchanged, len(results) - unchanged,
        )
        return results


def _normalize_date(raw: str) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD for consistent comparison."""
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw
