import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.schemas import EvidenceCreateRequest, EvidenceItem, EvidenceUpdateRequest
from app.db import session_store


class _FakeCursor:
    def __init__(self, sessions):
        self.sessions = sessions
        self._row = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params):
        normalized = " ".join(query.split())
        session_id = params[-1]
        if normalized.startswith("SELECT evidence_library"):
            session = self.sessions.get(session_id)
            self._row = (
                {"evidence_library": deepcopy(session["evidence_library"])}
                if session is not None
                else None
            )
            return

        if normalized.startswith("UPDATE sessions SET evidence_library"):
            import json

            self.sessions[session_id]["evidence_library"] = json.loads(params[0])
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    async def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, sessions):
        self.sessions = sessions
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self, **_kwargs):
        return _FakeCursor(self.sessions)

    async def commit(self):
        self.commits += 1


class _FakePool:
    def __init__(self, sessions):
        self.sessions = sessions

    def connection(self):
        return _FakeConnection(self.sessions)


def _item(item_id="item-1", **overrides):
    value = {
        "id": item_id,
        "source_type": "statute",
        "title": "Local Autonomy Act",
        "article_no": "Article 1",
        "content": "Evidence text",
        "relation_type": "GROUNDS",
        "target_article_key": None,
        "applicable_content": None,
        "note": None,
        "source_message_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applied_at": None,
    }
    value.update(overrides)
    return value


def test_evidence_schema_contract_and_source_types():
    evidence = EvidenceItem.model_validate(_item(source_type="qa_answer"))
    assert evidence.source_type == "qa_answer"
    assert evidence.created_at.tzinfo is not None

    with pytest.raises(ValidationError):
        EvidenceCreateRequest(
            source_type="web_page",
            title="Source",
            article_no="",
            content="Text",
        )


def test_evidence_update_supports_target_note_content_and_applied_timestamp():
    applied_at = datetime.now(timezone.utc)
    update = EvidenceUpdateRequest(
        target_article_key="article_4",
        applicable_content="Apply this wording.",
        note="Reviewed.",
        applied_at=applied_at,
    )
    assert update.target_article_key == "article_4"
    assert update.applicable_content == "Apply this wording."
    assert update.note == "Reviewed."
    assert update.applied_at == applied_at


def test_migration_is_idempotent_and_includes_evidence_library():
    assert (
        "ADD COLUMN IF NOT EXISTS evidence_library JSONB NOT NULL"
        in session_store._MIGRATE_SQL
    )
    assert "evidence_library JSONB" in session_store._CREATE_TABLE_SQL


def test_store_crud_and_deduplication(monkeypatch):
    sessions = {"session-1": {"evidence_library": []}}
    monkeypatch.setattr(session_store, "_pool", _FakePool(sessions))

    async def scenario():
        original = _item()
        stored, created = await session_store.add_evidence_item("session-1", original)
        assert created is True
        assert stored == original

        duplicate = _item(item_id="item-2", note="Different mutable metadata")
        stored, created = await session_store.add_evidence_item("session-1", duplicate)
        assert created is False
        assert stored["id"] == "item-1"
        assert len(sessions["session-1"]["evidence_library"]) == 1

        updated = await session_store.update_evidence_item(
            "session-1",
            "item-1",
            {
                "target_article_key": "article_2",
                "applicable_content": "Suggested language",
                "note": "Apply after review",
                "applied_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert updated["target_article_key"] == "article_2"
        assert updated["note"] == "Apply after review"

        assert await session_store.delete_evidence_item("session-1", "missing") is False
        assert await session_store.delete_evidence_item("session-1", "item-1") is True
        assert sessions["session-1"]["evidence_library"] == []

    asyncio.run(scenario())


def test_update_cannot_create_a_duplicate(monkeypatch):
    sessions = {
        "session-1": {
            "evidence_library": [
                _item(item_id="item-1"),
                _item(
                    item_id="item-2",
                    title="Other",
                    article_no="Article 2",
                    content="Other evidence",
                ),
            ]
        }
    }
    monkeypatch.setattr(session_store, "_pool", _FakePool(sessions))

    async def scenario():
        with pytest.raises(ValueError, match="duplicate_evidence"):
            await session_store.update_evidence_item(
                "session-1",
                "item-2",
                {
                    "title": "Local Autonomy Act",
                    "article_no": "Article 1",
                    "content": "Evidence text",
                },
            )

    asyncio.run(scenario())
