from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.api.schemas import WorkspaceResponse, WorkspaceRevision


def draft_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def revision_view(values: dict[str, Any]) -> tuple[list[dict], str | None, str | None]:
    revisions = list(values.get("revisions") or [])
    active_id = values.get("active_revision_id")
    finalized_id = values.get("finalized_revision_id")
    if revisions:
        return revisions, active_id, finalized_id

    draft = values.get("draft_full_text") or ""
    articles = values.get("article_contents") or {}
    if not draft and not articles:
        return [], None, None
    now = datetime.now(timezone.utc).isoformat()
    completed = values.get("current_stage") == "completed"
    revision_id = "legacy-revision-1"
    revision = {
        "revision_id": revision_id,
        "revision_number": 1,
        "status": "completed" if completed else (
            "ready_to_finalize" if values.get("legal_issues") is not None
            and values.get("current_stage") == "legal_checking" else "editing_draft"
        ),
        "version": 1,
        "article_contents": articles,
        "draft_full_text": draft,
        "legal_issues": values.get("legal_issues") or [],
        "is_legally_valid": values.get("is_legally_valid"),
        "reviewed_draft_hash": draft_hash(draft) if values.get("current_stage") in {"legal_checking", "completed"} else None,
        "legal_reviewed_at": now if values.get("current_stage") in {"legal_checking", "completed"} else None,
        "finalized_at": now if completed else None,
        "created_at": now,
        "updated_at": now,
        "based_on_revision_id": None,
    }
    return [revision], revision_id, revision_id if completed else None


def find_revision(revisions: list[dict], revision_id: str) -> tuple[int, dict]:
    for index, revision in enumerate(revisions):
        if revision.get("revision_id") == revision_id:
            return index, revision
    raise HTTPException(status_code=404, detail="Revision not found.")


def check_version(revision: dict, expected_version: int) -> None:
    if revision.get("version") != expected_version:
        raise HTTPException(status_code=409, detail="Revision version conflict.")


def workspace_response(sid: str, values: dict[str, Any]) -> WorkspaceResponse:
    revisions, active_id, finalized_id = revision_view(values)
    active = next((r for r in revisions if r["revision_id"] == active_id), None)
    finalized = next((r for r in revisions if r["revision_id"] == finalized_id), None)
    status = active.get("status") if active else None
    return WorkspaceResponse(
        session_id=sid,
        active_revision_id=active_id,
        finalized_revision_id=finalized_id,
        active_revision=WorkspaceRevision.model_validate(active) if active else None,
        finalized_revision=WorkspaceRevision.model_validate(finalized) if finalized else None,
        revisions=[WorkspaceRevision.model_validate(r) for r in revisions],
        can_edit_articles=active is not None,
        can_edit_draft=bool(
            active
            and active.get("draft_full_text")
            and status != "completed"
        ),
        can_finalize=status == "ready_to_finalize",
        regeneration_required=(
            "draft" if status == "editing_articles"
            else "legal_review" if status == "editing_draft" else None
        ),
    )
