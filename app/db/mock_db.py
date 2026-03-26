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

    def get_legal_conflicts(
        self,
        ordinance_id: str,
    ) -> list[dict[str, Any]]:
        # Mock returns empty — CONFLICTS_WITH is only populated by the pipeline.
        return []
