"""
세션 메타데이터 저장소.

sessions_registry.json 및 인메모리 dict를 대체합니다.
PostgreSQL의 sessions 테이블을 psycopg3 async 방식으로 CRUD합니다.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT        PRIMARY KEY,
    user_id         TEXT        NOT NULL,
    title           TEXT        NOT NULL DEFAULT '새 조례',
    stage           TEXT        NOT NULL DEFAULT 'intent_analysis',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    chat_history    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    initial_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
"""


async def init_db() -> None:
    """앱 시작 시 1회 호출 — 테이블이 없으면 생성합니다."""
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.commit()
    logger.info("sessions 테이블 초기화 완료")


async def create_session(
    *,
    session_id: str,
    user_id: str,
    title: str,
    initial_message: str,
    created_at: str,
) -> None:
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        await conn.execute(
            """
            INSERT INTO sessions
                (session_id, user_id, title, stage, created_at, initial_message)
            VALUES (%s, %s, %s, 'intent_analysis', %s, %s)
            """,
            (session_id, user_id, title, created_at, initial_message),
        )
        await conn.commit()


async def get_session(session_id: str) -> dict[str, Any] | None:
    async with await psycopg.AsyncConnection.connect(
        settings.POSTGRES_URL, row_factory=dict_row
    ) as conn:
        row = await (
            await conn.execute(
                "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
            )
        ).fetchone()
    return row  # None if not found


async def list_sessions_by_user(user_id: str) -> list[dict[str, Any]]:
    async with await psycopg.AsyncConnection.connect(
        settings.POSTGRES_URL, row_factory=dict_row
    ) as conn:
        rows = await (
            await conn.execute(
                """
                SELECT session_id, user_id, title, stage, created_at,
                       chat_history, initial_message
                FROM sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
        ).fetchall()
    return rows


async def update_session(
    *,
    session_id: str,
    stage: str,
    title: str,
    chat_history: list[dict],
) -> None:
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET stage = %s, title = %s, chat_history = %s::jsonb
            WHERE session_id = %s
            """,
            (
                stage,
                title,
                json.dumps(chat_history, ensure_ascii=False),
                session_id,
            ),
        )
        await conn.commit()
