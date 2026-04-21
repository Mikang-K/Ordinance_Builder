import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.graph.state import REQUIRED_FIELDS, OrdinanceBuilderState
from app.prompts.intent_analyzer import INTENT_ANALYZER_SYSTEM, build_intent_analyzer_human

logger = logging.getLogger(__name__)


class ExtractedInfo(BaseModel):
    """Structured output schema for the intent analyzer."""

    region: Optional[str] = Field(None, description="지역명 (공식 행정구역명). 예: '서울특별시 마포구'")
    purpose: Optional[str] = Field(None, description="조례의 주요 목적. 예: '청년 창업 지원'")
    target_group: Optional[str] = Field(None, description="지원 또는 규제 대상 집단. 예: '만 19~39세 청년'")
    support_type: Optional[str] = Field(None, description="지원 방식. 예: '보조금 지급', '현물 지원'")
    budget_range: Optional[str] = Field(None, description="예산 규모. 예: '연간 5억 이내'")
    industry_sector: Optional[str] = Field(None, description="관련 산업 분야. 예: 'IT/소프트웨어', '농업'")
    enforcement_scope: Optional[str] = Field(None, description="시행 범위 또는 기간")
    missing_fields: list[str] = Field(
        default_factory=list,
        description="조례 작성에 필수적이나 아직 언급되지 않은 필드명 목록",
    )


async def intent_analyzer_node(
    state: OrdinanceBuilderState,
    llm: BaseChatModel,
) -> dict:
    """
    Node 1 – Intent Analyzer

    Extracts structured ordinance information from the user's natural language input
    and merges it with previously collected data stored in ordinance_info.

    Input  State: user_input, ordinance_info, messages
    Output State: ordinance_info, missing_fields, current_stage, messages
    """
    structured_llm = llm.with_structured_output(ExtractedInfo)
    existing_info: dict = state.get("ordinance_info") or {}

    human_prompt = build_intent_analyzer_human(existing_info, state["user_input"])
    messages = [
        ("system", INTENT_ANALYZER_SYSTEM),
        ("human", human_prompt),
    ]

    logger.debug("[intent_analyzer] user_input=%r", state["user_input"])
    extracted: ExtractedInfo = await structured_llm.ainvoke(messages)

    # Merge: only overwrite fields that the LLM actually extracted (non-None)
    updated_info = dict(existing_info)
    for field in [
        "region", "purpose", "target_group", "support_type",
        "budget_range", "industry_sector", "enforcement_scope",
    ]:
        new_val = getattr(extracted, field, None)
        if new_val is not None:
            updated_info[field] = new_val

    # Recalculate missing fields based on actual values (LLM hint is advisory only)
    missing = [f for f in REQUIRED_FIELDS if not updated_info.get(f)]

    logger.info(
        "[intent_analyzer] extracted=%s | missing=%s",
        {k: v for k, v in updated_info.items() if v},
        missing,
    )
    return {
        "ordinance_info": updated_info,
        "missing_fields": missing,
        "current_stage": "intent_analysis",
        "messages": [HumanMessage(content=state["user_input"])],
    }
