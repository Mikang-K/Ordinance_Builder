from typing import Any

from app.db.base import GraphDBInterface
from app.db.seed_data import MOCK_ORDINANCE_PROVISIONS, MOCK_ORDINANCES, MOCK_PROVISIONS, MOCK_STATUTES


class MockGraphDB(GraphDBInterface):
    """
    In-memory mock implementation of GraphDBInterface.

    Simulates Neo4j graph traversal using simple keyword matching.
    Replace with Neo4jGraphDB by changing one line in workflow.py.
    """

    def find_legal_basis(
        self,
        keywords: list[str],
        support_type: str,
    ) -> list[dict[str, Any]]:
        results = []
        lower_keywords = [kw.lower() for kw in keywords if kw]

        for provision in MOCK_PROVISIONS:
            content_lower = provision["content_text"].lower()
            matched = any(kw in content_lower for kw in lower_keywords)
            # Also match against support_type keywords (보조금, 지원 등)
            support_matched = support_type and support_type.lower() in content_lower

            if matched or support_matched:
                statute = next(
                    (s for s in MOCK_STATUTES if s["id"] == provision["statute_id"]),
                    None,
                )
                if statute:
                    results.append(
                        {
                            "statute_id": statute["id"],
                            "statute_title": statute["title"],
                            "provision_article": provision["article_no"],
                            "provision_content": provision["content_text"],
                            "relation_type": "BASED_ON",
                        }
                    )

        # Deduplicate and cap at 5
        seen = set()
        unique = []
        for r in results:
            key = r["provision_article"] + r["statute_id"]
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique[:5]

    def find_similar_ordinances(
        self,
        region: str,
        keywords: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        lower_keywords = [kw.lower() for kw in keywords if kw]
        results = []

        for ord_ in MOCK_ORDINANCES:
            # Exclude the same region
            if ord_["region_name"] == region:
                continue

            ord_keywords_lower = [k.lower() for k in ord_.get("keywords", [])]
            title_lower = ord_["title"].lower()

            score = sum(
                1
                for kw in lower_keywords
                if kw in title_lower or kw in ord_keywords_lower
            )

            if score > 0:
                matched_kws = [kw for kw in lower_keywords if kw in title_lower or kw in ord_keywords_lower]
                reason = f"'{', '.join(matched_kws)}' 관련 유사 조례"
                results.append(
                    {
                        "ordinance_id": ord_["ordinance_id"],
                        "region_name": ord_["region_name"],
                        "title": ord_["title"],
                        "relevance_reason": reason,
                        "_score": score,
                    }
                )

        results.sort(key=lambda x: x["_score"], reverse=True)
        # Remove internal score field before returning
        for r in results:
            r.pop("_score", None)
        return results[:limit]

    def get_limiting_provisions(
        self,
        legal_term: str,
    ) -> list[dict[str, Any]]:
        term_lower = legal_term.lower()
        return [
            {
                "article_no": p["article_no"],
                "content_text": p["content_text"],
                "is_penalty_clause": p["is_penalty_clause"],
            }
            for p in MOCK_PROVISIONS
            if p["is_penalty_clause"] and term_lower in p["content_text"].lower()
        ]

    def get_similar_ordinance_provisions(
        self,
        ordinance_ids: list[str],
    ) -> list[dict[str, Any]]:
        return [
            p for p in MOCK_ORDINANCE_PROVISIONS
            if p["ordinance_id"] in ordinance_ids
        ]

    def find_legal_terms(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        mock_terms = [
            {
                "term_name": "보조금",
                "definition": "국가 또는 지방자치단체가 특정 사업을 지원하기 위하여 반대급부 없이 교부하는 금전적 급부를 말한다.",
                "source_statute": "보조금 관리에 관한 법률",
            },
            {
                "term_name": "청년",
                "definition": "19세 이상 34세 이하인 사람을 말한다. 다만, 다른 법령 및 조례에서 청년에 대한 연령을 다르게 적용하는 경우에는 그에 따른다.",
                "source_statute": "청년기본법",
            },
            {
                "term_name": "창업",
                "definition": "중소기업을 새로 설립하는 것을 말한다.",
                "source_statute": "중소기업 창업 지원법",
            },
            {
                "term_name": "소상공인",
                "definition": "소기업 중 상시 근로자 수가 10명 미만인 사업자로서 업종별 상시 근로자 수 등이 대통령령으로 정하는 기준에 해당하는 자를 말한다.",
                "source_statute": "소상공인 보호 및 지원에 관한 법률",
            },
            {
                "term_name": "중소기업",
                "definition": "중소기업기본법 제2조에 따른 기업으로서 업종별로 매출액 또는 자산총액 등이 대통령령으로 정하는 기준에 맞는 기업을 말한다.",
                "source_statute": "중소기업기본법",
            },
        ]
        return [
            t for t in mock_terms
            if any(kw in t["term_name"] for kw in keywords)
        ][:limit]

    def vector_search_provisions(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        # Mock: return first N provisions regardless of embedding similarity.
        # In tests this is sufficient; real semantic ranking only matters in production.
        results = []
        for provision in MOCK_PROVISIONS[:limit]:
            statute = next(
                (s for s in MOCK_STATUTES if s["id"] == provision["statute_id"]),
                None,
            )
            if statute:
                results.append({
                    "statute_id": statute["id"],
                    "statute_title": statute["title"],
                    "provision_article": provision["article_no"],
                    "provision_content": provision["content_text"],
                    "relation_type": "VECTOR_MATCH",
                })
        return results

    def vector_search_ordinances(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        # Mock: return first N ordinances regardless of embedding similarity.
        return [
            {
                "ordinance_id": o["ordinance_id"],
                "region_name": o["region_name"],
                "title": o["title"],
                "similarity_score": 0.9,
                "relevance_reason": "벡터 유사도 기반 추천 (Mock)",
            }
            for o in MOCK_ORDINANCES[:limit]
        ]

    def get_legal_conflicts(
        self,
        ordinance_id: str,
    ) -> list[dict[str, Any]]:
        # Mock returns empty — CONFLICTS_WITH is only populated by the pipeline.
        return []
