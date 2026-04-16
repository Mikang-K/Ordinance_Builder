import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage

from app.api.schemas import (
    ArticleBatchRequest,
    ChatRequest,
    ChatResponse,
    FinalizeRequest,
    FinalizeResponse,
    MessageRecord,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStateResponse,
    SessionSummary,
)
from app.core.auth import get_current_user
from app.core.limiter import limiter
from app.db.session_store import (
    create_session as db_create_session,
    delete_session as db_delete_session,
    get_session as db_get_session,
    list_sessions_by_user,
    update_session as db_update_session,
)
from app.graph.workflow import get_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ordinance"])


def _derive_title(ordinance_info: dict, initial_message: str = "") -> str:
    region = ordinance_info.get("region", "")
    purpose = ordinance_info.get("purpose", "")
    if region and purpose:
        return f"{region} {purpose} 조례"
    elif purpose:
        return f"{purpose} 조례"
    elif region:
        return f"{region} 조례"
    elif initial_message:
        return initial_message[:40] + ("..." if len(initial_message) > 40 else "")
    return "새 조례"


def _require_ownership(entry: dict | None, user_id: str, session_id: str) -> dict:
    """세션 존재 여부 및 소유권을 검증합니다. 통과 시 entry 반환."""
    if entry is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if entry["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return entry


# Stage that indicates the ordinance is fully confirmed by the user
_COMPLETE_STAGES = {"completed"}

# Stages where the full draft text should be returned to the caller
_DRAFT_VISIBLE_STAGES = {"draft_review", "legal_review_requested", "legal_checking", "completed"}

# Stages where legal issue results should be returned to the caller
_LEGAL_VISIBLE_STAGES = {"legal_checking", "completed"}

# Stages where similar ordinances should be returned to the caller
_SIMILAR_VISIBLE_STAGES = {"retrieving", "drafting", "draft_review",
                            "legal_checking", "completed"}

# Default initial state (injected on session creation)
_DEFAULT_STATE: dict[str, Any] = {
    "messages": [],
    "user_input": "",
    "ordinance_info": {},
    "current_stage": "intent_analysis",
    "missing_fields": [],
    "interview_turn_count": 0,
    "max_interview_turns": 5,
    "legal_basis": [],
    "similar_ordinances": [],
    "article_queue": None,
    "current_article_key": None,
    "article_contents": {},
    "draft_articles": [],
    "draft_full_text": "",
    "draft_review_decision": None,
    "legal_issues": [],
    "is_legally_valid": None,
    "response_to_user": "",
    "error_message": None,
}


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(user_id: str = Depends(get_current_user)):
    """본인의 세션 목록을 생성 시간 역순으로 반환합니다."""
    rows = await list_sessions_by_user(user_id)
    return [
        SessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            stage=r["stage"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


@router.delete("/session/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    """세션을 삭제합니다. 소유자만 삭제할 수 있습니다."""
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)
    await db_delete_session(sid)


@router.get("/session/{session_id}", response_model=SessionStateResponse)
async def get_session_state(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    """세션 메타데이터 및 채팅 기록을 반환합니다 (세션 복원용)."""
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    stage = entry["stage"]
    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}
    state_snapshot = await graph.aget_state(config)
    values = (state_snapshot.values or {}) if state_snapshot else {}

    chat_history = entry.get("chat_history") or []

    return SessionStateResponse(
        session_id=sid,
        title=entry["title"],
        stage=stage,
        created_at=str(entry["created_at"]),
        messages=[MessageRecord(**m) for m in chat_history],
        draft=values.get("draft_full_text") if stage in _DRAFT_VISIBLE_STAGES else None,
        similar_ordinances=(
            values.get("similar_ordinances") if stage in _SIMILAR_VISIBLE_STAGES else None
        ),
        legal_issues=values.get("legal_issues") if stage in _LEGAL_VISIBLE_STAGES else None,
        ordinance_info=values.get("ordinance_info", {}),
    )


@router.post("/session", response_model=SessionCreateResponse)
@limiter.limit("20/minute")
async def create_session(
    request: Request,
    body: SessionCreateRequest,
    user_id: str = Depends(get_current_user),
):
    """
    새 조례 초안 세션을 시작합니다.

    UUID가 API session_id이자 LangGraph MemorySaver thread_id로 사용됩니다.
    """
    session_id = str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    created_at = datetime.now(timezone.utc).isoformat()
    initial_message = body.initial_message or ""
    chat_history: list[dict] = []

    if body.initial_message:
        chat_history.append({"role": "user", "text": body.initial_message})
        initial_state = {
            **_DEFAULT_STATE,
            "user_input": body.initial_message,
            "messages": [HumanMessage(content=body.initial_message)],
        }
        try:
            result = await graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.exception("워크플로우 오류 발생 (session_id=%s)", session_id)
            raise HTTPException(status_code=500, detail="워크플로우 처리 중 오류가 발생했습니다.") from exc

        stage = result.get("current_stage", "intent_analysis")
        ai_message = result.get("response_to_user", "조례 작성을 시작합니다.")
        ordinance_info = result.get("ordinance_info", {})
        chat_history.append({"role": "ai", "text": ai_message})

        await db_create_session(
            session_id=session_id,
            user_id=user_id,
            title=_derive_title(ordinance_info, initial_message),
            initial_message=initial_message,
            created_at=created_at,
        )
        await db_update_session(
            session_id=session_id,
            stage=stage,
            title=_derive_title(ordinance_info, initial_message),
            chat_history=chat_history,
        )
        return SessionCreateResponse(
            session_id=session_id,
            message=ai_message,
            stage=stage,
        )

    await db_create_session(
        session_id=session_id,
        user_id=user_id,
        title=_derive_title({}, initial_message),
        initial_message=initial_message,
        created_at=created_at,
    )
    return SessionCreateResponse(
        session_id=session_id,
        message="안녕하세요! 어떤 조례를 작성하고 싶으신가요? 아이디어를 자유롭게 말씀해 주세요.",
        stage="intent_analysis",
    )


@router.post("/session/{session_id}/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    session_id: uuid.UUID,
    body: ChatRequest,
    user_id: str = Depends(get_current_user),
):
    """
    기존 세션에서 대화를 계속합니다.

    LangGraph MemorySaver가 thread_id로 이전 상태를 복원하므로
    새 user_input만 전달하면 됩니다.
    """
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}

    update: dict[str, Any] = {
        "user_input": body.message,
        "messages": [HumanMessage(content=body.message)],
    }

    if body.draft_text:
        update["draft_full_text"] = body.draft_text
        update["current_stage"] = "legal_review_requested"

    try:
        result = await graph.ainvoke(update, config=config)
    except Exception as exc:
        logger.exception("워크플로우 오류 발생 (session_id=%s)", sid)
        raise HTTPException(status_code=500, detail="워크플로우 처리 중 오류가 발생했습니다.") from exc

    stage: str = result.get("current_stage", "unknown")
    is_valid: bool | None = result.get("is_legally_valid")
    is_complete = stage in _COMPLETE_STAGES
    ai_response = result.get("response_to_user", "")

    ordinance_info = result.get("ordinance_info", {})
    chat_history = list(entry.get("chat_history") or [])
    chat_history.append({"role": "user", "text": body.message})
    chat_history.append({"role": "ai", "text": ai_response})

    await db_update_session(
        session_id=sid,
        stage=stage,
        title=_derive_title(ordinance_info, entry.get("initial_message", "")),
        chat_history=chat_history,
    )

    return ChatResponse(
        session_id=sid,
        message=ai_response,
        stage=stage,
        is_complete=is_complete,
        draft=result.get("draft_full_text") if stage in _DRAFT_VISIBLE_STAGES else None,
        legal_issues=result.get("legal_issues") if stage in _LEGAL_VISIBLE_STAGES else None,
        is_legally_valid=is_valid if stage in _LEGAL_VISIBLE_STAGES else None,
        similar_ordinances=(
            result.get("similar_ordinances") if stage in _SIMILAR_VISIBLE_STAGES else None
        ),
        article_queue=result.get("article_queue"),
        current_article_key=result.get("current_article_key"),
    )


@router.post("/session/{session_id}/articles_batch", response_model=ChatResponse)
async def submit_articles_batch(
    session_id: uuid.UUID,
    request: ArticleBatchRequest,
    user_id: str = Depends(get_current_user),
):
    """모달을 통한 조항 일괄 입력. 조항 인터뷰를 건너뛰고 바로 초안 생성으로 진행합니다."""
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}

    update: dict[str, Any] = {
        "user_input": "모달을 통해 항목을 일괄 입력했습니다.",
        "messages": [HumanMessage(content="[모달을 통한 일괄항목 작성]")],
        "article_contents": request.articles,
        "article_queue": [],
        "current_article_key": None,
        "current_stage": "article_complete",
    }

    try:
        result = await graph.ainvoke(update, config=config)
    except Exception as exc:
        logger.exception("워크플로우 오류 발생 (session_id=%s)", sid)
        raise HTTPException(status_code=500, detail="워크플로우 처리 중 오류가 발생했습니다.") from exc

    stage: str = result.get("current_stage", "unknown")
    is_valid: bool | None = result.get("is_legally_valid")
    is_complete = stage in _COMPLETE_STAGES
    ai_response = result.get("response_to_user", "")

    ordinance_info = result.get("ordinance_info", {})
    chat_history = list(entry.get("chat_history") or [])
    chat_history.append({"role": "user", "text": "모달을 통해 항목을 일괄 입력했습니다."})
    chat_history.append({"role": "ai", "text": ai_response})

    await db_update_session(
        session_id=sid,
        stage=stage,
        title=_derive_title(ordinance_info, entry.get("initial_message", "")),
        chat_history=chat_history,
    )

    return ChatResponse(
        session_id=sid,
        message=ai_response,
        stage=stage,
        is_complete=is_complete,
        draft=result.get("draft_full_text") if stage in _DRAFT_VISIBLE_STAGES else None,
        legal_issues=result.get("legal_issues") if stage in _LEGAL_VISIBLE_STAGES else None,
        is_legally_valid=is_valid if stage in _LEGAL_VISIBLE_STAGES else None,
        similar_ordinances=(
            result.get("similar_ordinances") if stage in _SIMILAR_VISIBLE_STAGES else None
        ),
        article_queue=result.get("article_queue"),
        current_article_key=result.get("current_article_key"),
    )


@router.post("/session/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session(
    session_id: uuid.UUID,
    request: FinalizeRequest = FinalizeRequest(),
    user_id: str = Depends(get_current_user),
):
    """
    조례 초안을 확정합니다.

    현재 저장된 상태를 읽고 completed로 마킹합니다.
    draft_text가 제공되면 사용자가 최종 편집한 버전을 우선 사용합니다.
    """
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}

    state_snapshot = await graph.aget_state(config)
    values = (state_snapshot.values or {}) if state_snapshot else {}

    final_draft = request.draft_text or values.get("draft_full_text", "")
    if not final_draft:
        raise HTTPException(status_code=400, detail="확정할 초안이 없습니다.")

    legal_issues = values.get("legal_issues") or []
    is_valid = values.get("is_legally_valid")

    if values:
        await graph.aupdate_state(
            config,
            {"current_stage": "completed", "draft_full_text": final_draft},
        )

    chat_history = list(entry.get("chat_history") or [])
    await db_update_session(
        session_id=sid,
        stage="completed",
        title=entry["title"],
        chat_history=chat_history,
    )

    return FinalizeResponse(
        session_id=sid,
        draft=final_draft,
        legal_issues=legal_issues,
        is_legally_valid=is_valid,
    )
