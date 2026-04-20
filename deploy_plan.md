# 조례 빌더 AI — 배포 현황 & SaaS 전환 계획

> 작성일: 2026-04-20  
> 목표: 단일 웹앱 배포 → 플랜 기반 SaaS 서비스 전환

---

## 목차

1. [현재 배포 현황](#1-현재-배포-현황)
2. [현재 vs SaaS 차이](#2-현재-vs-saas-차이)
3. [Phase 1 — 사용량 추적 & 플랜 제한](#3-phase-1--사용량-추적--플랜-제한)
4. [Phase 2 — 결제 연동](#4-phase-2--결제-연동)
5. [Phase 3 — 운영 고도화](#5-phase-3--운영-고도화)
6. [인프라 변경 계획](#6-인프라-변경-계획)
7. [완료 체크리스트](#7-완료-체크리스트)
8. [비용 추정](#8-비용-추정)

---

## 1. 현재 배포 현황

> 상태: **다중 사용자 웹앱 배포 완료**. 인증·격리·레이트리밋은 구현됨. 과금 체계 없음.

### 인프라

| 서비스 | 상태 | 값 |
|--------|------|----|
| Firebase Hosting (프론트엔드) | ✅ 배포 완료 | `https://ordinance-builder-b9f6c.web.app` |
| Cloud Run (백엔드) | ✅ 배포 완료 | `ordinance-builder-b9f6c`, `asia-northeast3` |
| Cloud SQL PostgreSQL | ✅ 운영 중 | LangGraph 체크포인트 + 세션 레지스트리 |
| Neo4j AuraDB | ✅ 연결 완료 | `neo4j+s://da425acb.databases.neo4j.io` |
| GCP 프로젝트 ID | — | `ordinance-builder-b9f6c` |

### 코드 — 이미 구현된 기능

| 항목 | 파일 | 비고 |
|------|------|------|
| Firebase ID Token 검증 | `app/core/auth.py` | `Depends(get_current_user)`, ADC/서비스 계정 모두 지원 |
| 세션 소유권 검증 | `app/api/routers/chat.py` | 타인 세션 403 반환 |
| PostgreSQL 세션 스토어 | `app/db/session_store.py` | 비동기 psycopg3 |
| AsyncPostgresSaver | `app/main.py` | LangGraph 체크포인트 |
| IP 기반 Rate Limit | `app/core/limiter.py` | slowapi, `get_remote_address` |
| 보안 헤더 미들웨어 | `app/main.py` | X-Content-Type-Options 등 |
| 비동기 LLM 호출 | `app/api/routers/chat.py` | `graph.ainvoke()` |
| Google 로그인 | `frontend/src/firebase.ts` | `signInWithRedirect` |
| API 인증 헤더 전송 | `frontend/src/api.ts` | `Authorization: Bearer <token>` |

### 현재 DB 스키마 (PostgreSQL)

```sql
-- sessions 테이블 (app/db/session_store.py)
CREATE TABLE sessions (
    session_id      TEXT        PRIMARY KEY,
    user_id         TEXT        NOT NULL,
    title           TEXT        NOT NULL DEFAULT '새 조례',
    stage           TEXT        NOT NULL DEFAULT 'intent_analysis',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    chat_history    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    initial_message TEXT
);

-- LangGraph 체크포인트 테이블 (AsyncPostgresSaver.setup()이 자동 생성)
-- langgraph_checkpoints, langgraph_writes, ...
```

---

## 2. 현재 vs SaaS 차이

| 항목 | 현재 상태 | SaaS에 필요한 것 |
|------|-----------|-----------------|
| **사용량 제한** | 없음 — 무제한 사용 가능 | 플랜별 월 초안 생성 횟수 제한 |
| **과금 체계** | 없음 | 플랜 테이블 + 결제 연동 |
| **Rate Limit 기준** | IP 주소 | 사용자(user_id) 기준으로 전환 |
| **LLM 비용 통제** | 없음 | 사용자별 LLM 호출 예산 추적 |
| **관리자 기능** | 없음 | 사용량 대시보드, 플랜 수동 변경 |
| **이용 약관 동의** | 없음 | 첫 로그인 시 동의 기록 |

---

## 3. Phase 1 — 사용량 추적 & 플랜 제한

> 예상 기간: 2~3주  
> 목표: 결제 없이도 Free/Pro 플랜 구조를 코드에 적용 가능한 상태로 만들기

### 3-1. PostgreSQL 스키마 추가

```sql
-- 플랜 정의
CREATE TABLE plans (
    plan_id     TEXT PRIMARY KEY,          -- 'free' | 'pro' | 'enterprise'
    name        TEXT NOT NULL,
    monthly_drafts INT NOT NULL DEFAULT 3, -- 월 초안 생성 허용 횟수 (-1 = 무제한)
    price_krw   INT NOT NULL DEFAULT 0
);
INSERT INTO plans VALUES ('free', 'Free', 3, 0);
INSERT INTO plans VALUES ('pro', 'Pro', -1, 29000);

-- 사용자 프로필 (Firebase UID 기반)
CREATE TABLE user_profiles (
    user_id         TEXT        PRIMARY KEY,  -- Firebase UID
    email           TEXT,
    plan_id         TEXT        NOT NULL DEFAULT 'free' REFERENCES plans(plan_id),
    plan_expires_at TIMESTAMPTZ,              -- NULL = 영구 (free 포함)
    tos_agreed_at   TIMESTAMPTZ,              -- 이용 약관 동의 시각
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 월별 사용량 카운터
CREATE TABLE usage_counters (
    user_id     TEXT    NOT NULL,
    year_month  TEXT    NOT NULL,  -- 'YYYY-MM' 형식
    draft_count INT     NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, year_month)
);
```

### 3-2. 사용량 게이트 미들웨어

**영향 파일**: `app/db/user_store.py` (신규), `app/core/plan_gate.py` (신규), `app/api/routers/chat.py`

#### app/db/user_store.py (신규)

```python
"""사용자 프로필 + 사용량 카운터 CRUD."""
import psycopg
from app.core.config import settings


async def get_or_create_user(user_id: str, email: str | None = None) -> dict:
    """최초 로그인 시 user_profiles 행 생성, 이후 조회만."""
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        row = await (await conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = %s", (user_id,)
        )).fetchone()
        if row is None:
            await conn.execute(
                "INSERT INTO user_profiles (user_id, email) VALUES (%s, %s)",
                (user_id, email)
            )
            await conn.commit()
            row = await (await conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = %s", (user_id,)
            )).fetchone()
    return dict(row)


async def increment_draft_count(user_id: str, year_month: str) -> int:
    """이번 달 초안 생성 횟수를 1 증가시키고, 증가 후 값을 반환."""
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        await conn.execute(
            """
            INSERT INTO usage_counters (user_id, year_month, draft_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, year_month)
            DO UPDATE SET draft_count = usage_counters.draft_count + 1
            """,
            (user_id, year_month)
        )
        await conn.commit()
        row = await (await conn.execute(
            "SELECT draft_count FROM usage_counters WHERE user_id = %s AND year_month = %s",
            (user_id, year_month)
        )).fetchone()
    return row[0]


async def get_draft_count(user_id: str, year_month: str) -> int:
    async with await psycopg.AsyncConnection.connect(settings.POSTGRES_URL) as conn:
        row = await (await conn.execute(
            "SELECT draft_count FROM usage_counters WHERE user_id = %s AND year_month = %s",
            (user_id, year_month)
        )).fetchone()
    return row[0] if row else 0
```

#### app/core/plan_gate.py (신규)

```python
"""
초안 생성 전 플랜 한도를 검사하는 FastAPI Dependency.

사용법:
    @router.post("/session/{id}/articles_batch")
    async def submit_articles(
        ...,
        _: None = Depends(check_draft_limit),
    ): ...
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from app.core.auth import get_current_user
from app.db.user_store import get_draft_count, get_or_create_user


async def check_draft_limit(user_id: str = Depends(get_current_user)) -> None:
    profile = await get_or_create_user(user_id)
    plan_id = profile["plan_id"]

    # Pro / Enterprise: 제한 없음
    if plan_id != "free":
        return

    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    count = await get_draft_count(user_id, year_month)

    if count >= 3:  # Free 플랜 월 3회 한도
        raise HTTPException(
            status_code=402,
            detail={
                "code": "DRAFT_LIMIT_EXCEEDED",
                "message": "Free 플랜은 월 3건까지 초안을 생성할 수 있습니다.",
                "upgrade_url": "/pricing",
            }
        )
```

#### chat.py — `/articles_batch` 엔드포인트에 적용

```python
from app.core.plan_gate import check_draft_limit
from app.db.user_store import increment_draft_count

@router.post("/session/{session_id}/articles_batch", response_model=ChatResponse)
async def submit_articles_batch(
    session_id: str,
    request: ArticleBatchRequest,
    user_id: str = Depends(get_current_user),
    _: None = Depends(check_draft_limit),   # ← 한도 초과 시 402
):
    ...
    # 초안 생성 성공 후 카운트 증가
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    await increment_draft_count(user_id, year_month)
    ...
```

### 3-3. Rate Limit — IP → User ID 기준으로 전환

```python
# app/core/limiter.py 수정
from slowapi import Limiter
from fastapi import Request

def _get_user_id(request: Request) -> str:
    """인증된 요청은 user_id, 미인증은 IP를 키로 사용."""
    return getattr(request.state, "user_id", None) or request.client.host

limiter = Limiter(key_func=_get_user_id)
```

```python
# app/main.py — 미들웨어에서 user_id 주입
class UserIdMiddleware(BaseHTTPMiddleware):
    """Firebase UID를 request.state에 저장해 rate limiter가 사용할 수 있게 함."""
    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from firebase_admin import auth as firebase_auth
                decoded = firebase_auth.verify_id_token(auth[7:])
                request.state.user_id = decoded["uid"]
            except Exception:
                pass
        return await call_next(request)
```

### 3-4. 이용 약관 동의 처리 (프론트엔드)

```typescript
// frontend/src/App.tsx — 최초 로그인 시 동의 모달 표시
// GET /api/v1/me → { tos_agreed_at: null } 이면 TosModal 렌더링
// POST /api/v1/me/tos-agree → tos_agreed_at 기록
```

---

## 4. Phase 2 — 결제 연동

> 예상 기간: 1~2주  
> 목표: Pro 플랜 구독 결제 → 자동으로 `user_profiles.plan_id` 갱신

### 결제 옵션 비교

| 옵션 | 장점 | 단점 |
|------|------|------|
| **Stripe** | 글로벌 표준, 웹훅 문서 풍부 | 국내 카드 수수료 3.4% |
| **토스페이먼츠** | 국내 카드 최적화, 수수료 2.2% | 사업자 등록 필요 |
| **포트원(아임포트)** | PG 통합 인터페이스 | 별도 계약 필요 |

> 공무원 대상 서비스 특성상 **토스페이먼츠** 권장 (국내 카드·계좌이체 모두 지원)

### 4-1. Stripe 기준 구현 (변경 최소 경로)

**영향 파일**: `requirements.txt`, `app/api/routers/billing.py` (신규), `app/db/user_store.py`

#### 스키마 추가

```sql
CREATE TABLE subscriptions (
    subscription_id     TEXT        PRIMARY KEY,  -- Stripe subscription ID
    user_id             TEXT        NOT NULL REFERENCES user_profiles(user_id),
    stripe_customer_id  TEXT        NOT NULL,
    plan_id             TEXT        NOT NULL,
    status              TEXT        NOT NULL,  -- 'active' | 'canceled' | 'past_due'
    current_period_end  TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### app/api/routers/billing.py (신규)

```python
"""Stripe 구독 관리 엔드포인트."""
import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from app.core.config import settings

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/checkout")
async def create_checkout_session(user_id: str = Depends(get_current_user)):
    """Pro 플랜 결제 페이지 URL 생성."""
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": settings.STRIPE_PRO_PRICE_ID, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/billing/success",
        cancel_url=f"{settings.FRONTEND_URL}/pricing",
        metadata={"user_id": user_id},
    )
    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(...)):
    """Stripe 이벤트 수신 → user_profiles.plan_id 자동 갱신."""
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        user_id = sub["metadata"]["user_id"]
        plan = "pro" if sub["status"] == "active" else "free"
        await update_user_plan(user_id, plan)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        await update_user_plan(sub["metadata"]["user_id"], "free")

    return {"ok": True}
```

#### config.py 추가 항목

```python
# app/core/config.py
STRIPE_SECRET_KEY: str = ""
STRIPE_WEBHOOK_SECRET: str = ""
STRIPE_PRO_PRICE_ID: str = ""
FRONTEND_URL: str = "https://ordinance-builder-b9f6c.web.app"
```

---

## 5. Phase 3 — 운영 고도화

> 예상 기간: 2~3주 (Phase 1·2 이후)  
> 목표: 서비스 안정 운영에 필요한 관찰성·관리 기능 추가

### 5-1. 관리자 API

```python
# app/api/routers/admin.py (신규)
# GET  /api/admin/users          — 전체 사용자 목록 + 플랜 + 사용량
# POST /api/admin/users/{id}/plan — 플랜 수동 변경 (테스터 Pro 지급 등)
# GET  /api/admin/stats          — 일별 세션 수, 초안 생성 수
```

관리자 권한 판별: `user_profiles.is_admin = TRUE` 컬럼 추가.

### 5-2. LLM 비용 추적

```sql
-- LLM 호출 비용 로그 (초안 생성당 Claude + Gemini + GPT-4o 합산)
CREATE TABLE llm_cost_log (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    session_id  TEXT        NOT NULL,
    node_name   TEXT        NOT NULL,  -- 'drafting_agent' | 'legal_checker' | ...
    input_tokens  INT,
    output_tokens INT,
    cost_usd    NUMERIC(10, 6),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

각 LLM 노드에서 `response.usage_metadata`를 읽어 적재.

### 5-3. 이메일 알림 (SendGrid / Resend)

| 이벤트 | 발송 타이밍 |
|--------|------------|
| 가입 환영 | `user_profiles` 첫 행 생성 시 |
| 사용량 경고 | Free 플랜 월 2/3회 도달 시 |
| 구독 만료 예정 | `current_period_end` 3일 전 |
| 초안 생성 완료 | `/finalize` 호출 시 (PDF 첨부 옵션) |

### 5-4. 초안 PDF 다운로드

```python
# reportlab 또는 WeasyPrint로 draft_full_text → PDF 변환
# GET /api/v1/session/{id}/export/pdf
# → Content-Disposition: attachment; filename="ordinance_draft.pdf"
```

---

## 6. 인프라 변경 계획

### 현재 → SaaS 인프라 비교

```
[현재]
Firebase Hosting → Cloud Run → Cloud SQL + Neo4j AuraDB

[SaaS 추가 사항]
Firebase Hosting → Cloud Run → Cloud SQL (스키마 확장)
                             → Neo4j AuraDB
                             → Stripe API (외부)
                 → Cloud Tasks (비동기 이메일 발송)
                 → Secret Manager (STRIPE_SECRET_KEY 추가)
```

### Secret Manager 추가 항목

```bash
# Phase 1
# 추가 환경변수 없음 (기존 POSTGRES_URL 재사용)

# Phase 2
echo -n "<stripe_secret>" | gcloud secrets create STRIPE_SECRET_KEY --data-file=-
echo -n "<webhook_secret>" | gcloud secrets create STRIPE_WEBHOOK_SECRET --data-file=-
echo -n "<price_id>"       | gcloud secrets create STRIPE_PRO_PRICE_ID --data-file=-
```

### Cloud Run 배포 업데이트 (Phase 2 이후)

```bash
gcloud run services update ordinance-backend \
  --region asia-northeast3 \
  --update-secrets "STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,\
STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,\
STRIPE_PRO_PRICE_ID=STRIPE_PRO_PRICE_ID:latest"
```

### Cloud SQL 마이그레이션

```bash
# 로컬에서 마이그레이션 스크립트 실행
# Cloud SQL Auth Proxy 사용
./cloud-sql-proxy ordinance-builder-b9f6c:asia-northeast3:ordinance-db &
psql "host=127.0.0.1 user=app_user dbname=ordinance_builder" \
  -f migrations/001_saas_tables.sql
```

---

## 7. 완료 체크리스트

### Phase 1 — 사용량 추적 & 플랜 제한

**백엔드**
- [ ] `migrations/001_saas_tables.sql` — `plans`, `user_profiles`, `usage_counters` 테이블 생성
- [ ] `app/db/user_store.py` — 사용자 프로필 + 사용량 CRUD 구현
- [ ] `app/core/plan_gate.py` — Free 플랜 월 3회 한도 Dependency 구현
- [ ] `app/api/routers/chat.py` — `/articles_batch`에 `check_draft_limit` + `increment_draft_count` 추가
- [ ] `app/core/limiter.py` — Rate limit 키를 IP → user_id 기준으로 전환
- [ ] `app/main.py` — `UserIdMiddleware` 추가 + `init_db()`에서 신규 테이블도 초기화
- [ ] `app/api/routers/me.py` (신규) — `GET /me` (플랜·사용량 조회), `POST /me/tos-agree`

**프론트엔드**
- [ ] `frontend/src/api.ts` — `getMyProfile()`, `agreeToTos()` 함수 추가
- [ ] `frontend/src/components/TosModal.tsx` — 최초 로그인 시 약관 동의 모달
- [ ] `frontend/src/components/UsageBadge.tsx` — 헤더에 "이번 달 N/3건" 표시
- [ ] `frontend/src/components/UpgradePrompt.tsx` — 402 응답 시 업그레이드 안내

**배포**
- [ ] Cloud SQL에 마이그레이션 스크립트 실행
- [ ] Cloud Run 재배포 및 동작 확인
- [ ] Free 계정으로 3건 초안 생성 → 4번째 시도 시 402 확인

---

### Phase 2 — 결제 연동

**백엔드**
- [ ] `requirements.txt` — `stripe>=8.0.0` 추가
- [ ] `app/core/config.py` — `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `FRONTEND_URL` 추가
- [ ] `migrations/002_subscriptions.sql` — `subscriptions` 테이블 생성
- [ ] `app/api/routers/billing.py` — checkout, webhook, portal 엔드포인트 구현
- [ ] `app/db/user_store.py` — `update_user_plan()` 구현
- [ ] `app/main.py` — billing 라우터 등록

**프론트엔드**
- [ ] `frontend/src/pages/Pricing.tsx` — 플랜 비교 페이지
- [ ] `frontend/src/pages/BillingSuccess.tsx` — 결제 완료 페이지
- [ ] `frontend/src/api.ts` — `createCheckoutSession()` 함수 추가

**인프라**
- [ ] Stripe 대시보드에서 Pro 플랜 상품·가격 생성
- [ ] Stripe 웹훅 엔드포인트 등록: `POST /api/v1/billing/webhook`
- [ ] Secret Manager에 Stripe 키 3개 등록
- [ ] Cloud Run 환경변수 업데이트

---

### Phase 3 — 운영 고도화

- [ ] `app/api/routers/admin.py` — 관리자 API 구현
- [ ] `migrations/003_admin_llm_cost.sql` — `llm_cost_log`, `user_profiles.is_admin` 추가
- [ ] LLM 노드에서 `usage_metadata` 읽어 `llm_cost_log` 적재
- [ ] 이메일 발송 서비스 연동 (SendGrid 또는 Resend)
- [ ] 초안 PDF 다운로드 엔드포인트 구현
- [ ] 관리자 대시보드 (간단한 내부용 페이지)

---

## 8. 비용 추정

### 현재 (웹앱 배포 상태)

| 항목 | 예상 비용/월 |
|------|-------------|
| Cloud Run (min 1 인스턴스) | ~$15–30 |
| Cloud SQL db-g1-small | ~$10 |
| Neo4j AuraDB Professional | ~$65 |
| Firebase Hosting | $0 (무료 tier) |
| **Gemini API** (일 10세션 기준) | ~$15–50 |
| **Claude API** (초안 생성) | ~$20–80 |
| **GPT-4o API** (법률 검증) | ~$5–20 |
| **합계** | **~$130–255/월** |

### SaaS 전환 후 (일 100세션 목표)

| 항목 | 예상 비용/월 | 비고 |
|------|-------------|------|
| Cloud Run | ~$30–60 | 트래픽 증가 |
| Cloud SQL db-g1-small | ~$10 | 동일 |
| Neo4j AuraDB Professional | ~$65 | 동일 |
| Firebase Hosting | $0 | 동일 |
| **LLM API 합계** | **~$200–600** | 세션당 $0.10–0.30 |
| Stripe 수수료 | 결제액의 3.4% | Pro 전환율에 따라 다름 |
| **합계** | **~$305–735/월** |  |

### 손익 분기점 (Pro 플랜 월 29,000원 기준)

| 조건 | 계산 |
|------|------|
| 고정 인프라 비용 | ~$80/월 ≈ 115,000원 |
| LLM 변동 비용 | 세션당 ~300–900원 |
| 손익 분기 (LLM 제외) | **Pro 4명** |
| 손익 분기 (LLM 포함, 월 100세션) | **Pro 약 15–20명** |

> **핵심 리스크**: LLM 비용이 가장 큰 변수. Free 플랜 월 3건 제한 및 초안 생성(가장 비싼 단계)에만 카운트 적용이 필수.
