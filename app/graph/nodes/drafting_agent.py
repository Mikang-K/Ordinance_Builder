from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.graph.state import OrdinanceBuilderState
from app.prompts.drafting_agent import DRAFTING_SYSTEM, build_drafting_human


class DraftArticle(BaseModel):
    article_no: str = Field(description="조문 번호. 예: '제1조'")
    title: str = Field(description="조문 제목. 예: '(목적)'")
    content: str = Field(description="조문 전체 내용 (완전한 문장)")


class OrdinanceDraft(BaseModel):
    """Structured output for the full ordinance draft."""

    ordinance_title: str = Field(description="조례 전체 제목")
    articles: list[DraftArticle] = Field(description="조문 목록 (제1조부터 순서대로, 최소 8개)")
    full_text: str = Field(description="제목과 전체 조문을 합친 완성 텍스트")


def drafting_agent_node(
    state: OrdinanceBuilderState,
    llm: ChatGoogleGenerativeAI,
) -> dict:
    """
    Node 4 – Drafting Agent

    Generates a complete ordinance draft using all collected information,
    retrieved legal basis, and similar ordinance references.

    Input  State: ordinance_info, legal_basis, similar_ordinances
    Output State: draft_articles, draft_full_text, current_stage,
                  response_to_user, messages
    """
    structured_llm = llm.with_structured_output(OrdinanceDraft)

    info: dict = state.get("ordinance_info") or {}
    legal_basis: list[dict] = state.get("legal_basis") or []
    similar: list[dict] = state.get("similar_ordinances") or []
    article_contents: dict = state.get("article_contents") or {}
    legal_terms: list[dict] = state.get("legal_terms") or []

    human_prompt = build_drafting_human(info, legal_basis, similar, article_contents, legal_terms)
    result: OrdinanceDraft = structured_llm.invoke(
        [("system", DRAFTING_SYSTEM), ("human", human_prompt)]
    )

    # Guarantee full_text is never empty — reconstruct from articles if the LLM omitted it
    full_text = (result.full_text or "").strip()
    if not full_text:
        parts = [result.ordinance_title]
        for a in result.articles:
            parts.append(f"\n{a.article_no} {a.title}")
            parts.append(a.content)
        full_text = "\n".join(parts)

    # Build a short preview of the first 3 articles for the user message
    preview = "\n\n".join(
        f"**{a.article_no} {a.title}**\n{a.content}"
        for a in result.articles[:3]
    )
    ellipsis = "\n\n..." if len(result.articles) > 3 else ""
    response = (
        f"조례 초안이 작성되었습니다.\n\n"
        f"**{result.ordinance_title}**\n\n"
        f"{preview}{ellipsis}\n\n"
        f"총 {len(result.articles)}개 조문이 생성되었습니다.\n\n"
        f"초안을 검토해 주세요. 수정이 필요하시면 수정 내용을 알려주시고, "
        f"이상이 없으시면 '확인' 또는 '법률 검증 진행'이라고 입력해 주세요."
    )

    return {
        "draft_articles": [
            {"article_no": a.article_no, "title": a.title, "content": a.content}
            for a in result.articles
        ],
        "draft_full_text": full_text,
        "current_stage": "draft_review",
        "response_to_user": response,
        "messages": [AIMessage(content=response)],
    }
