import asyncio
from io import BytesIO
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

from app.api.schemas import (
    ArticleBatchRequest,
    ChatRequest,
    ChatResponse,
    EvidenceAppliedRequest,
    EvidenceCreateRequest,
    EvidenceItem,
    EvidenceUpdateRequest,
    FinalizeRequest,
    FinalizeResponse,
    MessageRecord,
    ModelStatusItem,
    ModelStatusResponse,
    QADirectRequest,
    QAMessageRecord,
    QARequest,
    QAResponse,
    QASource,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStateResponse,
    SessionSummary,
    SuggestedOption,
    ArticlesRevisionRequest,
    DraftRevisionRequest,
    RevisionMutationRequest,
    WorkspaceResponse,
    WorkspaceRevision,
)
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.core.llm import get_llm
from app.db.session_store import (
    add_evidence_item as db_add_evidence_item,
    create_session as db_create_session,
    delete_evidence_item as db_delete_evidence_item,
    delete_session as db_delete_session,
    get_session as db_get_session,
    list_sessions_by_user,
    save_qa_history as db_save_qa_history,
    update_evidence_item as db_update_evidence_item,
    update_session as db_update_session,
)
from app.graph.nodes._article_examples import find_article_examples
from app.graph.workflow import get_db, get_graph
from app.prompts.qa_agent import QA_SYSTEM, QAOutput, build_qa_human
from app.services.qa_service import direct_search_qa
from app.services.revision_service import (
    check_version as _check_version,
    draft_hash as _draft_hash,
    find_revision as _find_revision,
    revision_view as _revision_view,
    workspace_response as _workspace_response,
)
from app.db.session_store import session_revision_lock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ordinance"])


def _role_llm(role: str):
    config = settings.llm_config(role)
    return get_llm(config["provider"], model=config["model"], base_url=config["base_url"], timeout=config["timeout"])


@router.get("/model-status", response_model=ModelStatusResponse)
async def model_status() -> ModelStatusResponse:
    """Return selected model metadata without credentials or endpoint URLs."""
    models = []
    for role in ("intent", "drafting", "reviewer", "legal"):
        config = settings.llm_config(role)
        available = settings.llm_available(role)
        models.append(ModelStatusItem(
            role=role, provider=str(config["provider"]), model=str(config["model"]),
            deployment="local" if config["provider"] in {"ollama", "openai_compatible"} else "cloud",
            status="available" if available else "unavailable",
            detail=None if available else "configuration_missing",
        ))
    count = sum(item.status == "available" for item in models)
    overall = "available" if count == len(models) else ("degraded" if count else "unavailable")
    return ModelStatusResponse(status=overall, models=models)

# 필드별 채팅 칩 선택지 (인터뷰 단계에서 사용)
_FIELD_OPTIONS: dict[str, list[dict]] = {
    "region": [
        {"label": "서울특별시", "value": "서울특별시"},
        {"label": "부산광역시", "value": "부산광역시"},
        {"label": "인천광역시", "value": "인천광역시"},
        {"label": "대구광역시", "value": "대구광역시"},
        {"label": "경기도", "value": "경기도"},
    ],
    "purpose": [
        {"label": "청년 창업 지원", "value": "청년 창업 지원"},
        {"label": "소상공인 지원", "value": "소상공인 지원"},
        {"label": "주거 복지", "value": "주거 복지 지원"},
        {"label": "문화·체육 활동", "value": "문화·체육 활동 지원"},
        {"label": "농업 진흥", "value": "농업 진흥 지원"},
    ],
    "target_group": [
        {"label": "청년 (19~39세)", "value": "만 19세 이상 39세 이하 청년"},
        {"label": "노인 (65세 이상)", "value": "만 65세 이상 노인"},
        {"label": "장애인", "value": "장애인복지법상 등록 장애인"},
        {"label": "소상공인", "value": "소상공인기본법상 소상공인"},
        {"label": "다문화가족", "value": "다문화가족지원법상 다문화가족"},
    ],
    "support_type": [
        {"label": "보조금 지급", "value": "보조금 지급"},
        {"label": "현물 지원", "value": "현물 지원 (물품·서비스)"},
        {"label": "바우처", "value": "바우처 지급"},
        {"label": "교육·컨설팅", "value": "교육 및 컨설팅 지원"},
        {"label": "시설 이용권", "value": "시설 이용 지원"},
    ],
}


def _build_suggested_options(stage: str, missing_fields: list[str]) -> list[SuggestedOption]:
    """인터뷰 단계에서 첫 번째 누락 필드의 선택지를 반환합니다."""
    if stage != "interviewing" or not missing_fields:
        return []
    first_field = missing_fields[0]
    return [SuggestedOption(**o) for o in _FIELD_OPTIONS.get(first_field, [])]


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


def _legal_issue_value(issue: Any, key: str, default: str = "") -> str:
    if isinstance(issue, dict):
        value = issue.get(key, default)
    else:
        value = getattr(issue, key, default)
    return "" if value is None else str(value)


def _format_legal_issues_text(legal_issues: list[Any]) -> str:
    if not legal_issues:
        return "발견된 법률 검토 이슈가 없습니다."

    lines: list[str] = []
    for index, issue in enumerate(legal_issues, start=1):
        severity = _legal_issue_value(issue, "severity", "UNKNOWN")
        statute = _legal_issue_value(issue, "related_statute")
        provision = _legal_issue_value(issue, "related_provision")
        description = _legal_issue_value(issue, "description")
        suggestion = _legal_issue_value(issue, "suggestion")
        related = " ".join(part for part in [statute, provision] if part).strip()

        lines.append(f"{index}. 중대도: {severity}")
        if related:
            lines.append(f"   관련 조항: {related}")
        if description:
            lines.append(f"   설명: {description}")
        if suggestion:
            lines.append(f"   제안: {suggestion}")
    return "\n".join(lines)


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _build_export_txt(*, draft: str) -> bytes:
    return draft.encode("utf-8")


def _set_docx_korean_font(document: Any, font_name: str = "맑은 고딕") -> None:
    from docx.oxml.ns import qn

    target_styles = [
        document.styles["Normal"],
        document.styles["Heading 1"],
        document.styles["Heading 2"],
    ]
    for style in target_styles:
        style.font.name = font_name
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), font_name)


def _build_export_docx(*, draft: str) -> bytes:
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Word 파일 생성을 위한 python-docx 의존성이 설치되어 있지 않습니다.",
        ) from exc

    document = Document()
    font_name = "맑은 고딕"
    _set_docx_korean_font(document, font_name)
    for line in draft.splitlines() or [""]:
        paragraph = document.add_paragraph(line)
        for run in paragraph.runs:
            run.font.name = font_name
            run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), font_name)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _safe_download_filename(filename: str | None, extension: str, fallback_stem: str) -> str:
    stem = (filename or "").strip()
    if stem.lower().endswith(f".{extension}"):
        stem = stem[: -(len(extension) + 1)]
    stem = _INVALID_FILENAME_CHARS.sub("-", stem).strip(" .")
    return f"{stem or fallback_stem}.{extension}"


def _download_headers(filename: str, fallback_filename: str = "ordinance-final") -> dict[str, str]:
    encoded_filename = quote(filename)
    extension = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
    ascii_fallback = _INVALID_FILENAME_CHARS.sub("-", fallback_filename).strip(" .")
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]", "-", ascii_fallback) or "ordinance-final"
    if not ascii_fallback.lower().endswith(f".{extension.lower()}"):
        ascii_fallback = f"{ascii_fallback}.{extension}"
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}'
        )
    }


# Stage that indicates the ordinance is fully confirmed by the user
_COMPLETE_STAGES = {"completed"}

# Stages where the full draft text should be returned to the caller
_DRAFT_VISIBLE_STAGES = {"draft_review", "legal_review_requested", "legal_checking", "completed"}

# Stages where legal issue results should be returned to the caller
_LEGAL_VISIBLE_STAGES = {"legal_checking", "completed"}

# Stages where similar ordinances should be returned to the caller
_SIMILAR_VISIBLE_STAGES = {"retrieving", "article_interviewing", "drafting", "draft_review",
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
    "revisions": [],
    "active_revision_id": None,
    "finalized_revision_id": None,
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

    qa_history_data = entry.get("qa_history") or []
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
        article_queue=values.get("article_queue"),
        current_article_key=values.get("current_article_key"),
        ordinance_type=values.get("ordinance_type"),
        qa_history=[QAMessageRecord(**m) for m in qa_history_data] or None,
        evidence_library=[
            EvidenceItem.model_validate(item)
            for item in (entry.get("evidence_library") or [])
        ],
    )


@router.get(
    "/session/{session_id}/evidence",
    response_model=list[EvidenceItem],
)
async def list_evidence(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)
    return [
        EvidenceItem.model_validate(item)
        for item in (entry.get("evidence_library") or [])
    ]


@router.post(
    "/session/{session_id}/evidence",
    response_model=EvidenceItem,
)
async def create_evidence(
    session_id: uuid.UUID,
    body: EvidenceCreateRequest,
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    evidence = {
        "id": str(uuid.uuid4()),
        **body.model_dump(mode="json"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    stored, _created = await db_add_evidence_item(sid, evidence)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return EvidenceItem.model_validate(stored)


@router.patch(
    "/session/{session_id}/evidence/{evidence_id}",
    response_model=EvidenceItem,
)
@router.put(
    "/session/{session_id}/evidence/{evidence_id}",
    response_model=EvidenceItem,
)
async def update_evidence(
    session_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: EvidenceUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    changes = body.model_dump(mode="json", exclude_unset=True)
    try:
        updated = await db_update_evidence_item(sid, str(evidence_id), changes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Duplicate evidence.") from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Evidence item not found.")
    return EvidenceItem.model_validate(updated)


@router.post(
    "/session/{session_id}/evidence/{evidence_id}/applied",
    response_model=EvidenceItem,
)
async def mark_evidence_applied(
    session_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: EvidenceAppliedRequest = EvidenceAppliedRequest(),
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    changes = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        **body.model_dump(mode="json", exclude_unset=True),
    }
    updated = await db_update_evidence_item(sid, str(evidence_id), changes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Evidence item not found.")
    return EvidenceItem.model_validate(updated)


@router.delete(
    "/session/{session_id}/evidence/{evidence_id}",
    status_code=204,
)
async def delete_evidence(
    session_id: uuid.UUID,
    evidence_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)
    if not await db_delete_evidence_item(sid, str(evidence_id)):
        raise HTTPException(status_code=404, detail="Evidence item not found.")


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
            "ordinance_type": body.ordinance_type,  # 프론트엔드에서 명시적으로 전달 → LLM 추출 불필요
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
        missing_fields = result.get("missing_fields") or []
        return SessionCreateResponse(
            session_id=session_id,
            message=ai_message,
            stage=stage,
            article_queue=result.get("article_queue"),
            current_article_key=result.get("current_article_key"),
            similar_ordinances=(
                result.get("similar_ordinances") if stage in _SIMILAR_VISIBLE_STAGES else None
            ),
            suggested_options=_build_suggested_options(stage, missing_fields) or None,
            ordinance_type=result.get("ordinance_type"),
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

    missing_fields = result.get("missing_fields") or []
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
        suggested_options=_build_suggested_options(stage, missing_fields) or None,
        ordinance_type=result.get("ordinance_type"),
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
        ordinance_type=result.get("ordinance_type"),
    )


async def _owned_workspace(
    session_id: uuid.UUID, user_id: str
) -> tuple[str, dict, Any, dict[str, Any]]:
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)
    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}
    snapshot = await graph.aget_state(config)
    values = dict((snapshot.values or {}) if snapshot else {})
    return sid, entry, graph, values


async def _lock_revision_mutation(session_id: uuid.UUID):
    async with session_revision_lock(str(session_id)):
        yield


@router.get("/session/{session_id}/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    sid, _entry, _graph, values = await _owned_workspace(session_id, user_id)
    return _workspace_response(sid, values)


@router.get("/session/{session_id}/revisions", response_model=list[WorkspaceRevision])
async def list_revisions(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
):
    _sid, _entry, _graph, values = await _owned_workspace(session_id, user_id)
    revisions, _active_id, _finalized_id = _revision_view(values)
    return [WorkspaceRevision.model_validate(item) for item in revisions]


@router.patch(
    "/session/{session_id}/revisions/{revision_id}/articles",
    response_model=WorkspaceResponse,
)
async def save_revision_articles(
    session_id: uuid.UUID,
    revision_id: str,
    body: ArticlesRevisionRequest,
    user_id: str = Depends(get_current_user),
    _lock: None = Depends(_lock_revision_mutation),
):
    sid, _entry, graph, values = await _owned_workspace(session_id, user_id)
    revisions, active_id, finalized_id = _revision_view(values)
    index, current = _find_revision(revisions, revision_id)
    _check_version(current, body.expected_version)

    # Editing a finalized revision branches instead of overwriting it.
    if revision_id == finalized_id or current.get("status") == "completed":
        now = datetime.now(timezone.utc).isoformat()
        current = {
            **current,
            "revision_id": str(uuid.uuid4()),
            "revision_number": max(r["revision_number"] for r in revisions) + 1,
            "status": "editing_articles",
            "version": 1,
            "article_contents": body.articles,
            "draft_full_text": "",
            "legal_issues": [],
            "is_legally_valid": None,
            "reviewed_draft_hash": None,
            "legal_reviewed_at": None,
            "finalized_at": None,
            "created_at": now,
            "updated_at": now,
            "based_on_revision_id": revision_id,
        }
        revisions.append(current)
        active_id = current["revision_id"]
    else:
        current = {
            **current,
            "article_contents": body.articles,
            "status": "editing_articles",
            "version": current["version"] + 1,
            "draft_full_text": "",
            "legal_issues": [],
            "is_legally_valid": None,
            "reviewed_draft_hash": None,
            "legal_reviewed_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        revisions[index] = current

    config = {"configurable": {"thread_id": sid}}
    await graph.aupdate_state(config, {
        "revisions": revisions,
        "active_revision_id": active_id,
        "finalized_revision_id": finalized_id,
        "article_contents": body.articles,
        "draft_full_text": "",
        "legal_issues": [],
        "is_legally_valid": None,
        "current_stage": "article_complete",
    })
    values.update(
        revisions=revisions, active_revision_id=active_id,
        finalized_revision_id=finalized_id, current_stage="article_complete",
    )
    return _workspace_response(sid, values)


@router.post(
    "/session/{session_id}/revisions/from-articles",
    response_model=WorkspaceResponse,
)
async def regenerate_from_articles(
    session_id: uuid.UUID,
    body: RevisionMutationRequest,
    user_id: str = Depends(get_current_user),
    _lock: None = Depends(_lock_revision_mutation),
):
    sid, entry, graph, values = await _owned_workspace(session_id, user_id)
    revisions, active_id, finalized_id = _revision_view(values)
    if not active_id:
        raise HTTPException(status_code=409, detail="No active revision.")
    index, current = _find_revision(revisions, active_id)
    _check_version(current, body.expected_version)
    if current.get("status") != "editing_articles":
        raise HTTPException(status_code=409, detail="Article regeneration is not required.")

    config = {"configurable": {"thread_id": sid}}
    result = await graph.ainvoke({
        "article_contents": current["article_contents"],
        "article_queue": [],
        "current_article_key": None,
        "current_stage": "article_complete",
        "legal_issues": [],
        "is_legally_valid": None,
    }, config=config)
    now = datetime.now(timezone.utc).isoformat()
    updated = {
        **current,
        "status": "editing_draft",
        "version": current["version"] + 1,
        "draft_full_text": result.get("draft_full_text") or "",
        "legal_issues": [],
        "is_legally_valid": None,
        "reviewed_draft_hash": None,
        "updated_at": now,
    }
    revisions[index] = updated
    await graph.aupdate_state(config, {
        "revisions": revisions, "active_revision_id": active_id,
        "finalized_revision_id": finalized_id,
    })
    await db_update_session(
        session_id=sid, stage="draft_review", title=entry["title"],
        chat_history=list(entry.get("chat_history") or []),
    )
    result.update(revisions=revisions, active_revision_id=active_id,
                  finalized_revision_id=finalized_id)
    return _workspace_response(sid, result)


@router.patch(
    "/session/{session_id}/revisions/{revision_id}/draft",
    response_model=WorkspaceResponse,
)
async def save_revision_draft(
    session_id: uuid.UUID,
    revision_id: str,
    body: DraftRevisionRequest,
    user_id: str = Depends(get_current_user),
    _lock: None = Depends(_lock_revision_mutation),
):
    sid, entry, graph, values = await _owned_workspace(session_id, user_id)
    revisions, active_id, finalized_id = _revision_view(values)
    index, current = _find_revision(revisions, revision_id)
    if revision_id != active_id or current.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Only the active revision can be edited.")
    _check_version(current, body.expected_version)
    updated = {
        **current,
        "draft_full_text": body.draft_text,
        "status": "editing_draft",
        "version": current["version"] + 1,
        "legal_issues": [],
        "is_legally_valid": None,
        "reviewed_draft_hash": None,
        "legal_reviewed_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    revisions[index] = updated
    config = {"configurable": {"thread_id": sid}}
    await graph.aupdate_state(config, {
        "revisions": revisions, "draft_full_text": body.draft_text,
        "legal_issues": [], "is_legally_valid": None, "current_stage": "draft_review",
    })
    await db_update_session(
        session_id=sid, stage="draft_review", title=entry["title"],
        chat_history=list(entry.get("chat_history") or []),
    )
    values.update(revisions=revisions, active_revision_id=active_id,
                  finalized_revision_id=finalized_id)
    return _workspace_response(sid, values)


@router.post(
    "/session/{session_id}/revisions/{revision_id}/legal-review",
    response_model=WorkspaceResponse,
)
async def review_revision(
    session_id: uuid.UUID,
    revision_id: str,
    body: RevisionMutationRequest,
    user_id: str = Depends(get_current_user),
    _lock: None = Depends(_lock_revision_mutation),
):
    sid, entry, graph, values = await _owned_workspace(session_id, user_id)
    revisions, active_id, finalized_id = _revision_view(values)
    index, current = _find_revision(revisions, revision_id)
    if revision_id != active_id:
        raise HTTPException(status_code=409, detail="Only the active revision can be reviewed.")
    _check_version(current, body.expected_version)
    if not current.get("draft_full_text"):
        raise HTTPException(status_code=400, detail="Draft is empty.")

    config = {"configurable": {"thread_id": sid}}
    result = await graph.ainvoke({
        "draft_full_text": current["draft_full_text"],
        "current_stage": "legal_review_requested",
        "legal_issues": [],
        "is_legally_valid": None,
    }, config=config)
    now = datetime.now(timezone.utc).isoformat()
    updated = {
        **current,
        "status": "ready_to_finalize",
        "version": current["version"] + 1,
        "legal_issues": result.get("legal_issues") or [],
        "is_legally_valid": result.get("is_legally_valid"),
        "reviewed_draft_hash": _draft_hash(current["draft_full_text"]),
        "legal_reviewed_at": now,
        "updated_at": now,
    }
    revisions[index] = updated
    await graph.aupdate_state(config, {
        "revisions": revisions, "active_revision_id": active_id,
        "finalized_revision_id": finalized_id,
    })
    await db_update_session(
        session_id=sid, stage="legal_checking", title=entry["title"],
        chat_history=list(entry.get("chat_history") or []),
    )
    result.update(revisions=revisions, active_revision_id=active_id,
                  finalized_revision_id=finalized_id)
    return _workspace_response(sid, result)


@router.post(
    "/session/{session_id}/revisions/{revision_id}/finalize",
    response_model=WorkspaceResponse,
)
async def finalize_revision(
    session_id: uuid.UUID,
    revision_id: str,
    body: RevisionMutationRequest,
    user_id: str = Depends(get_current_user),
    _lock: None = Depends(_lock_revision_mutation),
):
    sid, entry, graph, values = await _owned_workspace(session_id, user_id)
    revisions, active_id, finalized_id = _revision_view(values)
    index, current = _find_revision(revisions, revision_id)
    if revision_id != active_id:
        raise HTTPException(status_code=409, detail="Only the active revision can be finalized.")
    _check_version(current, body.expected_version)
    if (
        current.get("status") != "ready_to_finalize"
        or current.get("reviewed_draft_hash") != _draft_hash(current.get("draft_full_text") or "")
    ):
        raise HTTPException(status_code=409, detail="The current draft has not passed legal review.")
    now = datetime.now(timezone.utc).isoformat()
    revisions[index] = {
        **current, "status": "completed", "version": current["version"] + 1,
        "finalized_at": now, "updated_at": now,
    }
    config = {"configurable": {"thread_id": sid}}
    await graph.aupdate_state(config, {
        "revisions": revisions, "active_revision_id": revision_id,
        "finalized_revision_id": revision_id, "current_stage": "completed",
        "draft_full_text": current["draft_full_text"],
        "legal_issues": current.get("legal_issues") or [],
        "is_legally_valid": current.get("is_legally_valid"),
    })
    await db_update_session(
        session_id=sid, stage="completed", title=entry["title"],
        chat_history=list(entry.get("chat_history") or []),
    )
    values.update(revisions=revisions, active_revision_id=revision_id,
                  finalized_revision_id=revision_id, current_stage="completed")
    return _workspace_response(sid, values)


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

    reviewed_draft = values.get("draft_full_text", "")
    final_draft = request.draft_text or reviewed_draft
    if not final_draft:
        raise HTTPException(status_code=400, detail="확정할 초안이 없습니다.")
    if values.get("current_stage") != "legal_checking" or final_draft != reviewed_draft:
        raise HTTPException(
            status_code=409,
            detail="The current draft must complete legal review before finalization.",
        )

    legal_issues = values.get("legal_issues") or []
    is_valid = values.get("is_legally_valid")

    if values:
        revisions, active_id, _finalized_id = _revision_view(values)
        if active_id:
            index, revision = _find_revision(revisions, active_id)
            now = datetime.now(timezone.utc).isoformat()
            revisions[index] = {
                **revision,
                "draft_full_text": final_draft,
                "legal_issues": legal_issues,
                "is_legally_valid": is_valid,
                "reviewed_draft_hash": _draft_hash(final_draft),
                "legal_reviewed_at": revision.get("legal_reviewed_at") or now,
                "status": "completed",
                "version": revision["version"] + 1,
                "finalized_at": now,
                "updated_at": now,
            }
        await graph.aupdate_state(
            config,
            {
                "current_stage": "completed",
                "draft_full_text": final_draft,
                "revisions": revisions,
                "active_revision_id": active_id,
                "finalized_revision_id": active_id,
            },
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


@router.get("/session/{session_id}/export")
async def export_final_result(
    session_id: uuid.UUID,
    format: str = Query("txt", pattern="^(txt|docx)$"),
    filename: str | None = Query(None, min_length=1, max_length=120),
    user_id: str = Depends(get_current_user),
):
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}
    state_snapshot = await graph.aget_state(config)
    values = (state_snapshot.values or {}) if state_snapshot else {}

    revisions, _active_id, finalized_id = _revision_view(values)
    finalized = next(
        (revision for revision in revisions if revision.get("revision_id") == finalized_id),
        None,
    )
    if finalized is None and entry["stage"] != "completed":
        raise HTTPException(status_code=409, detail="No finalized ordinance is available for export.")
    draft = (finalized or {}).get("draft_full_text") or values.get("draft_full_text", "")
    if not draft:
        raise HTTPException(status_code=400, detail="저장할 최종 초안이 없습니다.")

    if format == "txt":
        data = _build_export_txt(draft=draft)
        download_filename = _safe_download_filename(filename, "txt", f"ordinance-final-{sid}")
        media_type = "text/plain; charset=utf-8"
    else:
        data = _build_export_docx(draft=draft)
        download_filename = _safe_download_filename(filename, "docx", f"ordinance-final-{sid}")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers=_download_headers(download_filename),
    )


def _extract_qa_keywords(question: str, ordinance_info: dict) -> list[str]:
    base = [
        ordinance_info.get("purpose", ""),
        ordinance_info.get("target_group", ""),
        ordinance_info.get("support_type", ""),
        ordinance_info.get("industry_sector", ""),
    ]
    q_words = [w for w in question.split() if len(w) >= 2]
    return [w for w in base + q_words if w][:10]


@router.post("/session/{session_id}/qa", response_model=QAResponse)
@limiter.limit("20/minute")
async def qa_chat(
    request: Request,
    session_id: uuid.UUID,
    body: QARequest,
    user_id: str = Depends(get_current_user),
):
    """GraphRAG 기반 Q&A: Neo4j에서 법령·조례를 검색해 질문에 답변합니다. 워크플로우 state를 변경하지 않습니다."""
    sid = str(session_id)
    entry = await db_get_session(sid)
    _require_ownership(entry, user_id, sid)

    # 1. 체크포인트 읽기 (읽기 전용)
    graph = get_graph()
    config = {"configurable": {"thread_id": sid}}
    state_snapshot = await graph.aget_state(config)
    values = (state_snapshot.values or {}) if state_snapshot else {}

    ordinance_info = values.get("ordinance_info", {})
    article_examples_cache = values.get("article_examples", [])
    current_article_key = values.get("current_article_key")
    current_stage = values.get("current_stage", "")
    draft_full_text = values.get("draft_full_text", "")

    # 2. 키워드 추출
    keywords = _extract_qa_keywords(body.question, ordinance_info)
    support_type = ordinance_info.get("support_type", "")

    # 3. GraphRAG 검색: 체크포인트 캐시 우선 → fresh 검색 fallback
    db = get_db()
    legal_basis: list[dict] = []
    legal_terms: list[dict] = []

    cached_legal_basis = values.get("legal_basis") or []

    if cached_legal_basis:
        # 1순위: 세션 생성 시 graph_retriever가 수집한 법령 (해당 조례에 최적화)
        legal_basis = cached_legal_basis
        if db:
            try:
                legal_terms = await asyncio.to_thread(db.find_legal_terms, keywords)
            except Exception:
                logger.warning("법률 용어 검색 실패 — 용어 없이 계속")
    else:
        # 2순위: 캐시 없으면 fresh 키워드 검색 (기존 동작)
        if db:
            try:
                legal_basis, legal_terms = await asyncio.gather(
                    asyncio.to_thread(db.find_legal_basis, keywords, support_type),
                    asyncio.to_thread(db.find_legal_terms, keywords),
                )
            except Exception:
                logger.warning("GraphRAG DB 검색 실패 — LLM 단독 답변으로 계속")

    # 4. 조항 예시 필터링 (캐시 재사용, article_interviewing 단계만)
    article_ex: list[dict] = []
    if current_stage == "article_interviewing" and current_article_key and article_examples_cache:
        article_ex = find_article_examples(current_article_key, article_examples_cache, max_count=3)

    # 5. LLM 구조화 출력 호출
    try:
        llm = _role_llm("intent")
        structured_llm = llm.with_structured_output(QAOutput)
        human_text = build_qa_human(
            question=body.question,
            ordinance_info=ordinance_info,
            legal_basis=legal_basis,
            legal_terms=legal_terms,
            article_examples=article_ex,
            current_article_key=current_article_key,
            draft_full_text=draft_full_text,
        )
        result: QAOutput = await structured_llm.ainvoke(
            [SystemMessage(content=QA_SYSTEM), HumanMessage(content=human_text)]
        )
    except Exception as exc:
        logger.exception("QA LLM 호출 실패 (session_id=%s)", sid)
        raise HTTPException(status_code=500, detail="AI 답변 생성 중 오류가 발생했습니다.") from exc

    # 6. 검색된 그래프 데이터로 sources 구성
    sources: list[QASource] = []
    for lb in legal_basis[:3]:
        sources.append(QASource(
            source_type="statute",
            title=lb.get("statute_title", ""),
            article_no=lb.get("provision_article", ""),
            content=lb.get("provision_content", "")[:200],
            relation_type=lb.get("relation_type", ""),
        ))
    for lt in legal_terms[:2]:
        sources.append(QASource(
            source_type="legal_term",
            title=lt.get("source_statute", ""),
            article_no=lt.get("term_name", ""),
            content=lt.get("definition", "")[:200],
            relation_type="DEFINES",
        ))

    # QA 교환 내역을 DB에 저장 (세션 복원 시 복구 가능하도록)
    try:
        qa_history = list(entry.get("qa_history") or [])
        qa_history.append({"role": "user", "text": body.question})
        qa_history.append({
            "role": "ai",
            "text": result.answer,
            "sources": [s.model_dump() for s in sources],
            "applicable_content": result.applicable_content,
            "applicable_article_key": result.applicable_article_key,
        })
        await db_save_qa_history(sid, qa_history)
    except Exception:
        logger.warning("QA 내역 저장 실패 (session_id=%s) — 답변은 정상 반환", sid)

    return QAResponse(
        answer=result.answer,
        sources=sources,
        applicable_content=result.applicable_content,
        applicable_article_key=result.applicable_article_key,
    )


@router.post("/qa", response_model=QAResponse)
@limiter.limit("20/minute")
async def qa_direct(
    request: Request,
    body: QADirectRequest,
    user_id: str = Depends(get_current_user),
):
    """직접 검색 QA: 질문 임베딩 → Neo4j 전체 벡터 검색 → LLM 답변. 세션 독립적."""
    db = get_db()

    try:
        result, legal_basis, legal_terms, similar_ordinances = await direct_search_qa(
            question=body.question,
            db=db,
            llm=_role_llm("intent"),
            current_article_key=body.current_article_key,
            ordinance_info=body.ordinance_info,
        )
    except Exception as exc:
        logger.exception("직접 QA LLM 호출 실패")
        raise HTTPException(status_code=500, detail="AI 답변 생성 중 오류가 발생했습니다.") from exc

    sources: list[QASource] = []
    for lb in legal_basis[:3]:
        sources.append(QASource(
            source_type="statute",
            title=lb.get("statute_title", ""),
            article_no=lb.get("provision_article", ""),
            content=lb.get("provision_content", "")[:200],
            relation_type=lb.get("relation_type", "VECTOR_MATCH"),
        ))
    for lt in legal_terms[:2]:
        sources.append(QASource(
            source_type="legal_term",
            title=lt.get("source_statute", ""),
            article_no=lt.get("term_name", ""),
            content=lt.get("definition", "")[:200],
            relation_type="DEFINES",
        ))
    for o in similar_ordinances[:2]:
        sources.append(QASource(
            source_type="ordinance",
            title=o.get("title", ""),
            article_no=o.get("region_name", ""),
            content=o.get("relevance_reason", ""),
            relation_type="VECTOR_MATCH",
        ))

    return QAResponse(
        answer=result.answer,
        sources=sources,
        applicable_content=result.applicable_content,
        applicable_article_key=result.applicable_article_key,
    )
