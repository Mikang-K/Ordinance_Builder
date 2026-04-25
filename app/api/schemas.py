from typing import Literal, Optional

from pydantic import BaseModel, Field


class MessageRecord(BaseModel):
    role: str   # "user" | "ai"
    text: str


class SuggestedOption(BaseModel):
    label: str   # 버튼 표시 텍스트
    value: str   # 클릭 시 전송 값


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
    article_queue: Optional[list[str]] = None
    current_article_key: Optional[str] = None
    ordinance_type: Optional[str] = None


class SessionCreateRequest(BaseModel):
    initial_message: Optional[str] = Field(
        None,
        max_length=4000,
        description="첫 메시지 (없으면 빈 세션 생성 후 별도 /chat 요청)",
    )


class SessionCreateResponse(BaseModel):
    session_id: str
    message: str
    stage: str
    article_queue: Optional[list[str]] = None
    current_article_key: Optional[str] = None
    similar_ordinances: Optional[list] = None
    suggested_options: Optional[list[SuggestedOption]] = None
    ordinance_type: Optional[str] = None


class SimilarOrdinance(BaseModel):
    ordinance_id: str
    region_name: str
    title: str
    similarity_score: float = 0.0
    relevance_reason: str = ""


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000, description="사용자 입력 메시지")
    draft_text: Optional[str] = Field(
        None,
        max_length=100_000,
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
    article_queue: Optional[list[str]] = None
    current_article_key: Optional[str] = None
    suggested_options: Optional[list[SuggestedOption]] = None  # 채팅 칩 선택지
    ordinance_type: Optional[str] = None


class ArticleBatchRequest(BaseModel):
    articles: dict[str, Optional[str]] = Field(
        ...,
        description="조항 키에 쓰여질 값 목록. 값이 null일 경우 인공지능이 기본값으로 자동 생성함."
    )



class FinalizeRequest(BaseModel):
    draft_text: Optional[str] = Field(None, description="사용자가 최종 편집한 초안 텍스트")


class FinalizeResponse(BaseModel):
    session_id: str
    draft: str
    legal_issues: list
    is_legally_valid: Optional[bool]


class QASource(BaseModel):
    source_type: Literal["statute", "ordinance", "legal_term"]
    title: str
    article_no: str
    content: str
    relation_type: str


class QARequest(BaseModel):
    question: str = Field(..., max_length=2000)


class QADirectRequest(BaseModel):
    question: str = Field(..., max_length=500, description="직접 검색 질문 — 세션 컨텍스트 없이 DB 전체 벡터 검색")


class QAResponse(BaseModel):
    answer: str
    sources: list[QASource]
    applicable_content: Optional[str] = None
    applicable_article_key: Optional[str] = None
