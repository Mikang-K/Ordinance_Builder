from __future__ import annotations

from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# Required fields that must be collected before drafting can begin
REQUIRED_FIELDS = ["region", "purpose", "target_group", "support_type"]


class OrdinanceBuilderState(TypedDict):
    """
    Full state for the ordinance drafting workflow.

    Design rules:
    - messages: accumulated via add_messages reducer
    - all other fields: last-write-wins (simple overwrite)
    """

    # Conversation history (accumulated, never overwritten)
    messages: Annotated[list[BaseMessage], add_messages]

    # Raw user input for the current turn
    user_input: str

    # Ordinance information collected through the interview
    # keys: region, purpose, target_group, support_type, budget_range,
    #       industry_sector, enforcement_scope
    ordinance_info: dict

    # --- Workflow control ---
    current_stage: Literal[
        "intent_analysis",
        "interviewing",
        "article_interviewing",    # collecting per-article content from user
        "article_complete",        # all article content collected (transient, for routing)
        "retrieving",
        "drafting",
        "draft_review",
        "legal_review_requested",  # user submitted their own draft for legal check
        "legal_checking",
        "completed",
        "error",
    ]
    missing_fields: list[str]    # Required fields not yet collected
    interview_turn_count: int    # Number of interview rounds (prevents infinite loop)
    max_interview_turns: int     # Cap; default 5

    # --- Article interview phase ---
    article_queue: list[str]           # Article keys remaining to be collected
    current_article_key: Optional[str] # Article currently being asked about
    article_contents: dict             # {article_key: str | None} (None = use AI default)

    # --- Retrieval results ---
    legal_basis: list[dict]         # Relevant statute provisions
    similar_ordinances: list[dict]  # Similar ordinances from other regions
    # Flat list of provisions from similar ordinances, keyed for article interview examples
    # Each item: {ordinance_id, region_name, ordinance_title, article_no, content_text}
    article_examples: list[dict]

    # --- Draft output ---
    draft_articles: list[dict]   # [{"article_no": str, "title": str, "content": str}]
    draft_full_text: str         # Complete ordinance text
    draft_review_decision: Optional[Literal["confirm", "revise"]]  # User's decision during draft_review

    # --- Validation results ---
    legal_issues: list[dict]     # [{"severity": str, "description": str, ...}]
    is_legally_valid: Optional[bool]

    # --- Response to surface to the API caller ---
    response_to_user: str
    error_message: Optional[str]
