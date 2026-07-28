from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.revision_service import (
    check_version as _check_version,
    draft_hash as _draft_hash,
    revision_view as _revision_view,
    workspace_response as _workspace_response,
)
from app.api.schemas import DraftRevisionRequest, WorkspaceRevision


def _legacy_state(**overrides):
    value = {
        "current_stage": "completed",
        "article_contents": {"purpose": "protect residents"},
        "draft_full_text": "Article 1 (Purpose)",
        "legal_issues": [],
        "is_legally_valid": True,
    }
    value.update(overrides)
    return value


def test_completed_legacy_checkpoint_projects_to_preserved_revision():
    revisions, active_id, finalized_id = _revision_view(_legacy_state())
    assert len(revisions) == 1
    assert active_id == finalized_id == "legacy-revision-1"
    assert revisions[0]["status"] == "completed"
    assert revisions[0]["draft_full_text"] == "Article 1 (Purpose)"
    assert revisions[0]["reviewed_draft_hash"] == _draft_hash("Article 1 (Purpose)")


def test_workspace_exposes_detailed_inputs_and_finalized_document():
    response = _workspace_response("session-1", _legacy_state())
    assert response.active_revision.article_contents == {"purpose": "protect residents"}
    assert response.finalized_revision.draft_full_text == "Article 1 (Purpose)"
    assert response.can_edit_articles is True
    assert response.can_edit_draft is False
    assert response.can_finalize is False


def test_editing_draft_invalidates_review_and_requires_recheck():
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "revisions": [{
            "revision_id": "revision-2",
            "revision_number": 2,
            "status": "editing_draft",
            "version": 4,
            "article_contents": {},
            "draft_full_text": "changed",
            "legal_issues": [],
            "is_legally_valid": None,
            "legal_reviewed_at": None,
            "finalized_at": None,
            "created_at": now,
            "updated_at": now,
            "based_on_revision_id": "revision-1",
        }],
        "active_revision_id": "revision-2",
        "finalized_revision_id": None,
    }
    response = _workspace_response("session-1", state)
    assert response.regeneration_required == "legal_review"
    assert response.can_finalize is False


def test_expected_version_conflicts_are_rejected():
    with pytest.raises(HTTPException) as exc:
        _check_version({"version": 3}, expected_version=2)
    assert exc.value.status_code == 409


def test_workspace_schema_rejects_invalid_status_and_empty_draft_patch():
    with pytest.raises(ValidationError):
        WorkspaceRevision(
            revision_id="r1",
            revision_number=1,
            status="unknown",
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    with pytest.raises(ValidationError):
        DraftRevisionRequest(draft_text="", expected_version=1)
