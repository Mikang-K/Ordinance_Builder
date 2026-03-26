from typing import Literal

from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.graph.state import OrdinanceBuilderState
from app.prompts.legal_checker import LEGAL_CHECKER_SYSTEM, build_legal_checker_human


class LegalIssueSchema(BaseModel):
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="위험도: HIGH(즉시 수정 필요), MEDIUM(수정 권고), LOW(개선 제안)"
    )
    related_statute: str = Field(description="관련 상위법령 명칭")
    related_provision: str = Field(description="관련 조문 번호")
    description: str = Field(description="이슈 설명")
    suggestion: str = Field(description="수정 제안")


class LegalCheckResult(BaseModel):
    """Structured output for the legal validation step."""

    is_valid: bool = Field(
        description="HIGH severity 이슈가 없고 법적 위반 사항이 없으면 True"
    )
    issues: list[LegalIssueSchema] = Field(
        default_factory=list,
        description="발견된 법률 이슈 목록 (없으면 빈 리스트)",
    )
    overall_assessment: str = Field(description="조례 전체에 대한 종합 평가 (2~4문장)")


def legal_checker_node(
    state: OrdinanceBuilderState,
    llm: ChatGoogleGenerativeAI,
) -> dict:
    """
    Node 5 – Legal Checker

    Validates the ordinance draft against the retrieved statute provisions.
    Flags conflicts and rates their severity.

    Input  State: draft_full_text, legal_basis
    Output State: legal_issues, is_legally_valid, current_stage,
                  response_to_user, messages
    """
    structured_llm = llm.with_structured_output(LegalCheckResult)

    draft: str = state.get("draft_full_text") or ""
    legal_basis: list[dict] = state.get("legal_basis") or []

    human_prompt = build_legal_checker_human(draft, legal_basis)
    result: LegalCheckResult = structured_llm.invoke(
        [("system", LEGAL_CHECKER_SYSTEM), ("human", human_prompt)]
    )

    # HIGH severity overrides is_valid even if LLM says True
    has_high = any(i.severity == "HIGH" for i in result.issues)
    is_valid = result.is_valid and not has_high

    # Build user-facing summary
    if is_valid:
        response = (
            f"법률 검증이 완료되었습니다. 중대한 상위법 충돌은 발견되지 않았습니다.\n\n"
            f"{result.overall_assessment}"
        )
        if result.issues:
            minor = "\n".join(
                f"  [{i.severity}] {i.description} → {i.suggestion}"
                for i in result.issues
            )
            response += f"\n\n개선 권고 사항:\n{minor}"
    else:
        high_issues = "\n".join(
            f"  [HIGH] {i.description}\n    → 수정 제안: {i.suggestion}"
            for i in result.issues
            if i.severity == "HIGH"
        )
        response = (
            f"법률 검증 결과, 다음 사항의 수정이 필요합니다:\n\n{high_issues}\n\n"
            f"{result.overall_assessment}\n\n"
            f"초안 편집창에서 해당 내용을 수정한 후 법률 검증을 다시 요청하거나, "
            f"이대로 확정하실 수 있습니다."
        )

    legal_issues = [
        {
            "severity": i.severity,
            "related_statute": i.related_statute,
            "related_provision": i.related_provision,
            "description": i.description,
            "suggestion": i.suggestion,
        }
        for i in result.issues
    ]

    return {
        "legal_issues": legal_issues,
        "is_legally_valid": is_valid,
        "current_stage": "legal_checking",
        "response_to_user": response,
        "messages": [AIMessage(content=response)],
    }
