# Q&A 기능 구현 계획 (GraphRAG 기반)

## 목표

조례 초안 작성 워크플로우 진행 중 언제든 자유롭게 질의응답할 수 있는 기능을 추가한다.
- Neo4j AuraDB의 법령·조례 그래프를 실시간 탐색하여 답변을 생성한다 (GraphRAG).
- 워크플로우 상태(`current_stage`, `article_contents` 등)를 변경하지 않는다.
- Q&A 답변을 선택적으로 현재 조항 입력창에 pre-fill할 수 있다.
- 기존 LangGraph 라우팅 불변 조건을 일절 건드리지 않는다.

---

## 설계 원칙

| 원칙 | 이유 |
|------|------|
| LangGraph 미경유, 체크포인트 읽기 전용 | Q&A는 OrdinanceBuilderState를 수정하지 않음 |
| 기존 DB 메서드 재사용 | `find_legal_basis`, `find_legal_terms`, `find_similar_ordinances` 그대로 활용 |
| `article_examples` 캐시 재활용 | graph_retriever가 이미 state에 적재한 조항 예시를 재탐색 없이 재사용 |
| 검색 전략은 기존 4단계 폴백 유지 | DELEGATES → BASED_ON → KEYWORD → VECTOR 순서 동일 |
| 워크플로우와 완전히 분리된 엔드포인트 | 기존 `/chat`, `/articles_batch` 흐름에 영향 없음 |
| Pre-fill은 선택적 · 사용자 확인 필수 | AI 답변이 자동으로 조항에 들어가지 않도록 |

---

## GraphRAG Q&A 아키텍처

```
[프론트엔드 QAPanel]
  질문 입력 → POST /api/v1/session/{id}/qa
                       │
          ┌────────────▼────────────┐
          │   1. 체크포인트 읽기     │  (읽기 전용)
          │   - ordinance_info       │
          │   - article_examples     │  ← graph_retriever 캐시 재활용
          │   - current_article_key  │
          │   - draft_full_text      │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   2. 키워드 추출         │
          │   question + ordinance_  │
          │   info → keywords list   │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   3. GraphRAG 병렬 검색  │
          │                          │
          │  ① find_legal_basis      │  → 관련 법령 조항
          │     (4단계 폴백)          │    DELEGATES/BASED_ON/
          │                          │    KEYWORD/VECTOR
          │  ② find_legal_terms      │  → 법률 용어 정의
          │     (2단계 폴백)          │    DEFINES/직접 매칭
          │                          │
          │  ③ find_article_examples │  → 유사 조례 조항 예시
          │     (캐시에서 필터링)     │    ← article_examples 재사용
          │     [article_interviewing│    현재 조항키 기준 매칭
          │      단계일 때만]         │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   4. RAG 프롬프트 구성   │
          │   - 검색된 법령 근거     │
          │   - 법률 용어 정의       │
          │   - 유사 조례 조항 예시  │
          │   - 현재 조례 맥락       │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   5. LLM 답변 생성       │
          │   (Gemini 2.5 Pro)       │
          │   - answer               │
          │   - sources (인용 근거)  │
          │   - applicable_content   │  → 현재 조항 pre-fill용
          │     [article_interviewing│
          │      + 관련 질문일 때만] │
          └────────────┬────────────┘
                       │
                   QAResponse
                       │
         ┌─────────────┘
         │  stage == "article_interviewing"
         │  AND applicable_content 존재
         ▼
  "현재 조항에 적용하기" 버튼
         │
         ▼
  ArticleItemsModal textarea pre-fill
  → 사용자 확인 후 직접 제출
```

---

## 검색 전략 (질문 유형별)

| 질문 유형 | 호출 DB 메서드 | 비고 |
|-----------|--------------|------|
| "관련 법령이 뭔가요?" | `find_legal_basis` | 항상 호출 |
| "이 용어의 법적 정의가 뭔가요?" | `find_legal_terms` | 항상 호출 |
| "[조항명]에 뭘 써야 하나요?" | `find_article_examples` (캐시) | article_interviewing 단계만 |
| "비슷한 조례 예시를 보여줘" | `find_similar_ordinances` (선택적) | 캐시에 없을 때 추가 호출 |
| "이 내용이 위법인가요?" | `find_legal_basis` + `get_limiting_provisions` | legal_basis에서 벌칙 조항 필터 |

**기본 전략**: `find_legal_basis` + `find_legal_terms` 항상 병렬 실행.  
`article_interviewing` 단계에서는 체크포인트의 `article_examples`에서 `find_article_examples`로 추가 필터링.

---

## 키워드 추출 방식

질문 텍스트 + 현재 `ordinance_info`를 결합하여 검색 키워드를 구성한다.
별도 LLM 호출 없이 간단한 규칙 기반 추출을 우선 적용한다.

```python
def extract_qa_keywords(question: str, ordinance_info: dict) -> list[str]:
    # 1. ordinance_info 핵심 필드 (인터뷰에서 수집한 정보)
    base = [
        ordinance_info.get("purpose", ""),
        ordinance_info.get("target_group", ""),
        ordinance_info.get("support_type", ""),
        ordinance_info.get("industry_sector", ""),
    ]
    # 2. 질문에서 명사성 단어 추출 (조사·접속사 제거, 4자 이상 우선)
    q_words = [w for w in question.split() if len(w) >= 2]
    
    return [w for w in base + q_words if w][:10]  # 최대 10개
```

이 방식으로도 `find_legal_basis`의 VECTOR_MATCH 단계에서 의미론적 검색이 보완된다.

---

## 변경 파일 목록

### 백엔드

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `app/api/schemas.py` | 수정 | `QARequest`, `QAResponse`, `QASource` 추가 |
| `app/api/routers/chat.py` | 수정 | `POST /api/v1/session/{session_id}/qa` 엔드포인트 추가 |
| `app/prompts/qa_agent.py` | 신규 | GraphRAG Q&A 프롬프트 템플릿 |

> `app/db/`, `app/graph/workflow.py`, `app/graph/edges/conditions.py` **변경 없음**

### 프론트엔드

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `frontend/src/types.ts` | 수정 | `QAMessage`, `QAResponse`, `QASource` 타입 추가 |
| `frontend/src/api.ts` | 수정 | `askQuestion()` 함수 추가 |
| `frontend/src/components/QAPanel.tsx` | 신규 | Q&A 사이드패널 컴포넌트 |
| `frontend/src/App.tsx` | 수정 | QA 상태 추가, QAPanel 렌더링, 콜백 연결 |
| `frontend/src/App.css` | 수정 | QAPanel 슬라이드 애니메이션 CSS |
| `frontend/src/components/ArticleItemsModal.tsx` | 수정 | `pendingQAContent` prop 수신 및 pre-fill 처리 |

---

## 상세 설계

### 1. 백엔드 스키마 (`app/api/schemas.py`)

```python
class QASource(BaseModel):
    source_type: Literal["statute", "ordinance", "legal_term"]
    title: str           # 법령명 또는 조례명
    article_no: str      # 조항 번호
    content: str         # 관련 조항 텍스트 (최대 200자)
    relation_type: str   # DELEGATES / BASED_ON / KEYWORD_MATCH / VECTOR_MATCH 등

class QARequest(BaseModel):
    question: str = Field(..., max_length=2000)

class QAResponse(BaseModel):
    answer: str                             # GraphRAG 기반 AI 답변
    sources: list[QASource]                 # 인용한 법령·조례 근거 목록
    applicable_content: Optional[str]       # 조항에 바로 사용 가능한 텍스트 (없으면 None)
    applicable_article_key: Optional[str]   # 어떤 조항에 적용할지 (current_article_key)
```

### 2. Q&A 엔드포인트 핸들러 (`app/api/routers/chat.py`)

```python
@router.post("/session/{session_id}/qa")
async def qa(session_id: str, body: QARequest, user = Depends(get_current_user)):
    # 1. 세션 소유권 확인
    await _require_ownership(session_id, user.uid)
    
    # 2. 체크포인트에서 읽기 전용 상태 로드
    checkpoint = await graph.aget_state({"configurable": {"thread_id": session_id}})
    values = checkpoint.values if checkpoint else {}
    
    ordinance_info     = values.get("ordinance_info", {})
    article_examples   = values.get("article_examples", [])   # 캐시된 유사 조례 조항
    current_article_key = values.get("current_article_key")
    current_stage      = values.get("current_stage", "")
    draft_full_text    = values.get("draft_full_text", "")
    
    # 3. 키워드 추출
    keywords = extract_qa_keywords(body.question, ordinance_info)
    support_type = ordinance_info.get("support_type", "")
    
    # 4. GraphRAG 병렬 검색
    legal_basis, legal_terms = await asyncio.gather(
        asyncio.to_thread(db.find_legal_basis, keywords, support_type),
        asyncio.to_thread(db.find_legal_terms, keywords),
    )
    
    # 5. 조항 예시 필터링 (article_interviewing 단계에서만, 캐시 재사용)
    article_ex = []
    if current_stage == "article_interviewing" and current_article_key:
        article_ex = find_article_examples(current_article_key, article_examples, max_count=3)
    
    # 6. RAG 프롬프트 구성 및 LLM 호출
    response = await _call_qa_llm(
        question=body.question,
        ordinance_info=ordinance_info,
        legal_basis=legal_basis,
        legal_terms=legal_terms,
        article_examples=article_ex,
        current_article_key=current_article_key,
        draft_full_text=draft_full_text,
    )
    
    return response  # QAResponse
```

**Rate limit**: 별도 `qa_limiter = RateLimiter(20/분)` 적용

### 3. Q&A 프롬프트 (`app/prompts/qa_agent.py`)

```
[시스템 역할]
당신은 대한민국 지방자치단체 조례 초안 작성 전문 어시스턴트입니다.
아래 그래프 DB에서 검색된 법령·조례 데이터를 근거로 답변하세요.
추측이 아닌 제공된 데이터 기반으로만 답변하며, 근거를 명시하세요.

[현재 작성 중인 조례 정보]
- 지역: {region}
- 목적: {purpose}
- 지원 대상: {target_group}
- 지원 유형: {support_type}
{draft_section}          ← draft_full_text 있으면 일부 첨부

[그래프 DB 검색 결과 — 법령 근거]
{legal_basis_block}      ← relation_type + statute_title + article_no + content

[그래프 DB 검색 결과 — 법률 용어 정의]
{legal_terms_block}      ← term_name + definition + source_statute

[유사 조례 조항 사례]
{article_examples_block} ← region + ordinance_title + article_no + content_text
                           (format_examples_block 함수 재사용)

[현재 작성 중인 조항]
{current_article_key}    ← article_interviewing 단계에서만

[사용자 질문]
{question}

[출력 형식 — JSON]
{
  "answer": "...",              // 한국어 답변, 법령 조항 번호 명시 인용
  "sources": [                  // 인용한 근거 목록 (최대 5개)
    {"source_type": "statute"|"ordinance"|"legal_term",
     "title": "...", "article_no": "...",
     "content": "...(최대 200자)", "relation_type": "..."}
  ],
  "applicable_content": "...",  // 현재 조항에 바로 쓸 수 있는 텍스트
                                 // (current_article_key가 있고
                                 //  질문이 해당 조항 내용과 관련될 때만)
  "applicable_article_key": "..." // applicable_content 대상 조항 키
}
```

**`applicable_content` 생성 기준**:
- `current_article_key`가 non-null
- 질문 내용이 해당 조항 작성과 직접 연관
- 유사 조례 사례(`article_examples_block`)를 참고해 조항 템플릿 형태로 생성
- 조건 미충족 시 null 반환

### 4. TypeScript 타입 (`frontend/src/types.ts`)

```typescript
interface QASource {
  source_type: 'statute' | 'ordinance' | 'legal_term'
  title: string
  article_no: string
  content: string
  relation_type: string
}

interface QAMessage {
  role: 'user' | 'ai'
  text: string
  sources?: QASource[]           // AI 답변에만 존재
  applicable_content?: string | null
  applicable_article_key?: string | null
}

interface QAResponse {
  answer: string
  sources: QASource[]
  applicable_content?: string | null
  applicable_article_key?: string | null
}
```

### 5. API 클라이언트 함수 (`frontend/src/api.ts`)

```typescript
export async function askQuestion(
  sessionId: string,
  question: string
): Promise<QAResponse>
```

### 6. QAPanel 컴포넌트 (`frontend/src/components/QAPanel.tsx`)

**Props:**
```typescript
interface QAPanelProps {
  isOpen: boolean
  onClose: () => void
  sessionId: string
  stage: Stage | null
  currentArticleKey: string | null
  onApplyContent: (content: string) => void
  fontSize: number
}
```

**UI 구조:**
```
[오른쪽에서 슬라이드인 패널, 폭 440px]
┌────────────────────────────────────┐
│ 💬 조례 작성 도우미           [×] │
├────────────────────────────────────┤
│ [대화 기록 영역 - 스크롤]          │
│  user: 질문 내용                   │
│                                    │
│  ai: 답변 내용                     │
│      ───────────────────────────   │
│      📋 법령 근거                  │
│      • 지방자치법 제22조 (DELEGATES)│  ← sources 표시
│        "지방자치단체는..."          │
│      • 청년기본법 제5조 (BASED_ON) │
│        "국가 및 지자체는..."        │
│      ───────────────────────────   │
│      [↩ 현재 조항에 적용하기]      │  ← applicable_content 있고
│                                    │     article_interviewing일 때만
├────────────────────────────────────┤
│ [입력창]                  [전송 →] │
└────────────────────────────────────┘
```

**"현재 조항에 적용하기" 버튼 표시 조건:**
- `stage === 'article_interviewing'`
- `applicable_content` 값 존재
- `applicable_article_key === currentArticleKey`

**sources 표시**: 접힌 형태(collapsed)로 기본 표시, 클릭 시 펼침.  
`relation_type` 값에 따라 배지 색상 구분:
- `DELEGATES`: 파랑 (법적 위임)
- `BASED_ON`: 초록 (참조 근거)
- `KEYWORD_MATCH` / `VECTOR_MATCH`: 회색 (검색 매칭)

### 7. App.tsx 상태 추가

```typescript
const [isQAPanelOpen, setIsQAPanelOpen] = useState(false)
const [qaHistory, setQAHistory] = useState<QAMessage[]>([])
const [pendingQAContent, setPendingQAContent] = useState<string | null>(null)
```

**"질문하기" 버튼 위치:**
- 채팅창 입력영역 우측 상단 아이콘 버튼 (세션 있을 때 항상 표시)
- ArticleItemsModal 헤더 내부 (조항 작성 중 접근성 향상)

**pre-fill 연결:**
```typescript
const handleApplyQAContent = (content: string) => {
  setPendingQAContent(content)
  setIsQAPanelOpen(false)
}
// ArticleItemsModal의 pendingQAContent prop으로 전달
// 모달 내에서 현재 조항 textarea에 값 set 후 onQAContentApplied() 호출
```

**세션 전환 시 초기화:**
```typescript
const resetState = () => {
  // ...기존 초기화...
  setIsQAPanelOpen(false)
  setQAHistory([])
  setPendingQAContent(null)
}
```

### 8. ArticleItemsModal 수정

```typescript
interface ArticleItemsModalProps {
  // ...기존 props...
  pendingQAContent?: string | null
  onQAContentApplied?: () => void
  onOpenQA?: () => void
}
```

`pendingQAContent`가 non-null이면 현재 조항 `values[currentKey]`에 자동 set 후 `onQAContentApplied()` 호출.  
기존 값이 있을 경우 "현재 입력 내용을 대체합니다" confirm 다이얼로그 표시.

---

## UI/UX 흐름

### 시나리오 1: 법령 근거 질문

```
기본정보 인터뷰 단계
  → "질문하기" 버튼 클릭 → QAPanel 슬라이드인
  → "청년 창업 조례를 만들 때 어떤 법령 위임이 필요한가요?" 입력
  → GraphRAG: find_legal_basis(["청년", "창업", "지원"])
              find_legal_terms(["청년", "창업"])
  → AI 답변 + sources:
      📋 법령 근거
      • 청년기본법 제15조 (DELEGATES): "지자체는 청년 창업 지원 조례를..."
      • 중소기업창업 지원법 제3조 (BASED_ON): "...위임 가능"
  → 사용자가 답변 참고 후 인터뷰 계속 (적용 버튼 없음)
```

### 시나리오 2: 조항 작성 중 질문 → pre-fill 적용

```
ArticleItemsModal에서 "지원금액" 조항 작성 중
  → "질문하기" 버튼 클릭 → QAPanel 슬라이드인
  → "청년 창업 지원금 한도를 어떻게 설정하면 법적으로 안전한가요?" 입력
  → GraphRAG:
      find_legal_basis(["지원금액", "한도", "청년", "창업"])  → 보조금 관리법 관련 조항
      find_legal_terms(["보조금", "지원한도"])
      find_article_examples("지원금액", cached_article_examples)  → 서울시·부산시 조례 예시
  → AI 답변 + applicable_content: "이 조례에 따른 지원금액은 연간 500만원 이내로 한다. 다만, 예산의 범위에서 조정할 수 있다."
  → 📋 법령 근거 표시 + "↩ 현재 조항에 적용하기" 버튼
  → 클릭 → QAPanel 닫힘 → "지원금액" textarea에 pre-fill
  → 사용자가 내용 수정 후 "확인 및 조례 초안 생성" 제출
```

### 시나리오 3: 초안 검토 중 법률 질문

```
DraftModal에서 초안 확인 중
  → "질문하기" 버튼 클릭 → QAPanel 슬라이드인
  → "제3조 지원 대상에 외국인을 포함하면 상위법 위반인가요?" 입력
  → GraphRAG:
      find_legal_basis(["외국인", "지원대상"])  → 외국인 관련 법령 조항
      find_legal_terms(["외국인"])             → 외국인처우법 정의
  → AI: "보조금 관리에 관한 법률 제…조에 따라 외국인 포함 시 다음 요건이 필요합니다..."
  → 사용자가 직접 DraftModal textarea에서 수정 (적용 버튼 없음 — article_interviewing 아님)
```

---

## 구현 순서

1. **백엔드 기반**
   - `app/api/schemas.py` — `QASource`, `QARequest`, `QAResponse` 추가
   - `app/prompts/qa_agent.py` — GraphRAG RAG 프롬프트 작성
   - `app/api/routers/chat.py` — `/qa` 엔드포인트, `extract_qa_keywords()`, `_call_qa_llm()` 구현

2. **프론트엔드 기반**
   - `frontend/src/types.ts` — 타입 추가
   - `frontend/src/api.ts` — `askQuestion()` 추가

3. **UI 컴포넌트**
   - `frontend/src/components/QAPanel.tsx` — Q&A 패널 신규 작성
   - `frontend/src/App.css` — 슬라이드 애니메이션 추가

4. **연결**
   - `frontend/src/App.tsx` — 상태 추가, QAPanel 렌더링, 콜백 연결
   - `frontend/src/components/ArticleItemsModal.tsx` — `pendingQAContent` pre-fill 처리

---

## 주의사항 및 체크리스트

### 불변 조건
- [ ] `/qa` 엔드포인트는 LangGraph 체크포인트를 **읽기만** 하고 쓰지 않는다
- [ ] `route_at_start` 수정 불필요 (Q&A는 LangGraph 미경유)
- [ ] `OrdinanceBuilderState` 필드 추가 불필요

### GraphRAG 관련
- [ ] `article_examples`가 체크포인트에 없는 경우 (인터뷰 단계 이전) → 빈 리스트로 처리
- [ ] `find_legal_basis`의 4단계 폴백 중 VECTOR_MATCH는 AuraDB에서 Provision 임베딩 비활성화 시 실패 → `try/except`로 감싸 graceful fallback 처리 (기존 `graph_retriever.py`와 동일 패턴)
- [ ] Neo4j 연결 실패 시 → GraphRAG 없이 LLM만으로 답변 (degraded mode 안내 문구 포함)

### TypeScript 타입
- [ ] `applicable_content?: string | null` — Python None → JSON null 허용
- [ ] `sources: QASource[]` — 빈 배열로 초기화

### 모달 z-index 계층
| 컴포넌트 | z-index |
|----------|---------|
| LoadingModal | 200 |
| QAPanel | 150 |
| DraftModal / ArticleItemsModal | 100 |

### Pre-fill 안전성
- [ ] `applicable_article_key`가 `currentArticleKey`와 일치할 때만 "적용" 버튼 표시
- [ ] 기존 입력값 있을 때 덮어쓰기 confirm 다이얼로그 표시

### QA 세션 상태
- [ ] 세션 전환·초기화 시 `qaHistory`, `pendingQAContent` 초기화
- [ ] QAPanel 닫을 때 `qaHistory`는 유지 (같은 세션 내에서 QA 기록 보존)
- [ ] `qaHistory`는 PostgreSQL에 저장하지 않음 (메모리 전용, 세션 재접속 시 초기화)

### CLAUDE.md 업데이트 항목 (구현 완료 후)
- `/qa` 엔드포인트 추가 (엔드포인트 매핑 표)
- QAPanel 컴포넌트 설명
- GraphRAG Q&A 검색 전략 (§ 새 섹션)
- Pre-fill 연결 패턴
