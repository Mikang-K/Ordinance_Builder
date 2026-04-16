"""
Firebase ID Token 검증 미들웨어.

모든 API 엔드포인트에서 Depends(get_current_user)로 사용합니다.
검증 성공 시 Firebase UID(str)를 반환합니다.

로컬 개발:
  .env에 FIREBASE_CREDENTIALS_PATH=<서비스 계정 JSON 경로> 설정

Cloud Run 배포:
  FIREBASE_CREDENTIALS_PATH 미설정 시 Application Default Credentials 자동 사용
"""
from __future__ import annotations

import logging

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import settings

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


def _ensure_firebase_initialized() -> None:
    global _firebase_app
    if _firebase_app is not None:
        return

    if settings.FIREBASE_CREDENTIALS_PATH:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase 초기화: 서비스 계정 JSON 사용")
    else:
        _firebase_app = firebase_admin.initialize_app()
        logger.info("Firebase 초기화: Application Default Credentials 사용")


async def get_current_user(authorization: str = Header(...)) -> str:
    """
    Authorization: Bearer <Firebase ID Token> 헤더를 검증하고 user_id(UID)를 반환합니다.

    실패 케이스:
      - 헤더 없음 / Bearer 형식 불일치 → 401
      - 만료된 토큰 → 401
      - 유효하지 않은 토큰 → 401
    """
    _ensure_firebase_initialized()

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer 토큰 형식이 필요합니다.")

    token = authorization[len("Bearer "):]
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다. 다시 로그인해 주세요.")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")
    except Exception as exc:
        logger.warning("Firebase 토큰 검증 실패: %s", exc)
        raise HTTPException(status_code=401, detail="인증에 실패했습니다.")
