"""
세션 메타데이터 저장소.

PostgreSQL의 sessions 테이블을 psycopg3 async 방식으로 CRUD합니다.
요청마다 새 커넥션을 열지 않고 AsyncConnectionPool을 공유합니다.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

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

_pool: AsyncConnectionPool | None = None


async def init_db() -> None:
    """앱 시작 시 1회 호출 — 커넥션 풀 생성 및 테이블 초기화."""
    global _pool
    _pool = AsyncConnectionPool(
        settings.POSTGRES_URL,
        min_size=2,
        max_size=10,
        open=False,
    )
    await _pool.open()
    async with _pool.connection() as conn:
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.commit()
    logger.info("sessions 테이블 및 커넥션 풀 초기화 완료")


async def close_db() -> None:
    """앱 종료 시 1회 호출 — 커넥션 풀 정리."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
    logger.info("커넥션 풀 종료")


async def create_session(
    *,
    session_id: str,
    user_id: str,
    title: str,
    initial_message: str,
    created_at: str,
) -> None:
    async with _pool.connection() as conn:
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
    async with _pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
            )
            return await cur.fetchone()


async def list_sessions_by_user(user_id: str) -> list[dict[str, Any]]:
    async with _pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT session_id, user_id, title, stage, created_at,
                       chat_history, initial_message
                FROM sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return await cur.fetchall()


async def delete_session(session_id: str) -> bool:
    """세션을 삭제합니다. 삭제된 경우 True, 존재하지 않으면 False를 반환합니다."""
    async with _pool.connection() as conn:
        result = await conn.execute(
            "DELETE FROM sessions WHERE session_id = %s",
            (session_id,),
        )
        await conn.commit()
    return result.rowcount > 0


async def update_session(
    *,
    session_id: str,
    stage: str,
    title: str,
    chat_history: list[dict],
) -> None:
    async with _pool.connection() as conn:
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
