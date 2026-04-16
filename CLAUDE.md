# 조례 빌더 AI (Ordinance Builder AI)

> 대화형 AI를 통해 지자체별 특수성을 반영하고, 상위법령을 준수하는 **지방 조례 초안**을 단계별로 생성·검토하는 풀스택 AI 서비스

---

## 목차

1. [프로젝트 소개](#프로젝트-소개)
2. [핵심 기능](#핵심-기능)
3. [시스템 아키텍처](#시스템-아키텍처)
4. [LangGraph 워크플로우](#langgraph-워크플로우)
5. [OWL 온톨로지 설계](#owl-온톨로지-설계)
6. [데이터베이스 스키마](#데이터베이스-스키마)
7. [ETL 파이프라인](#etl-파이프라인)
8. [프로젝트 구조](#프로젝트-구조)
9. [기술 스택](#기술-스택)
10. [시작하기](#시작하기)
11. [API 명세](#api-명세)
12. [로드맵](#로드맵)

---

## 프로젝트 소개

지방 조례는 법적 형식 요건과 상위법 정합성을 모두 충족해야 하지만, 실무 담당자가 법률 전문 지식 없이 초안을 작성하는 것은 매우 어렵습니다.

**조례 빌더 AI**는 이 문제를 해결하기 위해:

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

```
사용자: "서울시 청년 창업 지원 조례를 만들고 싶어요"
  → region: 서울특별시, purpose: 청년 창업 지원 (자동 추출)
  → 누락: target_group, support_type
AI: "지원 대상 연령 범위와 지원 방식(보조금/공간/멘토링 등)을 알려주세요."
```

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
│  │          ├─[article_interviewing]──► article_interviewer │   │
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
| `intent_analyzer` | Gemini | 자연어 입력 → 필드 추출 (`ExtractedInfo` 구조화 출력) | `ordinance_info`, `missing_fields` |
| `interviewer` | 없음 | 미수집 필드 질문 생성 (최대 2개씩) | `response_to_user` |
| `graph_retriever` | 없음 | Neo4j 쿼리: 상위법 + 유사조례 + 조문 예시 | `legal_basis`, `similar_ordinances` |
| `article_planner` | 없음 | 9개 조항 순서 정의 + 첫 질문 | `article_queue` |
| `article_interviewer` | 없음 | 조항별 답변 수집, "기본값" → None 처리 | `article_contents`, `current_stage` |
| `drafting_agent` | Gemini | 조례 초안 생성 (`OrdinanceDraft`) | `draft_full_text` |
| `draft_reviewer` | Gemini | 피드백 분류 + 수정 적용 | `draft_review_decision` |
| `legal_checker` | Gemini | 상위법 충돌 검증 (`LegalCheckResult`) | `legal_issues`, `is_legally_valid` |

### 조건부 분기 (edges/conditions.py)

```
route_at_start(state) →
  "legal_review_requested"  # draft_text와 함께 POST된 경우
  "draft_review"            # 사용자가 초안 검토 요청
  "article_interviewing"    # 조항 Q&A 진행 중
  "default"                 # intent_analyzer로 진입

after_intent_analyzer(state) →
  "interviewer"   # missing_fields 존재
  "graph_retriever"  # 정보 완비

after_graph_retriever(state) →
  "article_planner"   # article_queue가 없으면 새로 계획
  "drafting_agent"    # 이미 queue 있으면 생성

after_article_interviewer(state) →
  "drafting_agent"  # 모든 조항 완료
  END               # 다음 조항 질문 (다음 /chat 대기)

after_draft_reviewer(state) →
  "legal_checker"  # confirm
  END              # revise (수정된 초안 반환)
```

---

## OWL 온톨로지 설계

법령 도메인의 개념 체계를 **Protégé**로 모델링한 OWL 온톨로지(`ordinance.rdf`)입니다. Neo4j 그래프 스키마의 개념적 기반이 되며, Phase 3에서 SWRL 논리 규칙 추론에 활용할 예정입니다.

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
│   │       ├── chat.py                 # POST /api/v1/session, /chat, /finalize
│   │       └── debug.py                # 디버그 엔드포인트
│   ├── core/
│   │   ├── config.py                   # 환경 변수 설정 (pydantic-settings)
│   │   ├── llm.py                      # Gemini 2.5 Pro 싱글톤
│   │   └── embedder.py                 # Gemini 임베딩 클라이언트
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

## 기술 스택

| 계층 | 기술 | 역할 |
|------|------|------|
| **LLM** | Gemini 2.5 Pro (`langchain-google-genai`) | 정보 추출, 초안 생성, 법률 검증 |
| **Embedding** | `models/gemini-embedding-001` (3072d) | 조문 의미 검색 |
| **Orchestration** | LangGraph + LangChain | 상태 기반 멀티노드 워크플로우 |
| **Backend** | FastAPI + Uvicorn | REST API 서버 |
| **Frontend** | React 18 + TypeScript + Vite | 대화형 UI |
| **Graph DB** | Neo4j 5.23 (Docker) → Neo4j AuraDB (프로덕션) | 법령 관계 그래프 |
| **ETL** | 국가법령정보센터 Open API + 자체 파이프라인 | 법령·조례 데이터 수집 |
| **배포** | Docker Compose (로컬) / Cloud Functions + AuraDB (예정) | 컨테이너 기반 배포 |

---

## 시작하기

### 사전 요구사항

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- [국가법령정보센터 Open API 키](https://open.law.go.kr)
- Google Gemini API 키

### 1. 환경 변수 설정

```bash
cp .env.example .env
```

**모든 환경 변수는 프로젝트 루트 `.env` 하나에서 관리합니다.**  
백엔드(`pydantic-settings`)와 프론트엔드(`VITE_*`) 변수가 모두 이 파일에 정의됩니다.

```env
# ── 백엔드 ──────────────────────────────────────
GOOGLE_API_KEY=<Gemini API 키>
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<Neo4j 비밀번호>
LAW_API_KEY=<국가법령정보센터 API 키>
POSTGRES_URL=postgresql://app_user:<password>@localhost:5432/ordinance_builder
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json

# ── 프론트엔드 (Firebase Web App) ───────────────
# Firebase 콘솔 > 프로젝트 설정 > 웹 앱 > SDK 구성
VITE_FIREBASE_API_KEY=<웹 앱 API 키>
VITE_FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=<project-id>
```

**동작 원리:**
- **로컬 개발**: `frontend/vite.config.ts`의 `envDir: '../'` 설정으로 Vite가 루트 `.env`에서 `VITE_*` 변수를 읽습니다.
- **Docker 빌드**: `docker-compose.yml`의 `build.args`가 루트 `.env`의 `VITE_*` 값을 `frontend/Dockerfile`의 `ARG`로 전달합니다.

### 2. Docker로 전체 실행 (권장)

```bash
docker compose up -d
```

| 서비스 | 주소 |
|--------|------|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Neo4j Browser | http://localhost:7474 |

### 3. 로컬 개발 실행

```bash
# Neo4j만 Docker로 실행
docker compose up -d neo4j

# Backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev       # http://localhost:5173
```

### 4. 데이터 파이프라인 실행 (최초 1회)

```bash
# 국가법령정보센터 → Neo4j 전체 적재 (4단계)
# Phase 1: 필수 법령 6개 적재
# Phase 2: 도메인 키워드 기반 법령 검색 및 적재
# Phase 3: 도메인 키워드 기반 조례 검색 및 적재
# Phase 4: 노드 간 관계 구축 + 전체 벡터 임베딩 생성
python -m pipeline.scripts.initial_load

# 이후 주기적 증분 업데이트
python -m pipeline.scripts.incremental_update
```

### 5. Mock DB로 빠른 테스트

파이프라인 없이 바로 테스트하려면 `app/graph/workflow.py`에서:

```python
# Neo4jGraphDB() 주석 처리
# MockGraphDB() 주석 해제
```

---

## API 명세

### 세션 생성

```
POST /api/v1/session
```

```json
// Request
{ "initial_message": "서울시 청년 창업 지원 조례를 만들고 싶어요" }

// Response
{
  "session_id": "uuid-v4",
  "message": "조례 작성을 시작하겠습니다. 지원 대상 연령 범위를 알려주세요.",
  "stage": "interviewing"
}
```

### 대화 (조례 생성 진행)

```
POST /api/v1/session/{session_id}/chat
```

```json
// Request
{
  "message": "만 19세에서 39세 청년이요",
  "draft_text": null   // 사용자가 직접 편집한 초안 (draft_review 단계에서 사용)
}

// Response
{
  "session_id": "uuid-v4",
  "message": "AI 응답 메시지",
  "stage": "article_interviewing",
  "is_complete": false,
  "draft": null,
  "legal_issues": [],
  "is_legally_valid": null,
  "similar_ordinances": [
    {
      "ordinance_id": "...",
      "region_name": "부산광역시",
      "title": "부산광역시 청년 창업 지원 조례",
      "similarity_score": 0.92,
      "relevance_reason": "지원 대상 및 방식이 유사"
    }
  ]
}
```

### 조례 확정

```
POST /api/v1/session/{session_id}/finalize
```

```json
// Request
{ "draft_text": "최종 편집된 초안 전문" }

// Response
{
  "session_id": "uuid-v4",
  "draft": "최종 조례 초안 전문",
  "legal_issues": [
    {
      "severity": "MEDIUM",
      "related_statute": "보조금 관리에 관한 법률 제22조",
      "description": "보조금 지급 상한선 명시 권장",
      "suggestion": "제5조에 연간 1인당 지급 한도액 추가"
    }
  ],
  "is_legally_valid": true
}
```

### `stage` 값 참조

| 값 | 설명 |
|----|------|
| `intent_analysis` | 사용자 입력 분석 중 |
| `interviewing` | 필수 정보 수집 인터뷰 중 |
| `retrieving` | Graph DB 법적 근거 검색 중 |
| `article_interviewing` | 조항별 세부 내용 인터뷰 중 |
| `draft_review` | AI 초안 검토 완료, 사용자 확인 대기 |
| `legal_review_requested` | 사용자 제출 초안 법률 검증 요청 |
| `legal_checking` | 법률 검증 진행 중 |
| `completed` | 조례 초안 완성 |

---

## 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| **Phase 1** | LangGraph State + 노드 구조 + FastAPI 뼈대 + React 프론트엔드 | ✅ 완료 |
| **Phase 2** | 국가법령정보센터 API 파이프라인 → Neo4j 적재 + 관계 구축 + 벡터 인덱스 | ✅ 완료 |
| **Phase 3** | Protégé 기반 SWRL 논리 규칙(추론) 반영 | 예정 |
| **Phase 4** | 법률 전문가 검토 피드백 반영 및 인간 협업 인터페이스 고도화 | 예정 |
