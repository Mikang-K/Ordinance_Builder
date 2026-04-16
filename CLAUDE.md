# 조례 빌더 AI (Ordinance Builder AI)

> 대화형 AI를 통해 지자체별 특수성을 반영하고, 상위법령을 준수하는 **지방 조례 초안**을 단계별로 생성·검토하는 풀스택 AI 서비스

## 프로젝트 소개

- **대화형 인터뷰**: 사용자가 자연어로 아이디어를 입력하면 AI가 필수 정보를 단계적으로 수집
- **그래프 기반 법령 검색**: Neo4j Graph DB에서 관련 상위법·유사 조례를 의미적으로 탐색
- **법적 초안 자동 생성**: 수집된 정보와 법령 근거를 바탕으로 완전한 조례 조문 출력
- **실시간 법률 검증**: 생성된 초안을 상위법 조항과 대조하여 충돌 위험 고지

를 제공합니다.

### 핵심 설계 원칙

| 원칙 | 구현 방식 |
|------|-----------|
| **법적 안정성** | Neo4j LIMITS/CONFLICTS_WITH 관계 기반 실시간 충돌 감지 |
| **사용자 편의성** | 단계별 인터뷰 루프, 조항별 "기본값" 자동 생성 옵션 |
| **데이터 기반** | 전국 지자체 조례 SIMILAR_TO 관계망, 벡터 유사도 검색 |
| **확장성** | GraphDBInterface(ABC) 추상화로 Mock↔Neo4j↔AuraDB 교체 가능 |

---

## 핵심 기능

### 1. 대화형 조례 인터뷰

필수 4개 필드(`region`, `purpose`, `target_group`, `support_type`)가 모두 확보될 때까지 자연어로 반복 질문합니다. Gemini가 사용자 입력에서 정보를 자동 추출하므로, 구조화된 폼 없이 자유로운 대화가 가능합니다.

### 2. 조항별 세부 인터뷰

9개 조문 템플릿(목적·정의·지원대상·지원내용·지원금액·신청방법·심사선정·환수제재·위임)에 대해 개별적으로 세부 내용을 수집합니다. 각 조항마다 "기본값"을 입력하면 AI가 유사 조례를 참고해 자동 생성합니다.

### 3. 그래프 DB 기반 법령 검색

```
Graph DB 탐색 경로 (우선순위 순):
1. DELEGATES 경로: 상위법이 명시적으로 위임한 조례 영역
2. BASED_ON 경로: 해당 영역 기존 조례의 법령 근거
3. 키워드 폴백 + 벡터 유사도 검색 (Gemini Embedding 3072차원)
```

Neo4j의 관계 그래프를 순회해 법령 근거와 타 지자체 유사 조례를 함께 제공합니다.

### 4. 법적 조문 초안 생성

Gemini 2.5 Pro가 수집된 정보와 법령 근거를 바탕으로 제1조~최종조까지 완전한 조례문을 생성합니다. 구조화 출력(`OrdinanceDraft` Pydantic 모델)으로 파싱 오류 없이 안정적으로 처리됩니다.

### 5. AI 자체 검토 및 사용자 편집

생성된 초안을 AI가 스스로 검토합니다. 사용자는 편집 모달에서 직접 수정 후 재검증을 요청할 수 있으며, `draft_review_decision`(confirm/revise)으로 워크플로우가 분기됩니다.

### 6. 상위법 정합성 검증

```json
{
  "severity": "HIGH",
  "related_statute": "보조금 관리에 관한 법률 제22조",
  "description": "보조금 지급 상한선 미설정 시 법 위반 가능",
  "suggestion": "제5조에 연간 지급 한도 명시 필요"
}
```

HIGH·MEDIUM·LOW 3단계 심각도로 분류하여 사용자에게 위험 요소를 고지합니다.

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    React + TypeScript (Vite)                    │
│              Chat UI / DraftModal / LegalIssuesPanel            │
│                      http://localhost:3000                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────▼──────────────────────────────────────┐
│                   FastAPI Backend  :8000                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  LangGraph Workflow                      │   │
│  │                                                          │   │
│  │  START ──[route_at_start]─────────────────────────────► │   │
│  │          │                                               │   │
│  │          ├─[legal_review_requested]─► legal_checker      │   │
│  │          ├─[draft_review]──────────► draft_reviewer      │   │
│  │          ├─[article_interviewing/article_complete]─► article_interviewer │   │
│  │          └─[otherwise]─────────────► intent_analyzer     │   │
│  │                                           │              │   │
│  │                              [누락 필드?]─┤              │   │
│  │                         yes ◄─────────────┤              │   │
│  │                          │          [정보 완비]          │   │
│  │                    interviewer            │              │   │
│  │                          │         graph_retriever       │   │
│  │                         END               │              │   │
│  │                               [article_queue?]           │   │
│  │                          yes ◄────────────┤              │   │
│  │                          │           no ◄─┤              │   │
│  │                   article_planner   drafting_agent        │   │
│  │                          │               │              │   │
│  │                   article_interviewer    END             │   │
│  │                [조항 완료?]─yes─► drafting_agent         │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  MemorySaver (thread_id = session_id)                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Bolt (7687)
┌──────────────────────────▼──────────────────────────────────────┐
│              Neo4j Graph DB  :7474 / :7687                      │
│  Vector Index: idx_provision_embedding (3072d, cosine)          │
│  Vector Index: idx_ordinance_embedding  (3072d, cosine)         │
│  노드: Statute / Provision / Ordinance / LegalTerm              │
└─────────────────────────────────────────────────────────────────┘
                           ▲
          ┌────────────────┘
          │  pipeline/ (독립 모듈)
┌─────────┴───────────────────────────────────────────────────────┐
│         국가법령정보센터 Open API  →  ETL Pipeline               │
│   LawApiClient → SchemaMapper → Neo4jLoader                     │
│   initial_load.py (4단계) / incremental_update.py (증분)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## LangGraph 워크플로우

### State 설계

`OrdinanceBuilderState`는 TypedDict 기반으로 전체 대화 맥락을 관리합니다.

```python
class OrdinanceBuilderState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 누적 (add_messages reducer)
    user_input: str
    ordinance_info: dict          # region / purpose / target_group / support_type
    current_stage: Literal[...]   # 10개 단계
    missing_fields: list[str]
    interview_turn_count: int
    max_interview_turns: int      # default: 5

    # 조항 인터뷰
    article_queue: list[str]      # 미처리 조항 목록
    current_article_key: str
    article_contents: dict        # {조항키: 사용자입력 | None}

    # DB 검색 결과
    legal_basis: list[dict]       # 상위법 조항
    similar_ordinances: list[dict]
    article_examples: list[dict]

    # 초안
    draft_articles: list[dict]    # [{"article_no", "title", "content"}]
    draft_full_text: str
    draft_review_decision: Optional[Literal["confirm", "revise"]]

    # 법률 검증
    legal_issues: list[dict]      # [{"severity", "description", "suggestion"}]
    is_legally_valid: Optional[bool]
    response_to_user: str
```

> **핵심 설계**: `messages`만 `add_messages` 리듀서로 누적하고, 나머지 필드는 덮어쓰기로 처리합니다. 인터뷰 루프는 LangGraph의 `interrupt` 없이, `/chat` 요청마다 그래프 진입점으로 재진입하는 방식을 사용합니다.

### 노드별 역할

| 노드 | LLM | 기능 | 출력 |
|------|-----|------|------|
| `intent_analyzer` | Gemini 2.5 Pro | 자연어 입력 → 필드 추출 (`ExtractedInfo` 구조화 출력) | `ordinance_info`, `missing_fields` |
| `interviewer` | 없음 | 미수집 필드 질문 생성 (최대 2개씩) | `response_to_user` |
| `graph_retriever` | 없음 | Neo4j 쿼리: 상위법 + 유사조례 + 조문 예시 | `legal_basis`, `similar_ordinances` |
| `article_planner` | 없음 | 9개 조항 순서 정의 + 첫 질문 | `article_queue` |
| `article_interviewer` | 없음 | 조항별 답변 수집, "기본값" → None 처리 | `article_contents`, `current_stage` |
| `drafting_agent` | Claude Opus 4.6 | 조례 초안 생성 (`OrdinanceDraft`) | `draft_full_text` |
| `draft_reviewer` | Claude Opus 4.6 | 피드백 분류 + 수정 적용 | `draft_review_decision` |
| `legal_checker` | GPT-4o | 상위법 충돌 검증 (`LegalCheckResult`) | `legal_issues`, `is_legally_valid` |

### 조건부 분기 (edges/conditions.py)

```
route_at_start(state) →
  "legal_review_requested"              # draft_text와 함께 POST된 경우
  "draft_review"                        # 사용자가 초안 검토 요청
  "article_interviewing"                # 조항 Q&A 진행 중 (chat 경로)
  "article_complete" (→ article_interviewer) # 모달 일괄 제출 (articles_batch 경로)
  "default"                             # intent_analyzer로 진입

after_intent_analyzer(state) →
  "interviewer"   # missing_fields 존재
  "graph_retriever"  # 정보 완비

after_graph_retriever(state) →
  "article_planner"   # article_queue가 없으면 새로 계획
  "drafting_agent"    # 이미 queue 있으면 생성

after_article_interviewer(state) →
  "drafting_agent"  # 모든 조항 완료 (current_stage == "article_complete")
  END               # 다음 조항 질문 (다음 /chat 대기)

after_draft_reviewer(state) →
  "legal_checker"  # confirm
  END              # revise (수정된 초안 반환)
```

> **⚠️ 라우팅 불변 조건**: `route_at_start`는 백엔드 엔드포인트가 주입할 수 있는 **모든 `current_stage` 값을 명시적으로 처리**해야 합니다.
>
> `/articles_batch` 엔드포인트는 `current_stage = "article_complete"`를 주입합니다.
> 이 값을 처리하지 않으면 `intent_analyzer`(default)로 빠지고, Gemini가 `missing_fields != []`를
> 반환할 경우 `interviewer → END`로 흘러 **초안 생성에 도달하지 못하고 모달이 열리지 않습니다.**
>
> **새로운 엔드포인트나 스테이지를 추가할 때는 반드시 `route_at_start`에 해당 case를 추가하세요.**

---

## OWL 온톨로지 설계

법령 도메인의 개념 체계를 **Protégé**로 모델링한 OWL 온톨로지(`ordinance.rdf`)입니다. Neo4j 그래프 스키마의 개념적 기반이 되며, Phase 3에서 SWRL 논리 규칙 추론에 활용.

### 클래스 계층 구조

```
Thing
├── 법규범
│   ├── 상위법률                  ← 헌법·법률·시행령
│   └── 자치법규
│       ├── 조례                  ← 지방의회 제정
│       └── 규칙                  ← 지자체장 제정
│
├── 조문구조
│   └── 장(章)
│       └── 조(條)
│           └── 항(項)
│               └── 호(號)
│                   └── 목(目)   ← 최소 조문 단위
│
└── 법적개념
    ├── 권리주체                  ← 행위의 주체 (개인·법인·기관)
    ├── 법적행위                  ← 보조금 지급, 신청, 제재 등
    └── 객체                      ← 행위의 대상
```

### 객체 속성 (Object Properties)

| 속성 | 도메인 | 범위 | 설명 |
|------|--------|------|------|
| `위임하다` | 상위법률 | 조례 | 상위법이 조례 제정을 위임 |
| `위임근거를_가지다` | 조례 | 상위법률 | 조례가 보유한 위임 근거 |
| `상충하다` | 조례 | 상위법률 | 조례가 상위법과 충돌 |
| `준용하다` | 조례 | 상위법률 | 조례가 상위법을 준용 |
| `포함하다` | 조문구조 | 조문구조 | 장→조→항→호→목 계층 포함 관계 |
| `정의하다` | 조문구조 | 법적개념 | 조문이 법적 개념을 정의 |
| `수행주체이다` | 법적행위 | 권리주체 | 특정 행위의 권리 주체 |

### 데이터 속성 (Data Properties)

| 속성 | 타입 | 설명 |
|------|------|------|
| `조문번호` | `xsd:integer` | 조문의 일련번호 |
| `조문제목` | `xsd:string` | 조문의 표제 |
| `조문` | `xsd:string` | 조문 본문 텍스트 |
| `법적효력일` | `xsd:dateTime` | 시행 일자 |

### Neo4j 스키마와의 매핑

OWL 클래스와 속성은 Neo4j 그래프 노드·관계로 다음과 같이 대응됩니다:

| OWL 개념 | Neo4j 노드/관계 |
|----------|----------------|
| `상위법률` | `:Statute` 노드 |
| `조례` | `:Ordinance` 노드 |
| `조(條)` | `:Provision` 노드 |
| `항/호/목` | `:Paragraph` / `:Item` / `:SubItem` 노드 |
| `법적개념` | `:LegalTerm` 노드 |
| `위임하다` | `DELEGATES` 관계 |
| `위임근거를_가지다` | `BASED_ON` 관계 |
| `상충하다` | `CONFLICTS_WITH` 관계 |
| `포함하다` | `CONTAINS` 관계 |
| `정의하다` | `DEFINES` 관계 |

---

## 데이터베이스 스키마

### Neo4j 노드

| 레이블 | 주요 속성 | 설명 |
|--------|-----------|------|
| `Statute` | `id`, `title`, `category`, `enforcement_date`, `embedding` | 상위 법령 |
| `Provision` | `id`, `article_no`, `content_text`, `is_penalty_clause`, `embedding` | 법령 개별 조문 |
| `Ordinance` | `id`, `region_name`, `title`, `enforcement_date`, `embedding` | 지자체 조례 |
| `LegalTerm` | `term_name`, `definition`, `synonyms` | 핵심 법률 용어 |
| `Paragraph` | `id`, `content_text` | 조문의 항(項) |
| `Item` | `id`, `content_text` | 조문의 호(號) |
| `SubItem` | `id`, `content_text` | 조문의 목(目) |

### 관계 타입

| 타입 | 방향 | 설명 |
|------|------|------|
| `CONTAINS` | `Statute → Provision` | 법령 → 세부 조문 |
| `BASED_ON` | `Ordinance → Statute` | 조례의 법령 근거 |
| `DELEGATES` | `Statute → Ordinance` | 위임 관계 (우선 탐색) |
| `SUPERIOR_TO` | `Statute → Ordinance` | 법적 위계질서 |
| `SIMILAR_TO` | `Ordinance ↔ Ordinance` | 지자체 간 유사 조례 |
| `LIMITS` | `Provision → LegalTerm` | 조항의 행위 제한 범위 |
| `CONFLICTS_WITH` | `Ordinance → Statute` | 충돌 관계 |
| `REFERENCES` | `Provision → Provision` | 조문 간 인용 |
| `DEFINES` | `Statute → LegalTerm` | 법령이 정의하는 용어 |

### 벡터 인덱스

```cypher
CREATE VECTOR INDEX idx_provision_embedding
  FOR (p:Provision) ON p.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}

CREATE VECTOR INDEX idx_ordinance_embedding
  FOR (o:Ordinance) ON o.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
```

임베딩 모델: `models/gemini-embedding-001` (3072차원)

---

## ETL 파이프라인

국가법령정보센터 Open API에서 데이터를 수집해 Neo4j에 적재하는 독립 모듈입니다.

### 파이프라인 구성

```
LawApiClient (XML 파싱)
    ↓
SchemaMapper (API 응답 → Node 객체)
    ↓
Neo4jLoader (MERGE + 관계 구축 + 벡터 임베딩)
```

### 초기 적재 4단계 (initial_load.py)

```
Phase 1: mandatory_statutes 6개 법령 강제 적재
         (지방자치법, 청년기본법, 보조금 관리법 등)

Phase 2: domain_keywords 기반 법령 검색 및 적재
         키워드: 청년, 창업, 기업지원, 소상공인, 중소기업 등

Phase 3: domain_keywords 기반 조례 검색 및 적재
         전국 지자체 조례 수집

Phase 4: 노드 간 관계 구축
         BASED_ON, SUPERIOR_TO, SIMILAR_TO, DELEGATES 등
         + 전체 Provision 노드 벡터 임베딩 생성
```

### 변경 감지 (change_detector.py)

`enforcement_date` 비교로 개정 여부를 판단하며, 현행 버전만 유지하는 방식으로 증분 업데이트를 처리합니다.

---

## 프로젝트 구조

```
Ordinance_Builder/
├── app/                                # FastAPI + LangGraph 애플리케이션
│   ├── main.py                         # FastAPI 진입점 (lifespan 훅)
│   ├── api/
│   │   ├── schemas.py                  # Pydantic 요청/응답 모델
│   │   └── routers/
│   │       ├── chat.py                 # POST /api/v1/session, /chat, /finalize; DELETE /api/v1/session/{id}
│   │       └── debug.py                # 디버그 엔드포인트
│   ├── core/
│   │   ├── config.py                   # 환경 변수 설정 (pydantic-settings) — LLM_* 노드별 provider 포함
│   │   ├── llm.py                      # provider별 캐싱 팩토리 get_llm(provider) — Gemini/OpenAI/Anthropic
│   │   └── embedder.py                 # Gemini 임베딩 클라이언트 (Neo4j 벡터 인덱스 고정)
│   ├── db/
│   │   ├── base.py                     # GraphDBInterface (ABC)
│   │   ├── mock_db.py                  # MockGraphDB (개발/테스트용)
│   │   ├── neo4j_db.py                 # Neo4jGraphDB (프로덕션)
│   │   └── seed_data.py                # Mock 시드 데이터
│   ├── graph/
│   │   ├── state.py                    # OrdinanceBuilderState (TypedDict)
│   │   ├── workflow.py                 # LangGraph 그래프 조립 및 컴파일
│   │   ├── nodes/
│   │   │   ├── intent_analyzer.py      # 자연어 입력 → 필드 추출
│   │   │   ├── interviewer.py          # 누락 필드 반복 질문
│   │   │   ├── graph_retriever.py      # DB 법적 근거·유사 조례 검색
│   │   │   ├── article_planner.py      # 조항 구성 계획 (9개 템플릿)
│   │   │   ├── article_interviewer.py  # 조항별 세부 내용 Q&A
│   │   │   ├── drafting_agent.py       # 법적 조문 초안 생성
│   │   │   ├── draft_reviewer.py       # AI 자체 검토 및 수정
│   │   │   ├── legal_checker.py        # 상위법 충돌 검증
│   │   │   └── _article_examples.py   # 조항 예시 헬퍼
│   │   └── edges/
│   │       └── conditions.py           # 조건부 분기 함수 (5개)
│   └── prompts/                        # LLM 프롬프트 템플릿
│       ├── intent_analyzer.py
│       ├── drafting_agent.py
│       ├── draft_reviewer.py
│       └── legal_checker.py
│
├── pipeline/                           # 국가법령정보센터 → Neo4j ETL (독립 모듈)
│   ├── config.py                       # 도메인 키워드·필수 법령 설정
│   ├── api/
│   │   └── law_api_client.py           # Open API 호출 + XML 파싱
│   ├── transform/
│   │   └── schema_mapper.py            # API 응답 → Graph 스키마 변환
│   ├── loaders/
│   │   └── neo4j_loader.py             # Neo4j MERGE 적재 + 임베딩
│   ├── sync/
│   │   └── change_detector.py          # enforcement_date 비교로 개정 감지
│   └── scripts/
│       ├── initial_load.py             # 최초 전체 적재 (4단계)
│       ├── incremental_update.py       # 주기적 증분 업데이트
│       └── migrate_schema.py           # 스키마 마이그레이션
│
├── frontend/                           # React 18 + TypeScript (Vite)
│   └── src/
│       ├── App.tsx                     # 메인 앱 (상태 관리, 탭 전환)
│       ├── api.ts                      # FastAPI 연동 클라이언트
│       ├── types.ts                    # TypeScript 타입 정의
│       └── components/
│           ├── ChatWindow.tsx          # 메시지 목록 + 입력 필드
│           ├── MessageBubble.tsx       # 개별 메시지 버블
│           ├── StageIndicator.tsx      # 진행 단계 표시
│           ├── DraftModal.tsx          # 초안 편집 + 검증 모달
│           ├── DraftPanel.tsx          # 확정 초안 표시
│           ├── LegalIssuesPanel.tsx    # 법률 이슈 목록 (severity 색상 코딩)
│           └── SimilarOrdinancesPanel.tsx # 유사 조례 참고
│
├── docker-compose.yml                  # Neo4j + Backend + Frontend
├── Dockerfile                          # Backend 이미지
├── requirements.txt                    # Python 의존성
├── ordinance.rdf                       # OWL 온톨로지 (선택)
└── .env.example                        # 환경 변수 템플릿
```

---

## 로컬 개발 환경 설정

### 필수 환경변수 체크리스트

`.env.example`을 복사하여 `.env`를 생성할 때, **아래 변수가 모두 채워져 있는지 반드시 확인**하세요.

| 변수 | 역할 | 누락 시 증상 |
|------|------|-------------|
| `GOOGLE_API_KEY` | Gemini LLM / Embedding | `intent_analyzer` 실패 |
| `ANTHROPIC_API_KEY` | Claude (초안 생성·검토) | `drafting_agent` / `draft_reviewer` 실패 |
| `OPENAI_API_KEY` | GPT-4o (법률 검증) | `legal_checker` 실패 |
| `NEO4J_URI` | Graph DB 연결 | `graph_retriever` 실패 |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 인증 | Graph DB 연결 실패 |
| **`POSTGRES_PASSWORD`** | **PostgreSQL 컨테이너 초기화 + 백엔드 URL** | **백엔드 시작 실패 → 502** |
| `POSTGRES_URL` | 로컬 직접 접속용 (docker-compose 미사용 시) | 세션 저장 실패 |
| `FIREBASE_CREDENTIALS_PATH` | 서버사이드 Firebase 인증 | 인증 미들웨어 실패 |

> **주의**: `POSTGRES_PASSWORD`는 `docker-compose.yml`에서 두 곳에 사용됩니다.
> 1. `postgres` 서비스 초기화: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`
> 2. `backend` 서비스 URL: `postgresql://app_user:${POSTGRES_PASSWORD}@postgres:5432/ordinance_builder`
>
> 이 값이 없으면 PostgreSQL은 패스워드 없이 초기화되지만, 네트워크 연결 시 인증이 거부되어
> `fe_sendauth: no password supplied` 에러와 함께 백엔드 컨테이너가 즉시 종료됩니다.

### Docker Compose 시작 순서

```bash
# 1. .env 파일 생성 (모든 필수 변수 채우기)
cp .env.example .env
# .env 파일을 열어 실제 값으로 채움

# 2. 전체 스택 시작 (의존성 순서: postgres/neo4j → backend → frontend)
docker compose up -d

# 3. 백엔드 로그 확인 (정상: "Application startup complete")
docker logs ordinance_builder-backend-1 -f
```

### 백엔드 502 에러 진단 절차

```bash
# 1. 컨테이너 상태 확인
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 2. 백엔드가 Exited 상태라면 로그 확인
docker logs ordinance_builder-backend-1

# 3. PostgreSQL 비밀번호 문제라면 볼륨 재생성
docker compose down postgres --volumes
docker compose up -d postgres
# postgres healthy 확인 후
docker compose up -d backend
```

### 모달이 열리지 않을 때 진단 절차

초안 생성(DraftModal)이나 조항 입력(ArticleItemsModal)이 열리지 않을 때:

```bash
# 1. 브라우저 개발자 도구 → Network 탭에서 실패한 요청 확인
#    - /articles_batch → 500이면 백엔드 LLM 호출 오류
#    - /chat           → 500이면 그래프 노드 실행 오류

# 2. 백엔드 로그에서 실제 예외 확인
docker logs ordinance_builder-backend-1 --tail 50
```

응답이 200이지만 모달이 안 열리는 경우 → 응답 JSON의 `stage`와 `draft` 필드를 확인하세요.
- `DraftModal`: `stage === "draft_review"` **AND** `draft !== ""` 이어야 열림
- `ArticleItemsModal`: `stage === "article_interviewing"` **AND** `current_article_key !== null` 이어야 열림

---

## 개발 시 주의사항

### 1. `route_at_start` 완전성 원칙

**새로운 엔드포인트나 스테이지를 추가할 때 반드시 `route_at_start`를 업데이트하세요.**

```python
# app/graph/edges/conditions.py
def route_at_start(state) -> RouteAtStart:
    current_stage = state.get("current_stage") or "intent_analysis"
    # ↓ 백엔드에서 주입 가능한 모든 stage를 명시적으로 처리해야 함
    if current_stage == "legal_review_requested": return "legal_checker"
    if current_stage == "draft_review":           return "draft_reviewer"
    if current_stage in ("article_interviewing", "article_complete"):
        return "article_interviewer"  # article_complete: 빈 queue 감지 → drafting_agent
    return "intent_analyzer"          # default: 미처리 stage는 의도치 않은 경로로 흐름
```

**위반 시 증상**: `/articles_batch` 제출 후 초안 모달이 열리지 않음.
원인: `"article_complete"` 미처리 → `intent_analyzer` fallback → Gemini가 `missing_fields != []` 반환 가능 → `interviewer → END` → 초안 생성 미도달.

### 2. 엔드포인트별 주입 스테이지 매핑

| 엔드포인트 | 주입하는 `current_stage` | `route_at_start` 처리 |
|-----------|--------------------------|----------------------|
| `POST /session` (initial_message 포함) | (주입 없음, 첫 실행) | `intent_analyzer`부터 실행 |
| `/chat` (일반) | (주입 없음, 체크포인트 값 유지) | 체크포인트 stage에 따라 분기 |
| `/chat` (draft_text 포함) | `"legal_review_requested"` | `legal_checker` |
| `/articles_batch` | `"article_complete"` | `article_interviewer` |
| `/finalize` | `graph.aupdate_state`로 `"completed"` 직접 설정 | 그래프 미경유 |
| `DELETE /session/{id}` | — (그래프 미경유) | PostgreSQL 레코드만 삭제 |

> **⚠️ `SessionCreateResponse` 필드 누락 주의**: 기본정보를 한 번에 입력하면 그래프가
> `article_planner`까지 실행되며 `article_queue`, `current_article_key`가 설정됩니다.
> 이 값이 `SessionCreateResponse`에 없으면 프론트엔드 조항 모달이 열리지 않습니다.
> **→ 자세한 원인·수정 위치는 개발 시 주의사항 §7 참조.**

### 3. 멀티 LLM 지원 — 노드별 provider 및 API 키

| 노드 | Provider | 환경변수 | 누락 시 증상 |
|------|----------|----------|-------------|
| `intent_analyzer` | Gemini 2.5 Pro | `GOOGLE_API_KEY` | 인터뷰 정보 추출 실패 |
| `drafting_agent` | Claude Opus 4.6 | `ANTHROPIC_API_KEY` | 초안 생성 실패, 모달 미표시 |
| `draft_reviewer` | Claude Opus 4.6 | `ANTHROPIC_API_KEY` | 초안 수정 검토 실패 |
| `legal_checker` | GPT-4o | `OPENAI_API_KEY` | 법률 검증 실패 |

LLM provider 변경은 `.env`의 `LLM_INTENT` / `LLM_DRAFTING` / `LLM_REVIEWER` / `LLM_LEGAL` 값으로 제어합니다. 허용값: `"gemini"` | `"openai"` | `"anthropic"`

### 4. 프론트엔드 모달 개방 조건

```typescript
// DraftModal이 열리는 유일한 조건 (App.tsx applyResponse)
if (res.stage === 'draft_review' && res.draft) {  // res.draft 빈 문자열도 미열림
    setIsDraftModalOpen(true)
}

// ArticleItemsModal이 열리는 유일한 조건
const isArticleModalOpen = stage === 'article_interviewing' && mappedArticles.length > 0
// mappedArticles = currentArticleKey ? [currentArticleKey, ...articleQueue] : []
// → currentArticleKey가 null이면 모달 미표시
```

### 5. Firebase 인증 — `signInWithPopup` 사용 금지

**`signInWithPopup` 대신 반드시 `signInWithRedirect`를 사용하세요.**

```
오류 메시지:
Cross-Origin-Opener-Policy policy would block the window.close call.
```

**원인**: 브라우저의 COOP(Cross-Origin-Opener-Policy) 정책이 팝업 창이 `window.close()`로
스스로 닫히는 것을 차단합니다. Firebase popup 인증은 팝업 닫기로 결과를 opener에게 전달하므로
인증 흐름이 완료되지 않습니다.

**올바른 구현** (`frontend/src/firebase.ts`):
```typescript
// ❌ 금지
import { signInWithPopup } from 'firebase/auth'
export const loginWithGoogle = () => signInWithPopup(auth, googleProvider)

// ✅ 사용
import { signInWithRedirect, getRedirectResult } from 'firebase/auth'
export const loginWithGoogle = () => signInWithRedirect(auth, googleProvider)
export { getRedirectResult }
```

**App.tsx `useEffect`에서 리디렉션 결과 처리**:
```typescript
useEffect(() => {
    // 리디렉션 후 돌아왔을 때 pending 결과 처리
    getRedirectResult(auth).catch((e) => console.error('redirect auth error:', e))

    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
        setUser(firebaseUser)
        setAuthLoading(false)
    })
    return unsubscribe
}, [])
```

**동작 차이**:
- `signInWithPopup`: 팝업 창 열림 → COOP 차단 → 인증 실패
- `signInWithRedirect`: 현재 탭이 Google로 이동 → 인증 → 앱으로 복귀 → `onAuthStateChanged` 자동 처리

### 6. 조항 수집 경로 — 점진적 입력 vs. 일괄 입력

조항을 하나씩 입력하면 DraftModal이 열리는데, ArticleItemsModal로 한 번에 제출하면 모달이 열리지 않는 경우의 원인과 올바른 흐름입니다.

| 경로 | 엔드포인트 | 주입 `current_stage` | 워크플로우 |
|------|-----------|----------------------|-----------|
| 점진적 (하나씩) | `/chat` | `"article_interviewing"` (체크포인트 유지) | `article_interviewer` → 큐 소진 → `drafting_agent` |
| 일괄 (ArticleItemsModal) | `/articles_batch` | `"article_complete"` + `article_queue=[]` | `article_interviewer` → 빈 큐 감지 → `drafting_agent` |

두 경로 모두 `article_interviewer`를 거칩니다. `article_interviewer`는 `article_queue`가 `[]`일 때 `current_stage = "article_complete"`를 설정하고, `route_after_article_interview`가 `drafting_agent`로 분기합니다.

**`route_at_start`에 `"article_complete"` 미처리 시 실제 발생 흐름:**
```
/articles_batch 제출 (article_queue=[], current_stage="article_complete")
→ route_at_start("article_complete") — 처리 케이스 없음
→ intent_analyzer (default fallback)
→ Gemini가 missing_fields != [] 반환 가능
→ interviewer → END
→ draft 미생성 → DraftModal 열리지 않음
```

**올바른 흐름 (현재 conditions.py):**
```
/articles_batch 제출
→ route_at_start("article_complete") → article_interviewer
→ 빈 큐 감지 → route_after_article_interview → drafting_agent
→ draft_full_text 생성 → stage="draft_review" → DraftModal 열림
```

> **체크리스트**: `/articles_batch`처럼 `article_queue=[]`를 주입하는 엔드포인트를 추가할 때는
> 반드시 `route_at_start`에 해당 stage 케이스를 추가하고, `article_interviewer`로 라우팅하세요.

### 7. 기본정보 한 번에 입력 시 — `SessionCreateResponse` 필드 누락

**증상**: 기본정보 4개를 첫 메시지에 한 번에 제공하면 조항 입력 모달·버튼이 안 뜸. 점진적으로 입력하면 정상.

**원인**:

첫 메시지는 `sessionIdRef.current == null` → `createSession(text)` 경로를 사용합니다.
이때 그래프가 `article_planner`까지 실행되어 `current_article_key`, `article_queue`를 설정하지만,
`SessionCreateResponse`에 이 필드가 없어 프론트엔드로 전달되지 않습니다.

```
첫 메시지 → createSession() → POST /api/v1/session
  → 그래프: intent_analyzer → graph_retriever → article_planner
  → article_planner: current_article_key="목적", article_queue=[...] 설정
  → SessionCreateResponse(session_id, message, stage) ← article 필드 없음!
  → applyResponse()에서 setCurrentArticleKey() 미호출
  → currentArticleKey = null → mappedArticles = [] → isArticleModalOpen = false
```

두 번째 이후 메시지는 `sendMessage()` → `/chat` → `ChatResponse` 경유므로 `article_queue`, `current_article_key`가 정상 포함됩니다.

**수정 위치 (세 군데)**:
1. `app/api/schemas.py` — `SessionCreateResponse`에 `article_queue`, `current_article_key` 추가
2. `app/api/routers/chat.py` — `create_session` 핸들러에서 `result.get()`으로 해당 값 반환
3. `frontend/src/types.ts` — `SessionCreateResponse` 인터페이스에 필드 추가

> **원칙**: `SessionCreateResponse`는 `ChatResponse`와 동일한 수준의 그래프 출력 필드를 포함해야 합니다.
> 새 그래프 노드를 추가하고 첫 메시지에서 도달 가능하다면, 두 응답 스키마를 동시에 업데이트하세요.

### 8. TypeScript `null` vs `undefined` — 백엔드 API 타입 일관성

**증상**: Docker 빌드 시 TypeScript 컴파일 오류:

```
Type 'string | null | undefined' is not assignable to type 'string | undefined'.
  Type 'null' is not assignable to type 'string | undefined'.
```

**원인**: Python `None` → JSON `null` → TypeScript `null`로 수신됩니다.
TypeScript 인터페이스나 함수 파라미터를 `T | undefined`로만 정의하면 `null`을 거부합니다.

```typescript
// ❌ 잘못된 타입 — Python None → JSON null이지만 TypeScript가 거부
current_article_key?: string           // string | undefined 만 허용

// ✅ 올바른 타입
current_article_key?: string | null    // string | null | undefined 모두 허용
```

**수정 위치**:
- `frontend/src/types.ts` — `null`을 반환할 수 있는 모든 필드에 `| null` 추가
  (`SessionCreateResponse`, `ChatResponse`, `SessionStateResponse`의 `current_article_key`)
- `frontend/src/App.tsx` — `applyResponse` 파라미터 타입 동기화

> **체크리스트**: 새 API 필드 추가 시 Python 백엔드에서 `None` 반환 가능 여부를 확인하고,
> TypeScript 인터페이스와 해당 필드를 사용하는 함수 파라미터 타입에 `| null`을 포함하세요.

---

## 기술 스택

| 계층 | 기술 | 역할 |
|------|------|------|
| **LLM (정보 추출)** | Gemini 2.5 Pro (`langchain-google-genai`) | `intent_analyzer` — 한국어 구조화 추출 |
| **LLM (초안 생성·검토)** | Claude Opus 4.6 (`langchain-anthropic`) | `drafting_agent`, `draft_reviewer` — 장문 법적 문서 작성·수정 |
| **LLM (법률 검증)** | GPT-4o (`langchain-openai`) | `legal_checker` — 비판적 법률 분석·충돌 검증 |
| **Embedding** | `models/gemini-embedding-001` (3072d) | 조문 의미 검색 (Neo4j 벡터 인덱스 고정) |
| **Orchestration** | LangGraph + LangChain | 상태 기반 멀티노드 워크플로우 |
| **Backend** | FastAPI + Uvicorn | REST API 서버 |
| **Frontend** | React 18 + TypeScript + Vite | 대화형 UI |
| **Graph DB** | Neo4j 5.23 (Docker) → Neo4j AuraDB (프로덕션) | 법령 관계 그래프 |
| **ETL** | 국가법령정보센터 Open API + 자체 파이프라인 | 법령·조례 데이터 수집 |
| **배포** | Docker Compose (로컬) / Cloud Functions + AuraDB (예정) | 컨테이너 기반 배포 |
