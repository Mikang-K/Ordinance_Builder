import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app.graph.state import OrdinanceBuilderState
from app.prompts.legal_checker import LEGAL_CHECKER_SYSTEM, build_legal_checker_human

logger = logging.getLogger(__name__)


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
    llm: BaseChatModel,
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
    legal_terms: list[dict] = state.get("legal_terms") or []

    logger.debug("[legal_checker] draft_len=%d | legal_basis=%d건", len(draft), len(legal_basis))
    human_prompt = build_legal_checker_human(draft, legal_basis, legal_terms)
    result: LegalCheckResult = structured_llm.invoke(
        [("system", LEGAL_CHECKER_SYSTEM), ("human", human_prompt)]
    )

    # HIGH severity overrides is_valid even if LLM says True
    has_high = any(i.severity == "HIGH" for i in result.issues)
    is_valid = result.is_valid and not has_high

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for i in result.issues:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    logger.info(
        "[legal_checker] is_valid=%s | HIGH=%d MEDIUM=%d LOW=%d",
        is_valid, counts["HIGH"], counts["MEDIUM"], counts["LOW"],
    )

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
