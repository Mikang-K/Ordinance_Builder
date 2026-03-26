import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    FinalizeRequest,
    FinalizeResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from app.graph.workflow import get_graph

router = APIRouter(prefix="/api/v1", tags=["ordinance"])

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


@router.post("/session", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest):
    """
    Start a new ordinance drafting session.

    Generates a UUID that acts as both the API session_id and the
    LangGraph MemorySaver thread_id, ensuring state continuity across calls.
    """
    session_id = str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    if request.initial_message:
        initial_state = {
            **_DEFAULT_STATE,
            "user_input": request.initial_message,
            "messages": [HumanMessage(content=request.initial_message)],
        }
        try:
            result = graph.invoke(initial_state, config=config)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"워크플로우 오류: {exc}") from exc
        return SessionCreateResponse(
            session_id=session_id,
            message=result.get("response_to_user", "조례 작성을 시작합니다."),
            stage=result.get("current_stage", "intent_analysis"),
        )

    return SessionCreateResponse(
        session_id=session_id,
        message="안녕하세요! 어떤 조례를 작성하고 싶으신가요? 아이디어를 자유롭게 말씀해 주세요.",
        stage="intent_analysis",
    )


@router.post("/session/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    """
    Continue an existing drafting conversation.

    LangGraph MemorySaver restores the previous state using thread_id,
    so only the new user_input needs to be provided.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # Provide only the fields that change on each user turn.
    # LangGraph merges this update into the checkpointed state.
    update: dict[str, Any] = {
        "user_input": request.message,
        "messages": [HumanMessage(content=request.message)],
    }

    # If the caller supplies draft_text, the user has edited the draft themselves
    # and wants legal review performed on their version immediately.
    if request.draft_text:
        update["draft_full_text"] = request.draft_text
        update["current_stage"] = "legal_review_requested"

    try:
        result = graph.invoke(update, config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"워크플로우 오류: {exc}") from exc

    stage: str = result.get("current_stage", "unknown")
    is_valid: bool | None = result.get("is_legally_valid")
    is_complete = stage in _COMPLETE_STAGES

    return ChatResponse(
        session_id=session_id,
        message=result.get("response_to_user", ""),
        stage=stage,
        is_complete=is_complete,
        draft=result.get("draft_full_text") if stage in _DRAFT_VISIBLE_STAGES else None,
        legal_issues=result.get("legal_issues") if stage in _LEGAL_VISIBLE_STAGES else None,
        is_legally_valid=is_valid if stage in _LEGAL_VISIBLE_STAGES else None,
        similar_ordinances=(
            result.get("similar_ordinances") if stage in _SIMILAR_VISIBLE_STAGES else None
        ),
    )


@router.post("/session/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session(session_id: str, request: FinalizeRequest = FinalizeRequest()):
    """
    Confirm and finalize the ordinance draft.

    Reads the current state from memory, marks the session as completed,
    and returns the final draft. Optionally accepts a draft_text override
    (the user's final edited version from the modal).
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # Read the current persisted state without running the graph
    state_snapshot = graph.get_state(config)
    values = (state_snapshot.values or {}) if state_snapshot else {}

    # draft_text from caller takes priority over stored draft
    final_draft = request.draft_text or values.get("draft_full_text", "")
    if not final_draft:
        raise HTTPException(status_code=400, detail="확정할 초안이 없습니다.")

    legal_issues = values.get("legal_issues") or []
    is_valid = values.get("is_legally_valid")

    # Persist the completed stage
    if values:
        graph.update_state(
            config,
            {"current_stage": "completed", "draft_full_text": final_draft},
        )

    return FinalizeResponse(
        session_id=session_id,
        draft=final_draft,
        legal_issues=legal_issues,
        is_legally_valid=is_valid,
    )
