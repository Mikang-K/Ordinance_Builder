# Multiple LLM Model Support — 구현 계획

> 목표: 답변 품질 향상을 위해 노드별 역할에 최적화된 LLM을 배정한다.  
> 전략: **역할 분담 (Role-based Assignment)** — 각 모델의 강점을 노드 특성에 맞춰 배정  
> 원칙: 기존 `functools.partial` 의존성 주입 패턴과 LangChain `BaseChatModel` 인터페이스를 최대한 활용하여 노드 로직은 건드리지 않는다.

---

## 1. 현황 분석

### LLM을 사용하는 노드 (변경 대상, 4개)

| 노드 | LLM 호출 수 | 현재 타입 힌트 | 작업 성격 |
|------|------------|--------------|----------|
| `intent_analyzer` | 1회 | `ChatGoogleGenerativeAI` | 구조화 추출 (`ExtractedInfo`) |
| `drafting_agent` | 1회 | `ChatGoogleGenerativeAI` | 장문 조례 초안 생성 (`OrdinanceDraft`) |
| `draft_reviewer` | **2회** | `ChatGoogleGenerativeAI` | ① 의도 분류 (`ReviewDecision`) + ② 수정 생성 (`OrdinanceDraft`) |
| `legal_checker` | 1회 | `ChatGoogleGenerativeAI` | 법률 충돌 검증 (`LegalCheckResult`) |

### LLM 없는 노드 (변경 불필요, 4개)

`interviewer`, `article_planner`, `article_interviewer`, `graph_retriever` — 결정론적 또는 DB 쿼리만 사용

### 임베딩 (변경 불가)

`app/core/embedder.py`의 `GoogleGenerativeAIEmbeddings`는 Neo4j 벡터 인덱스(3072차원 cosine)와 연계되어 있다.  
임베딩 모델을 바꾸면 전체 인덱스를 재구축해야 하므로 **Gemini 고정 유지**.

---

## 2. 역할 배정 및 근거

| 노드 | 배정 모델 | 변경 여부 | 근거 |
|------|----------|---------|------|
| `intent_analyzer` | **Gemini 2.5 Pro** | 유지 | 한국어 구조화 추출 이미 검증됨. 임베딩 파이프라인과 동일 제공자 유지로 일관성 확보 |
| `drafting_agent` | **Claude Opus 4.6** | 변경 | 장문 법적 문서 작성에서 Claude의 문체 일관성·조항 구조 유지 능력이 우수 |
| `draft_reviewer` | **Claude Opus 4.6** | 변경 | 수정 생성(Call 2)이 주 작업이며 장문 생성이므로 Claude 적합. 의도 분류(Call 1)는 동일 모델로 처리 |
| `legal_checker` | **GPT-4o** | 변경 | 비판적 법률 분석, 충돌 감지, 조항별 논리 검토에서 GPT-4o의 분석력이 우수 |

### `draft_reviewer` 2-Call 구조 상세

```python
# Call 1: 의도 분류 (confirm / revise) — 간단한 이진 분류
classifier_llm = llm.with_structured_output(ReviewDecision)

# Call 2: 수정 생성 — 전체 조례 초안 재생성 (revise 시만 실행)
reviser_llm = llm.with_structured_output(OrdinanceDraft)
```

초기 구현에서는 **하나의 `llm` (Claude Opus 4.6)** 을 두 호출 모두에 사용한다.  
Call 1은 분류 난이도가 낮아 Claude 사용이 다소 과잉이지만, 시그니처 변경 없이 단순하게 유지할 수 있다.  
→ 향후 개선: `classifier_llm` (GPT-4o-mini)과 `reviser_llm` (Claude)로 분리 가능 (Step 5 참고)

---

## 3. `.with_structured_output()` 호환성 확인

세 provider 모두 LangChain의 `BaseChatModel` 인터페이스를 구현하며,  
`.with_structured_output(PydanticModel)` 을 통한 구조화 출력을 지원한다.

| Provider | 구현 방식 | 호환 여부 |
|----------|---------|---------|
| `langchain-google-genai` | Gemini 함수 호출 | ✅ |
| `langchain-anthropic` | Claude tool use | ✅ |
| `langchain-openai` | OpenAI function calling / JSON mode | ✅ |

기존 노드 로직의 `structured_llm.invoke(messages)` 패턴은 **세 provider 모두 동일하게 동작**한다.

---

## 4. 구현 단계

### Step 1: 의존성 추가

**파일: `requirements.txt`**

```
# 추가 (기존 langchain-google-genai 아래에)
langchain-openai>=0.2.0
langchain-anthropic>=0.3.0
```

설치 확인:
```bash
pip install langchain-openai langchain-anthropic
```

---

### Step 2: 환경 변수 추가

**파일: `.env`**

```env
# ── 추가 LLM API 키 ──────────────────────────────────────
OPENAI_API_KEY=<OpenAI API 키>
ANTHROPIC_API_KEY=<Anthropic API 키>

# ── 노드별 LLM 제공자 설정 (기본값 포함, 변경 시만 .env에 명시) ──
LLM_INTENT=gemini       # intent_analyzer
LLM_DRAFTING=anthropic  # drafting_agent
LLM_REVIEWER=anthropic  # draft_reviewer
LLM_LEGAL=openai        # legal_checker
```

---

### Step 3: `app/core/config.py` 확장

**변경 내용:** API 키 2개, 노드별 provider 설정 4개 추가

```python
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    OPENAI_API_KEY: str = ""       # 추가
    ANTHROPIC_API_KEY: str = ""    # 추가

    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # 노드별 LLM provider 설정 (추가)
    LLM_INTENT: Literal["gemini", "openai", "anthropic"] = "gemini"
    LLM_DRAFTING: Literal["gemini", "openai", "anthropic"] = "anthropic"
    LLM_REVIEWER: Literal["gemini", "openai", "anthropic"] = "anthropic"
    LLM_LEGAL: Literal["gemini", "openai", "anthropic"] = "openai"

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    POSTGRES_URL: str
    FIREBASE_CREDENTIALS_PATH: str = ""

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

---

### Step 4: `app/core/llm.py` 리팩터링

**변경 내용:** 단일 싱글톤 → provider별 캐싱 팩토리 함수

```python
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings

# provider별 인스턴스 캐시
_llm_cache: dict[str, BaseChatModel] = {}


def get_llm(provider: str | None = None) -> BaseChatModel:
    """
    provider에 맞는 LLM 인스턴스를 반환한다. 인스턴스는 provider별로 캐싱된다.

    Args:
        provider: "gemini" | "openai" | "anthropic". None이면 "gemini"로 폴백.

    Returns:
        BaseChatModel 구현체 (세 provider 모두 .with_structured_output() 지원)
    """
    key = provider or "gemini"

    if key not in _llm_cache:
        if key == "gemini":
            _llm_cache[key] = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0.2,
                max_output_tokens=8192,
            )
        elif key == "openai":
            _llm_cache[key] = ChatOpenAI(
                model="gpt-4o",
                api_key=settings.OPENAI_API_KEY,
                temperature=0.2,
                max_tokens=8192,
            )
        elif key == "anthropic":
            _llm_cache[key] = ChatAnthropic(
                model="claude-opus-4-6",
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=0.2,
                max_tokens=8192,
            )
        else:
            raise ValueError(f"지원하지 않는 LLM provider: {key}")

    return _llm_cache[key]
```

**설계 포인트:**
- `_llm_cache` dict로 provider별 인스턴스를 재사용한다 (기존 싱글톤과 동일한 효과)
- 반환 타입이 `BaseChatModel`이므로 호출부에서 provider를 알 필요 없다
- `provider=None` 호출은 기존 `get_llm()` 형태와 동일하게 동작해 하위 호환성 유지

---

### Step 5: 노드 타입 힌트 수정 (4개 파일)

각 노드 파일에서 import 1줄, 타입 힌트 1곳만 변경한다. **함수 본문은 전혀 수정하지 않는다.**

#### `app/graph/nodes/intent_analyzer.py`

```python
# 변경 전
from langchain_google_genai import ChatGoogleGenerativeAI

def intent_analyzer_node(state: OrdinanceBuilderState, llm: ChatGoogleGenerativeAI) -> dict:

# 변경 후
from langchain_core.language_models import BaseChatModel

def intent_analyzer_node(state: OrdinanceBuilderState, llm: BaseChatModel) -> dict:
```

#### `app/graph/nodes/drafting_agent.py`

```python
# 변경 전
from langchain_google_genai import ChatGoogleGenerativeAI

def drafting_agent_node(state: OrdinanceBuilderState, llm: ChatGoogleGenerativeAI) -> dict:

# 변경 후
from langchain_core.language_models import BaseChatModel

def drafting_agent_node(state: OrdinanceBuilderState, llm: BaseChatModel) -> dict:
```

#### `app/graph/nodes/draft_reviewer.py`

```python
# 변경 전
from langchain_google_genai import ChatGoogleGenerativeAI

def draft_reviewer_node(state: OrdinanceBuilderState, llm: ChatGoogleGenerativeAI) -> dict:

# 변경 후
from langchain_core.language_models import BaseChatModel

def draft_reviewer_node(state: OrdinanceBuilderState, llm: BaseChatModel) -> dict:
```

#### `app/graph/nodes/legal_checker.py`

```python
# 변경 전
from langchain_google_genai import ChatGoogleGenerativeAI

def legal_checker_node(state: OrdinanceBuilderState, llm: ChatGoogleGenerativeAI) -> dict:

# 변경 후
from langchain_core.language_models import BaseChatModel

def legal_checker_node(state: OrdinanceBuilderState, llm: BaseChatModel) -> dict:
```

---

### Step 6: `app/graph/workflow.py` 수정

노드별로 다른 LLM 인스턴스를 주입한다.

```python
# 변경 전
llm = get_llm()

builder.add_node("intent_analyzer", partial(intent_analyzer_node, llm=llm))
builder.add_node("drafting_agent",  partial(drafting_agent_node,  llm=llm))
builder.add_node("draft_reviewer",  partial(draft_reviewer_node,  llm=llm))
builder.add_node("legal_checker",   partial(legal_checker_node,   llm=llm))

# 변경 후
intent_llm   = get_llm(settings.LLM_INTENT)    # Gemini 2.5 Pro
drafting_llm = get_llm(settings.LLM_DRAFTING)  # Claude Opus 4.6
reviewer_llm = get_llm(settings.LLM_REVIEWER)  # Claude Opus 4.6
legal_llm    = get_llm(settings.LLM_LEGAL)      # GPT-4o

builder.add_node("intent_analyzer", partial(intent_analyzer_node, llm=intent_llm))
builder.add_node("drafting_agent",  partial(drafting_agent_node,  llm=drafting_llm))
builder.add_node("draft_reviewer",  partial(draft_reviewer_node,  llm=reviewer_llm))
builder.add_node("legal_checker",   partial(legal_checker_node,   llm=legal_llm))
```

---

## 5. 변경 파일 요약

| 파일 | 변경 내용 |
|------|---------|
| `requirements.txt` | `langchain-openai`, `langchain-anthropic` 추가 |
| `.env` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_*` 4개 추가 |
| `app/core/config.py` | API 키 2개, `LLM_*` 설정 4개 추가 |
| `app/core/llm.py` | 싱글톤 → 캐싱 팩토리 (`get_llm(provider)`) 리팩터링 |
| `app/graph/nodes/intent_analyzer.py` | import + 타입 힌트 1줄씩 변경 |
| `app/graph/nodes/drafting_agent.py` | import + 타입 힌트 1줄씩 변경 |
| `app/graph/nodes/draft_reviewer.py` | import + 타입 힌트 1줄씩 변경 |
| `app/graph/nodes/legal_checker.py` | import + 타입 힌트 1줄씩 변경 |
| `app/graph/workflow.py` | 노드별 LLM 인스턴스 분리 주입 |

**변경하지 않는 파일:**  
`app/core/embedder.py`, `app/main.py`, `app/db/`, `app/prompts/`, `app/graph/edges/`, `app/graph/state.py`,  
`app/graph/nodes/interviewer.py`, `app/graph/nodes/article_planner.py`, `app/graph/nodes/article_interviewer.py`, `app/graph/nodes/graph_retriever.py`

---

## 6. 향후 확장: `draft_reviewer` 2-LLM 분리 (선택)

현재 `draft_reviewer_node`는 단일 `llm`을 두 목적으로 사용한다.  
비용 최적화가 필요해지면 노드 시그니처를 아래와 같이 확장할 수 있다.

```python
# draft_reviewer.py 시그니처 확장 (선택적 개선)
def draft_reviewer_node(
    state: OrdinanceBuilderState,
    llm: BaseChatModel,                          # 수정 생성용 (Claude)
    classifier_llm: BaseChatModel | None = None, # 분류 전용 (GPT-4o-mini) — None이면 llm 폴백
) -> dict:
    effective_classifier = classifier_llm or llm

    # Call 1: 의도 분류
    classifier = effective_classifier.with_structured_output(ReviewDecision)

    # Call 2: 수정 생성 (revise 시)
    reviser = llm.with_structured_output(OrdinanceDraft)
    ...
```

```python
# workflow.py 주입 (선택적 개선)
classifier_llm = get_llm("openai")  # gpt-4o-mini로 교체 가능
reviewer_llm   = get_llm(settings.LLM_REVIEWER)

builder.add_node(
    "draft_reviewer",
    partial(draft_reviewer_node, llm=reviewer_llm, classifier_llm=classifier_llm)
)
```

---

## 7. 검증 방법

1. **의존성 확인**
   ```bash
   pip install -r requirements.txt
   python -c "from langchain_openai import ChatOpenAI; from langchain_anthropic import ChatAnthropic; print('OK')"
   ```

2. **팩토리 함수 단위 테스트**
   ```python
   from app.core.llm import get_llm
   llm_g = get_llm("gemini")
   llm_o = get_llm("openai")
   llm_a = get_llm("anthropic")
   assert get_llm("gemini") is get_llm("gemini")  # 캐시 검증
   ```

3. **구조화 출력 호환성 확인** — 각 노드를 Mock State로 직접 호출하여 Pydantic 모델 파싱 오류 없는지 확인

4. **엔드투엔드 테스트** — 전체 워크플로우를 실행하여 `intent_analyzer → drafting_agent → draft_reviewer → legal_checker` 경로를 모두 통과하는지 확인
