import logging
from typing import Literal as TypingLiteral

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app.graph.nodes.drafting_agent import DraftArticle, OrdinanceDraft
from app.graph.state import OrdinanceBuilderState
from app.prompts.draft_reviewer import (
    DRAFT_REVIEWER_SYSTEM,
    DRAFT_REVISION_SYSTEM,
    build_draft_reviewer_human,
    build_draft_revision_human,
)

logger = logging.getLogger(__name__)


class ReviewDecision(BaseModel):
    """Structured output for user intent classification during draft review."""

    decision: TypingLiteral["confirm", "revise"] = Field(
        description="사용자 의도: 'confirm'(법률 검증 진행) 또는 'revise'(초안 수정 요청)"
    )


async def draft_reviewer_node(
    state: OrdinanceBuilderState,
    llm: BaseChatModel,
) -> dict:
    """
    Node – Draft Reviewer

    Classifies the user's message as confirm or revise.
    - "confirm": signals route_after_draft_review to proceed to legal_checker
    - "revise":  applies the requested changes, returns updated draft to END
                 so the user can review again

    Input  State: user_input, draft_full_text, draft_articles
    Output State: draft_review_decision, current_stage, response_to_user, messages
                  (on revise: also draft_articles, draft_full_text)
    """
    user_input: str = state.get("user_input") or ""
    draft_full_text: str = state.get("draft_full_text") or ""
    draft_articles: list[dict] = state.get("draft_articles") or []

    # Step 1: Classify user intent (confirm vs revise)
    classifier_llm = llm.with_structured_output(ReviewDecision)
    logger.debug("[draft_reviewer] user_input=%r", user_input)
    decision_result: ReviewDecision = await classifier_llm.ainvoke([
        ("system", DRAFT_REVIEWER_SYSTEM),
        ("human", build_draft_reviewer_human(user_input, draft_full_text)),
    ])
    decision = decision_result.decision
    logger.info("[draft_reviewer] decision=%s", decision)

    if decision == "confirm":
        response = "확인되었습니다. 법률 검증을 시작합니다."
        return {
            "draft_review_decision": "confirm",
            "current_stage": "draft_review",
            "response_to_user": response,
            "messages": [AIMessage(content=response)],
        }

    # Step 2 (revise): Apply changes using a second LLM call
    logger.debug("[draft_reviewer] revise 요청 — 수정 생성 시작")
    reviser_llm = llm.with_structured_output(OrdinanceDraft)
    revised: OrdinanceDraft = await reviser_llm.ainvoke([
        ("system", DRAFT_REVISION_SYSTEM),
        ("human", build_draft_revision_human(user_input, draft_full_text, draft_articles)),
    ])

    preview = "\n\n".join(
        f"**{a.article_no} {a.title}**\n{a.content}"
        for a in revised.articles[:3]
    )
    ellipsis = "\n\n..." if len(revised.articles) > 3 else ""
    response = (
        f"요청하신 수정 사항을 반영했습니다.\n\n"
        f"**{revised.ordinance_title}**\n\n"
        f"{preview}{ellipsis}\n\n"
        f"총 {len(revised.articles)}개 조문입니다. "
        f"수정된 초안을 확인하신 후 법률 검증 진행을 요청해 주세요."
    )

    logger.info("[draft_reviewer] 수정 완료 | title=%r | articles=%d개", revised.ordinance_title, len(revised.articles))
    return {
        "draft_articles": [
            {"article_no": a.article_no, "title": a.title, "content": a.content}
            for a in revised.articles
        ],
        "draft_full_text": revised.full_text,
        "draft_review_decision": "revise",
        "current_stage": "draft_review",
        "response_to_user": response,
        "messages": [AIMessage(content=response)],
    }
