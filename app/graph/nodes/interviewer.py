from langchain_core.messages import AIMessage

from app.graph.state import OrdinanceBuilderState

# Deterministic question templates per missing field
FIELD_QUESTIONS: dict[str, str] = {
    "region": "어느 지역의 조례를 작성하고 싶으신가요?\n  (예: 서울특별시 강남구, 경기도 수원시)",
    "purpose": "이 조례의 주요 목적이 무엇인가요?\n  (예: 청년 창업 지원, 농업 활성화, 소상공인 보호)",
    "target_group": "지원 또는 규제 대상이 되는 집단은 어떻게 되나요?\n  (예: 만 19~39세 청년, 소규모 농가, 지역 소상공인)",
    "support_type": "어떤 방식으로 지원하고 싶으신가요?\n  (예: 보조금 지급, 임대료 지원, 시설 제공, 컨설팅)",
    "budget_range": "예산 규모는 어느 정도로 생각하고 계신가요?\n  (예: 연간 5억 이내, 추후 결정)",
    "industry_sector": "특정 산업 분야가 있나요?\n  (예: IT/소프트웨어, 농업, 문화예술, 제조업)",
}


def interviewer_node(state: OrdinanceBuilderState) -> dict:
    """
    Node 2 – Interviewer  (no LLM call – deterministic)

    Generates a natural question for up to 2 missing fields at a time.
    On the first interview turn, also surfaces relevant similar ordinances
    discovered during a prior graph_retriever run (if any).

    Input  State: missing_fields, similar_ordinances, interview_turn_count
    Output State: response_to_user, current_stage, interview_turn_count, messages
    """
    missing: list[str] = state.get("missing_fields") or []
    similar: list[dict] = state.get("similar_ordinances") or []
    turn_count: int = (state.get("interview_turn_count") or 0) + 1

    # Ask at most 2 fields per turn for better UX
    fields_to_ask = missing[:2]
    question_lines = "\n".join(
        f"• {FIELD_QUESTIONS.get(f, f'{f} 정보를 알려주세요.')}"
        for f in fields_to_ask
    )

    response = f"조례 초안 작성을 위해 몇 가지 정보가 필요합니다.\n\n{question_lines}"

    # On the first turn, optionally suggest similar ordinances as reference
    if similar and turn_count == 1:
        refs = "\n".join(
            f"  - {o['region_name']}: {o['title']} ({o['relevance_reason']})"
            for o in similar[:2]
        )
        response += (
            f"\n\n참고로, 유사한 목적의 조례 사례가 있습니다:\n{refs}\n"
            "이를 참고하여 작성하시겠습니까?"
        )

    return {
        "current_stage": "interviewing",
        "interview_turn_count": turn_count,
        "response_to_user": response,
        "messages": [AIMessage(content=response)],
    }
