from app.db.base import GraphDBInterface
from app.graph.state import OrdinanceBuilderState


def graph_retriever_node(
    state: OrdinanceBuilderState,
    db: GraphDBInterface,
) -> dict:
    """
    Node 3 – Graph Retriever  (no LLM call – DB query only)

    Queries the graph database for:
    1. Relevant statute provisions (legal basis for the ordinance)
    2. Similar ordinances from other regions
    3. Provision content from those similar ordinances (for article interview examples)

    Input  State: ordinance_info
    Output State: legal_basis, similar_ordinances, article_examples, current_stage
    """
    info: dict = state.get("ordinance_info") or {}

    # Build keyword list from collected ordinance info
    keywords = [
        v for k, v in info.items()
        if v and k in ("purpose", "target_group", "support_type", "industry_sector")
    ]
    region: str = info.get("region", "")
    support_type: str = info.get("support_type", "")

    legal_basis = db.find_legal_basis(keywords=keywords, support_type=support_type)
    similar_ordinances = db.find_similar_ordinances(
        region=region,
        keywords=keywords,
        limit=5,
    )

    # Pre-fetch provisions from similar ordinances so article_interviewer can
    # surface per-article examples without additional DB round-trips.
    ordinance_ids = [o["ordinance_id"] for o in similar_ordinances]
    article_examples = db.get_similar_ordinance_provisions(ordinance_ids=ordinance_ids)

    return {
        "legal_basis": legal_basis,
        "similar_ordinances": similar_ordinances,
        "article_examples": article_examples,
        "current_stage": "retrieving",
    }
