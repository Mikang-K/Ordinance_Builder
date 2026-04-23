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

### 10. 세션 복원 시 article_queue / current_article_key 누락

**증상**: `article_interviewing` 단계에서 "목록" 버튼으로 나갔다가 같은 세션을 다시 선택하면 상세 조항 작성 모달과 "상세 조항 계속 작성하기" 버튼이 사라짐.

**원인**:

`GET /api/v1/session/{id}` (`get_session_state`) 핸들러가 `SessionStateResponse`를 생성할 때
`article_queue`와 `current_article_key`를 그래프 state에서 꺼내 포함하지 않았음.

```
목록 클릭 → handleReset() → resetState()
  → currentArticleKey = null, articleQueue = [], stage = null

세션 재선택 → handleSelectSession() → GET /api/v1/session/{id}
  → SessionStateResponse에 article_queue, current_article_key 없음 (undefined 반환)
  → if (state.article_queue !== undefined) 조건 false → setArticleQueue() 미호출
  → currentArticleKey = null → mappedArticles = [] → isArticleModalOpen = false
```

**수정 위치 (두 곳)**:

1. `app/api/routers/chat.py` — `get_session_state` 핸들러 `SessionStateResponse(...)` 생성 시 추가:
   ```python
   article_queue=values.get("article_queue"),
   current_article_key=values.get("current_article_key"),
   ```

2. `frontend/src/App.tsx` — `handleSelectSession` null 가드 수정:
   ```typescript
   // ❌ null !== undefined → true → setArticleQueue(null) TypeScript 오류
   if (state.article_queue !== undefined) setArticleQueue(state.article_queue)

   // ✅ null과 undefined 모두 스킵 (loose inequality)
   if (state.article_queue != null) setArticleQueue(state.article_queue)
   ```

   `current_article_key`는 `string | null`을 허용하는 타입이므로 변경 불필요.

3. `frontend/src/types.ts` — `SessionStateResponse.article_queue` 타입 보완:
   ```typescript
   article_queue?: string[] | null   // Python None → JSON null 허용
   ```

**패턴**: 백엔드 그래프 state에서 읽는 필드를 새로 추가할 때는 `get_session_state` 핸들러도 함께 업데이트하세요. `ChatResponse`와 `SessionStateResponse`는 동일한 수준의 필드를 반환해야 합니다.

---

### 9. TypeScript 컴파일 오류 — firebase 패키지 미설치

**증상**: `npx tsc --noEmit` 실행 시 아래 4개 오류가 함께 발생:

```
src/firebase.ts: Cannot find module 'firebase/app' or its corresponding type declarations.
src/firebase.ts: Cannot find module 'firebase/auth' or its corresponding type declarations.
src/App.tsx: Parameter 'e' implicitly has an 'any' type.
src/App.tsx: Parameter 'firebaseUser' implicitly has an 'any' type.
```

**원인**: `package.json`에 `"firebase": "^10.14.0"`이 선언돼 있지만 `node_modules/firebase`가 존재하지 않는 상태. firebase 타입이 없으면 콜백 파라미터 타입도 추론되지 않아 implicit `any` 오류가 연쇄 발생.

**해결**:

```bash
cd frontend
npm install firebase
```

> **체크리스트**: 새 개발 환경 세팅 또는 `node_modules` 초기화 후 반드시 `npm install` 실행. TypeScript 오류가 특정 npm 패키지 경로를 가리키면 해당 패키지 설치 여부를 먼저 확인.

### 10. 유사 조례 원문 링크 — law.go.kr 검색 URL (Phase 1)

유사 조례 목록에 국가법령정보센터 원문 링크를 달아 새 탭에서 열 수 있도록 구현합니다.

**표시 위치 (2곳):**

| 위치 | 컴포넌트 | 표시 방식 |
|------|----------|-----------|
| 채팅창 하단 유사 조례 패널 | `SimilarOrdinancesPanel.tsx` | 각 조례 제목 옆 "원문 보기 ↗" 링크 버튼 |
| 조례 상세 조항 설정 모달 — 진행 목차 아래 | `ArticleItemsModal.tsx` (스크롤 영역) | 최대 3건, "원문 ↗" 링크 |

**`ArticleItemsModal.tsx` 사이드바 구조:**

```
사이드바 (flex column)
├── 스크롤 영역 (flex: 1, overflowY: auto)
│   ├── 진행 목차
│   └── 유사 조례 (최대 3건 + 원문 ↗ 링크)   ← 스크롤 영역
└── 가이드 패널 (#fffbeb, overflowY: auto, maxHeight: 280px)
    ├── 💡 작성 가이드 (hint)
    └── 예시 텍스트 (있는 경우)
```

**가이드 패널 `maxHeight: 280px` 이유**: 패널이 무한히 늘어나면 스크롤 영역(진행 목차)이 밀려 조항 이동이 어려워지므로 상한 지정 후 내부 스크롤 처리.

> **주의**: 가이드 패널(노란 영역) 안에는 유사 조례를 표시하지 않습니다. 유사 조례는 스크롤 영역(진행 목차 아래)에만 표시합니다. 가이드 패널에 유사 조례를 추가하면 배포 빌드를 재생성해야 하므로 주의가 필요합니다.

**데이터 연결 (`App.tsx`):**

```typescript
// ArticleItemsModal에 similarOrdinances 전달 (optional prop, 기본값 [])
<ArticleItemsModal
  similarOrdinances={similarOrdinances}  // App.tsx 상태
  ...
/>
```

**URL 구성 방식 (검색 URL):**

```typescript
`https://www.law.go.kr/ordinSc.do?query=${encodeURIComponent(title)}`
// target="_blank" rel="noopener noreferrer" 로 새 탭에서 열기
```

**한계점 및 Phase 2 업그레이드 계획:**
- Phase 1은 제목 기반 **검색 결과 페이지**로 링크 — 직접 원문이 아님
- Phase 2: `pipeline/transform/schema_mapper.py`에서 API 응답의 `ordinSeq`를 추출해 Neo4j에 `source_url` 저장 → `https://www.law.go.kr/ordinInfoP.do?ordinSeq={ordinSeq}` 직접 링크

---

### 11. 로딩 모달 — `LoadingModal.tsx`

API 호출 중 화면 중앙에 오버레이 모달을 표시합니다.

**구성 요소:**
- `frontend/src/components/LoadingModal.tsx` — 모달 컴포넌트
- `frontend/src/App.css` — `.loading-modal-*` CSS 블록 (애니메이션 포함)
- `frontend/src/App.tsx` — `loadingMessage` 상태 + `<LoadingModal>` 렌더링

**렌더링 조건**: `isLoading && loadingMessage` 동시 충족 시 표시 (z-index: 200, 모든 모달 위)

**핸들러별 메시지:**

| 핸들러 | 메시지 |
|--------|--------|
| `handleSend` (첫 세션) | "기본 정보를 분석하고 있습니다..." |
| `handleSend` (일반) | "AI가 응답을 준비 중입니다..." |
| `handleLegalReview` | "법률 조항을 검증하고 있습니다..." |
| `handleFinalize` | "조례 초안을 확정하는 중입니다..." |
| `handleArticlesSubmit` | "조례 초안을 생성하고 있습니다..." |

**애니메이션:**
- 바깥 링: 시계 방향 회전 (`spinCw`, 1.8s)
- 안쪽 링: 반시계 방향 회전 (`spinCcw`, 1.2s)
- 중앙 ⚖️ 아이콘: 위아래 부유 (`floatUpDown`, 2s)
- 카드 진입: scale + fade-in (`loadingModalIn`, 0.22s)

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

---

## 배포 시 주의사항

### 12. AuraDB 배포 — Provision 임베딩 제외 필수

**배경**: 로컬 Neo4j 덤프가 15GB에 달해 AuraDB Professional 기본 플랜(8GB) 초과.

**원인 분석**:
- Provision 노드 316,943개 × 3072차원 임베딩 × 8B ≈ **7.8GB** (전체의 90%)
- Ordinance 노드 20,888개 × 3072차원 × 8B ≈ 0.5GB

**해결**: ETL 파이프라인 실행 시 `SKIP_PROVISION_EMBEDDING=true` 환경변수로 Phase 5를 건너뜀.

```bash
# AuraDB 대상 ETL 실행 명령 (반드시 이 플래그 포함)
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
NEO4J_PASSWORD="<auradb-password>" \
SKIP_PROVISION_EMBEDDING=true \
python -m pipeline.scripts.initial_load
```

**영향 범위**: `find_legal_basis()`의 **4순위 fallback**(Provision 벡터 검색)만 비활성화.
1~3순위(DELEGATES 탐색 → BASED_ON 탐색 → 키워드 검색)는 정상 동작.
`try/except`로 감싸져 있어 앱 오류 없이 빈 결과 반환.

**수정 파일**: `pipeline/scripts/initial_load.py` — `SKIP_PROVISION_EMBEDDING` 환경변수 분기 추가 (2026-04-17)

---

### 13. GCP 프로젝트 ID

Firebase 프로젝트 ID(`ordinance-builder`)와 실제 GCP 프로젝트 ID가 다름.

| 항목 | 값 |
|------|---|
| Firebase 프로젝트 ID | `ordinance-builder` |
| **실제 GCP 프로젝트 ID** | **`ordinance-builder-b9f6c`** |
| AuraDB URI | `neo4j+s://da425acb.databases.neo4j.io` |

gcloud 명령 실행 시 반드시 `ordinance-builder-b9f6c` 사용:
```bash
gcloud config set project ordinance-builder-b9f6c
```

---

### 14. `CORS_ORIGINS` 환경변수 파싱 오류 — Cloud Run 배포 시

**증상**: Cloud Run 컨테이너 시작 실패 → 503:

```
pydantic_settings.exceptions.SettingsError: error parsing value for field "CORS_ORIGINS" from source "EnvSettingsSource"
```

**원인**: pydantic-settings v2는 `list[str]` 필드에 JSON 배열 형식(`["url"]`)을 요구하는데,
Cloud Run `--set-env-vars`로 `CORS_ORIGINS=https://...` (plain string)을 주입하면 파싱 실패.

**근본 원인**: pydantic-settings v2의 `EnvSettingsSource.decode_complex_value`가 `list[str]` 필드에 대해 `field_validator` 실행 전에 `json.loads(value)`를 먼저 호출함.
환경변수 값이 빈 문자열(`""`)이면 `json.loads("")` → `JSONDecodeError` 발생.

**최종 수정** (`app/core/config.py` + `app/main.py`):
- `CORS_ORIGINS` 타입을 `list[str]` → `str`으로 변경해 pydantic-settings의 JSON 디코딩 우회
- 파싱은 `main.py`에서 직접 처리:

```python
# config.py
CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

# main.py
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, ...)
```

Cloud Run 환경변수 설정:
```
CORS_ORIGINS=https://ordinance-builder-b9f6c.web.app
```

**수정 파일**: `app/core/config.py`, `app/main.py` (2026-04-18)

### 15. Claude 4.x — `temperature` 파라미터 deprecated

**증상**: `drafting_agent` / `draft_reviewer` 실행 시 500 오류:

```
anthropic.BadRequestError: 400 - `temperature` is deprecated for this model.
```

**원인**: `claude-opus-4-7` 이상 Claude 4.x 모델은 `temperature` 파라미터를 허용하지 않음.

**수정** (`app/core/llm.py`): `ChatAnthropic` 생성자에서 `temperature=0.2` 제거.

**수정 파일**: `app/core/llm.py` (2026-04-18)

---

## 테스트 환경

**모든 테스트는 배포 환경(Firebase Hosting + Cloud Run)에서 진행한다.**

- Docker Compose 로컬 환경이 아닌, `https://ordinance-builder-b9f6c.web.app` 기준으로 검증
- 오류 확인: GCP 콘솔 → Cloud Run → `ordinance-backend` → 로그 탭
- 빠른 로그 조회:
  ```bash
  gcloud logging read \
    'resource.type="cloud_run_revision" severity>=ERROR' \
    --project=ordinance-builder-b9f6c \
    --limit=20
  ```
- 코드 수정 후 반드시 Cloud Build + `gcloud run deploy`로 재배포 후 테스트

---

### 16. GraphRAG 기반 Q&A 기능 (QAPanel)

워크플로우 진행 단계와 무관하게 언제든 법령·조례 질의응답이 가능한 슬라이딩 패널 기능을 추가.

**구현 파일 요약:**

| 파일 | 변경 내용 |
|------|-----------|
| `app/api/schemas.py` | `QASource`, `QARequest`, `QAResponse` Pydantic 모델 추가 |
| `app/prompts/qa_agent.py` | `QAOutput` 구조화 출력 모델 + `QA_SYSTEM` 프롬프트 + `build_qa_human()` RAG 컨텍스트 빌더 (신규) |
| `app/graph/workflow.py` | `_db_instance` 전역 + `get_db()` 싱글톤 노출 (QA 엔드포인트가 읽기 전용으로 DB 공유) |
| `app/api/routers/chat.py` | `POST /session/{id}/qa` 엔드포인트: GraphRAG 검색 + LLM 구조화 출력 |
| `frontend/src/types.ts` | `QASource`, `QAMessage`, `QAResponse` 인터페이스 추가 |
| `frontend/src/api.ts` | `askQuestion()` 함수 추가 |
| `frontend/src/components/QAPanel.tsx` | 오른쪽 슬라이딩 패널 컴포넌트 (신규) |
| `frontend/src/App.tsx` | `isQAPanelOpen`, `qaHistory`, `pendingQAContent` 상태 + QAPanel 렌더링 + 입력창에 "질문" 버튼 |
| `frontend/src/components/ArticleItemsModal.tsx` | `pendingQAContent` pre-fill `useEffect` + "질문하기" 버튼 추가 |

**GraphRAG 검색 4단계 fallback (chat.py `qa_chat`):**
1. DELEGATES 탐색 — 상위법이 위임한 조례 영역
2. BASED_ON 탐색 — 기존 조례의 법령 근거
3. 키워드 검색 (질문 단어 + 조례 기본정보)
4. `find_article_examples()` — `article_interviewing` 단계일 때 현재 조항 예시 (체크포인트 캐시 재사용)

**`applicable_content` 적용 흐름:**
```
QAPanel에서 "현재 조항에 적용하기" 클릭
→ App.tsx onApplyContent: pendingQAContent 설정 + QAPanel 닫기 + 모달 열기
→ ArticleItemsModal useEffect: 현재 조항 textarea에 pre-fill (confirm 다이얼로그)
→ onQAContentApplied 콜백으로 pendingQAContent 초기화
```

**z-index 계층:**
- LoadingModal: 200
- QAPanel: 150 (backdrop: 149)
- DraftModal / ArticleItemsModal: 100

**주의사항:**
- QA 엔드포인트는 LangGraph 체크포인트를 **읽기 전용**으로만 접근 (`graph.aget_state`) — 워크플로우 상태 변경 없음
- `applicable_content` 적용 버튼은 `stage === 'article_interviewing'` AND `applicable_article_key === currentArticleKey` 일치 시에만 표시
- `정의` 조항은 구조화 입력(term/desc 쌍)을 사용하므로 pre-fill 적용 제외 (confirm 단계에서 조항 키 확인 후 처리)

---

### 17. "🔍 질문" 버튼 — 헤더 상단 고정 배치 + 세션 기반 활성화

**경위**:
1. 초기 구현: 입력창 영역에 `{sessionIdRef.current && <button>}` 조건으로 배치
2. 문제: `useRef`는 `.current` 변경 시 리렌더링 미발생 → 버튼이 세션 생성 후에도 표시 안 됨
3. 1차 수정: `hasSession` useState 추가로 임시 해결
4. 2차 수정: 버튼을 헤더 `header-actions`로 이동 + 조건 제거 (항상 표시, `hasSession` 제거)
5. 2차 수정: `hasSession` state 재도입 — 버튼은 항상 표시하되, 세션이 없으면 `disabled` 처리
6. **최종 수정**: 버튼을 세션 없을 때 완전히 숨김 (`{hasSession && <button>}`)

**최종 구현** (`frontend/src/App.tsx`):

```typescript
// hasSession state — 세션 생성/복원 시 true, resetState 시 false
const [hasSession, setHasSession] = useState(false)

// 헤더 버튼 — 세션 있을 때만 렌더링
{hasSession && (
  <button
    onClick={() => setIsQAPanelOpen(true)}
    title="법령 Q&A 패널 열기"
    style={{ background: '#0f766e', ... }}
  >
    🔍 질문
  </button>
)}
```

**원칙**: `useRef.current`는 렌더링 사이클 밖의 값 보관용. UI 조건 렌더링에는 별도 `useState` 필요.

**수정 파일**: `frontend/src/App.tsx` — 질문 버튼 세션 없을 때 완전히 숨김 (2026-04-20)

---

### 18. Firebase 인증 — `signInWithRedirect` 적용 완료 (2026-04-21)

**수정 파일**: `frontend/src/firebase.ts`, `frontend/src/App.tsx`

CLAUDE.md §5에 기록된 금지 사항대로 `signInWithPopup` → `signInWithRedirect`로 전환.
`getRedirectResult`를 export하고, `App.tsx`의 인증 `useEffect` 상단에서 호출.

```typescript
// firebase.ts
export const loginWithGoogle = () => signInWithRedirect(auth, googleProvider)
export { onAuthStateChanged, getRedirectResult }

// App.tsx useEffect
getRedirectResult(auth).catch((e) => console.error('redirect auth error:', e))
```

**체크리스트**: `signInWithPopup`은 절대 사용하지 말 것. 새 Firebase Auth 코드 작성 시 §5 참조.

---

### 19. PostgreSQL 커넥션 풀 도입 (2026-04-21)

**수정 파일**: `app/db/session_store.py`, `app/main.py`, `requirements.txt`

**문제**: 모든 DB 함수가 `psycopg.AsyncConnection.connect()`를 요청마다 새로 호출 → Cloud Run 부하 시 503 위험.

**해결**: `psycopg-pool` 패키지의 `AsyncConnectionPool`을 도입. `init_db()`에서 풀 생성, `close_db()`에서 정리.

```python
# session_store.py
_pool: AsyncConnectionPool | None = None

async def init_db() -> None:
    global _pool
    _pool = AsyncConnectionPool(settings.POSTGRES_URL, min_size=2, max_size=10, open=False)
    await _pool.open()
    ...

async def close_db() -> None:
    if _pool: await _pool.close()
```

```python
# main.py lifespan
await init_db()
try:
    yield
finally:
    await close_db()
```

**체크리스트**: 새 DB 함수 작성 시 `_pool.connection()` 컨텍스트 사용. `dict_row`가 필요한 SELECT는 `conn.cursor(row_factory=dict_row)` 사용.

---

### 20. LangGraph 노드 async 전환 (2026-04-21)

**수정 파일**: `app/graph/nodes/intent_analyzer.py`, `drafting_agent.py`, `draft_reviewer.py`, `legal_checker.py`

**문제**: LLM 호출 노드 4개가 `def` + `llm.invoke()` (동기) 사용 → FastAPI async 워커를 LLM 응답 대기 시간(수십 초) 동안 완전 블로킹 → 동시 요청 처리 불가.

**해결**: 4개 노드 모두 `async def`로 변환 + `await llm.ainvoke()` 사용.

```python
# Before
def intent_analyzer_node(...): extracted = structured_llm.invoke(messages)
# After
async def intent_analyzer_node(...): extracted = await structured_llm.ainvoke(messages)
```

**영향 없는 노드** (LLM 미사용, sync 유지): `graph_retriever`, `article_planner`, `article_interviewer`, `interviewer`

**체크리스트**: 새 LLM 호출 노드는 반드시 `async def` + `await llm.ainvoke()` 패턴 사용. `langchain_anthropic`, `langchain_openai`, `langchain_google_genai` 모두 `ainvoke` 지원.

---

### 21. Google 로그인 — 인앱 브라우저 차단 (`disallowed_useragent`) (2026-04-23)

**증상**: 카카오톡·라인·네이버·인스타그램 등 앱에서 링크를 열고 Google 로그인 시도 시:

```
403 오류: disallowed_useragent
액세스 차단됨: ordinance-builder의 요청이 Google 정책을 준수하지 않습니다
```

**원인**: Google OAuth는 WebView(인앱 브라우저)에서의 로그인을 보안 정책으로 전면 차단.
`signInWithRedirect` vs `signInWithPopup` 선택과 무관하게, Google 서버가 User-Agent를 보고
WebView 식별자(예: `wv`, `KAKAOTALK`, `Line/`, `NAVER`, `Instagram`, `FBAN` 등)를 감지하면
인증 페이지 자체를 차단한다.

**해결** (`frontend/src/App.tsx`):
- `isInAppBrowser()` 함수로 User-Agent를 검사해 WebView 여부를 판별
- `!user` 로그인 카드에서 WebView 감지 시 Google 로그인 버튼 대신 `InAppBrowserWarning` 컴포넌트 표시
- Android: `intent://` scheme으로 Chrome 강제 실행 버튼 제공
- iOS: Safari에서 열라는 안내 + 주소 복사 버튼 제공

```typescript
// App.tsx 하단 유틸리티 함수
function isInAppBrowser(): boolean {
  const ua = navigator.userAgent
  return (
    /wv/.test(ua) || /KAKAOTALK/i.test(ua) || /Line\//i.test(ua) ||
    /NAVER/i.test(ua) || /Instagram/i.test(ua) || /FBAN|FBAV/i.test(ua) ||
    /Twitter/i.test(ua) || /MicroMessenger/i.test(ua)
  )
}

// !user 블록
const inApp = isInAppBrowser()
{inApp ? <InAppBrowserWarning /> : <button onClick={handleLogin}>Google 로그인</button>}
```

**Android Chrome 강제 실행 intent 형식**:
```
intent://<host>/<path>#Intent;scheme=https;package=com.android.chrome;end
```

**체크리스트**: Google 로그인 버튼을 새로 추가하는 곳에서는 반드시 `isInAppBrowser()` 체크를 선행할 것.

---

### 22. `signInWithRedirect` 무음 실패 — Chrome Bounce Tracking 차단 (2026-04-23)

**증상**: 로그인 버튼 클릭 → Google 인증 → 앱으로 돌아옴 → 여전히 로그인 화면, 에러 없음.
`getRedirectResult(auth)`가 오류 없이 `null`을 반환.

**원인**: Chrome 120+의 **Bounce Tracking 방지** 기능.

리다이렉트 경로가 도메인을 가로지르면 (`web.app → google.com → firebaseapp.com/__/auth → web.app`),
Chrome이 중간 경유 도메인(`firebaseapp.com`)의 저장소를 삭제합니다.
Firebase가 `firebaseapp.com`에 저장한 인증 결과가 사라지므로 `getRedirectResult`가 null을 반환.

**해결** (`.env` 수정):
```
# 기존 (cross-origin 경유 → Bounce Tracking 차단됨)
VITE_FIREBASE_AUTH_DOMAIN="ordinance-builder-b9f6c.firebaseapp.com"

# 수정 (동일 도메인 내 처리 → 차단 없음)
VITE_FIREBASE_AUTH_DOMAIN="ordinance-builder-b9f6c.web.app"
```

Firebase Hosting은 `/__/auth/**` 경로를 자동으로 처리하므로 별도 설정 불필요.
리다이렉트 경로가 `web.app → google.com → web.app/__/auth → web.app`으로 단일 도메인 내에서 완결됨.

**체크리스트**:
- `VITE_FIREBASE_AUTH_DOMAIN`은 반드시 앱 호스팅 도메인(`*.web.app`)으로 설정할 것
- `*.firebaseapp.com`을 authDomain으로 사용하면 Chrome 120+에서 로그인이 무음 실패함
- 수정 후 반드시 재빌드 + Firebase Hosting 재배포

---

### 23. Google OAuth — 테스트 모드에서 일부 계정만 로그인 가능 (2026-04-23)

**증상**: 특정 계정(프로젝트 소유자)은 로그인되지만 다른 Google 계정은 "액세스 차단됨" 오류 발생.

**원인**: Google Cloud Console의 OAuth 동의 화면이 **"테스트(Testing)"** 상태일 때:
- 프로젝트 소유자 계정 → 항상 로그인 가능 (테스트 모드와 무관)
- 명시적으로 등록된 테스트 사용자 → 로그인 가능
- 그 외 모든 Google 계정 → "액세스 차단됨" 오류

소유자 계정으로 로그인이 되면 앱 자체 문제가 아니라 OAuth 동의 화면 게시 여부 문제임을 즉시 의심할 것.

**해결**:

Google Cloud Console → **APIs & Services → OAuth consent screen** → **"PUBLISH APP"** 클릭

게시 후 모든 Google 계정으로 로그인 가능. Firebase Auth + Google 로그인 용도는 추가 앱 검수 없이 즉시 게시됨.

**체크리스트**:
- 신규 GCP 프로젝트 생성 후 Firebase Google 로그인 설정 시 반드시 OAuth 동의 화면을 게시할 것
- 로그인 문제 진단 순서:
  1. 소유자 계정으로 로그인 시도 → 성공이면 → OAuth 테스트 모드 문제
  2. 소유자 계정도 실패 → Firebase Auth 설정 또는 redirect_uri 문제 (§22 참조)

**관련 설정 위치**: Google Cloud Console → APIs & Services → OAuth consent screen → Publishing status

---

# 코드 작성 규칙
- 에러 수정 작업 후에는 반드시 수정 내역을 CLAUDE.md에 기록해 놓고 다시 같은 에러가 발생하지 않도록 할 것.