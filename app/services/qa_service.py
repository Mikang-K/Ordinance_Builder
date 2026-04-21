"""
QA 직접 검색 서비스 — Design §9 Clean Architecture, Application 계층.

세션 컨텍스트 없이 질문 임베딩 → 벡터 검색 → LLM 답변 경로를 담당합니다.
기존 /session/{id}/qa 엔드포인트(세션 기반)는 이 모듈과 무관하게 유지됩니다.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.embedder import get_embedder
from app.db.base import GraphDBInterface
from app.prompts.qa_agent import QA_SYSTEM, QAOutput, build_qa_human_direct

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def direct_search_qa(
    question: str,
    db: GraphDBInterface | None,
    llm,
) -> tuple[QAOutput, list[dict], list[dict], list[dict]]:
    """
    질문 텍스트를 임베딩하여 Neo4j 전체 DB를 벡터 검색한 뒤 LLM 답변을 생성합니다.

    Returns:
        (QAOutput, legal_basis, legal_terms, similar_ordinances)
        DB 오류 시 빈 리스트와 함께 LLM 단독 답변(degraded mode)을 반환합니다.
    """
    legal_basis: list[dict] = []
    legal_terms: list[dict] = []
    similar_ordinances: list[dict] = []

    if db:
        try:
            embedding: list[float] = await asyncio.to_thread(
                get_embedder().embed_query, question
            )

            # Provision 벡터 검색 + 법률 용어 키워드 검색 병렬 실행
            q_keywords = [w for w in question.split() if len(w) >= 2][:10]
            provision_results, term_results = await asyncio.gather(
                asyncio.to_thread(db.vector_search_provisions, embedding),
                asyncio.to_thread(db.find_legal_terms, q_keywords),
            )
            legal_basis = provision_results
            legal_terms = term_results

            # Provision 벡터 결과 없으면 Ordinance 벡터로 보완 (AuraDB degraded 환경)
            if not legal_basis:
                similar_ordinances = await asyncio.to_thread(
                    db.vector_search_ordinances, embedding
                )
                logger.info(
                    "Provision 벡터 결과 없음 — Ordinance 벡터 %d건으로 보완",
                    len(similar_ordinances),
                )

        except Exception:
            logger.warning("직접 검색 DB 오류 — LLM 단독 답변으로 계속 (degraded mode)")

    human_text = build_qa_human_direct(
        question=question,
        legal_basis=legal_basis,
        legal_terms=legal_terms,
        similar_ordinances=similar_ordinances if similar_ordinances else None,
    )

    structured_llm = llm.with_structured_output(QAOutput)
    result: QAOutput = await structured_llm.ainvoke(
        [SystemMessage(content=QA_SYSTEM), HumanMessage(content=human_text)]
    )

    return result, legal_basis, legal_terms, similar_ordinances
