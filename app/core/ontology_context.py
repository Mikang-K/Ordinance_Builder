from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.base import GraphDBInterface

logger = logging.getLogger(__name__)


@dataclass
class SWRLContext:
    """SWRL Rules 2-4 사전 계산 결과. graph_retriever → State에 저장."""
    hierarchy_chain: list[dict] = field(default_factory=list)    # Rule 2
    conflict_chain: list[dict] = field(default_factory=list)     # Rule 3
    penalty_extension: list[dict] = field(default_factory=list)  # Rule 4


class OntologyContext:
    """
    온톨로지 미들웨어 레이어.

    - 정적 (RDF 기반): 모듈 임포트 시 계산된 값을 반환 (class_guide, term_guide)
    - 동적 (DB 기반): 런타임에 keywords로 DB를 쿼리하고 결과를 반환

    workflow.py에서 db와 함께 싱글톤으로 생성되고,
    functools.partial로 필요한 노드에 주입됩니다.
    """

    def __init__(self, db: GraphDBInterface) -> None:
        self._db = db

    async def precompute_swrl(self, keywords: list[str]) -> SWRLContext:
        """
        SWRL Rules 2-4를 병렬 실행하여 SWRLContext 반환.
        graph_retriever에서 호출 → 결과를 State에 저장.
        """
        import asyncio

        async def _safe(fn, default):
            try:
                return await asyncio.to_thread(fn)
            except Exception as exc:
                logger.debug("SWRL 쿼리 생략: %s", exc)
                return default

        hierarchy, conflict, penalty = await asyncio.gather(
            _safe(lambda: self._db.get_hierarchy_chain(keywords=keywords), []),
            _safe(lambda: self._db.get_conflict_chain(keywords=keywords), []),
            _safe(lambda: self._db.get_penalty_extension(keywords=keywords), []),
        )
        return SWRLContext(
            hierarchy_chain=hierarchy,
            conflict_chain=conflict,
            penalty_extension=penalty,
        )

    async def get_article_hints(self, article_key: str, hint_keywords: list[str]) -> str:
        """
        조항 키에 맞는 LegalTerm 힌트 텍스트 반환.
        article_interviewer에서 다음 조항 질문 시 호출.
        DB 미응답 또는 LegalTerm 없으면 빈 문자열 반환.
        """
        try:
            import asyncio
            legal_terms: list[dict] = await asyncio.to_thread(
                lambda: self._db.find_legal_terms(keywords=hint_keywords, limit=3)
            )
            if not legal_terms:
                return ""
            lines = [
                f"  • **{t['term_name']}**: {t['definition'][:120]}"
                + (f" _(출처: {t['source_statute']})_" if t.get("source_statute") else "")
                for t in legal_terms
            ]
            return "\n\n---\n**관련 법령 용어** (OWL 온톨로지 기반)\n" + "\n".join(lines)
        except Exception as exc:
            logger.debug("온톨로지 힌트 생략 (article=%s): %s", article_key, exc)
            return ""
