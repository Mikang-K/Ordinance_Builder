from typing import Optional

from pydantic import BaseModel, Field


class MessageRecord(BaseModel):
    role: str   # "user" | "ai"
    text: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    stage: str
    created_at: str


class SessionStateResponse(BaseModel):
    session_id: str
    title: str
    stage: str
    created_at: str
    messages: list[MessageRecord]
    draft: Optional[str] = None
    similar_ordinances: Optional[list] = None
    legal_issues: Optional[list] = None
    ordinance_info: dict = {}


class SessionCreateRequest(BaseModel):
    initial_message: Optional[str] = Field(
        None,
        description="첫 메시지 (없으면 빈 세션 생성 후 별도 /chat 요청)",
    )


class SessionCreateResponse(BaseModel):
    session_id: str
    message: str
    stage: str


class SimilarOrdinance(BaseModel):
    ordinance_id: str
    region_name: str
    title: str
    similarity_score: float = 0.0
    relevance_reason: str = ""


class ChatRequest(BaseModel):
    message: str = Field(..., description="사용자 입력 메시지")
    draft_text: Optional[str] = Field(
        None,
        description="법률 검토를 요청할 조례 텍스트 (사용자가 직접 편집한 버전). "
                    "제공 시 draft_review 단계를 건너뛰고 법률 검토를 즉시 실행.",
    )


class ChatResponse(BaseModel):
    session_id: str
    message: str             # AI response text
    stage: str               # current workflow stage
    is_complete: bool        # True when ordinance is finalized (stage == completed)
    draft: Optional[str] = None              # full ordinance text
    legal_issues: Optional[list] = None      # legal issue list (after each check)
    is_legally_valid: Optional[bool] = None  # True if no HIGH issues found
    similar_ordinances: Optional[list[SimilarOrdinance]] = None  # similar cases from other regions


class FinalizeRequest(BaseModel):
    draft_text: Optional[str] = Field(None, description="사용자가 최종 편집한 초안 텍스트")


class FinalizeResponse(BaseModel):
    session_id: str
    draft: str
    legal_issues: list
    is_legally_valid: Optional[bool]
