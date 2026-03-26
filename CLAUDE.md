# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language & Style
- **Communication Language:** All responses and explanations must be in Korean. (모든 답변과 설명은 한국어로 작성할 것)
- **Code Comments:** Keep code comments in English for universality. (코멘트는 관례에 따라 영어로 유지)

## 📜 프로젝트 명세서: [프로젝트명: 조례 빌더 AI]

## 1. 프로젝트 개요 (Overview)

- **목적:** 사용자와의 대화를 통해 지자체별 특수성을 반영하고, 상위법령을 준수하는 '지방 조례 초례'를 단계별로 생성 및 검토하는 서비스.
- **핵심 가치:** * **법적 안정성:** 상위법 위반 여부를 실시간 검토.
    - **사용자 편의성:** 복잡한 법률 용어를 몰라도 대화를 통해 조례 완성.
    - **데이터 기반:** 전국 지자체의 유사 조례 데이터를 참고하여 최적의 초안 제안.

---

## 2. 시스템 아키텍처 (Architecture)

### **A. 데이터 계층 (Data Layer)**

- **Source:** 국가법령정보센터(Open API) - 법령, 시행령, 조례 데이터.
- **Storage:** **Neo4j AuraDB (Graph DB)**.
    - **Ontology:** 법령-조항-지자체-산업군 간의 논리적 관계 정의.
    - **Vector Index:** 조문 텍스트의 의미적 검색을 위한 임베딩 저장.

### **B. 추론 및 제어 계층 (Reasoning & Control)**

- **Framework:** **LangGraph**.
    - **State:** 대화 중 수집된 정보(지역, 목적, 지원금 등)를 실시간 유지.
    - **Nodes:** 1. `Intent Analyzer`: 사용자 입력에서 필수 정보 추출.
    2. `Graph Retriever`: Neo4j에서 관련 상위법 및 유사 조례 탐색.
    3. `Drafting Agent`: 수집된 정보를 바탕으로 법적 조문 생성.
    4. `Legal Checker`: 생성된 초안과 상위법 노드 간의 충돌 검증.

---

## **3. 주요 기능 명세 (Functional Requirements)**

| **구분** | **기능명** | **상세 설명** |
| --- | --- | --- |
| **분석** | 조례 간 관계 시각화 | 특정 키워드(예: '청년 복지')와 관련된 모든 조례의 연결망 표시 |
| **생성** | 맞춤형 조례 초안 생성 | 지역 특성, 대상, 목적 입력 시 법적 형식을 갖춘 초안 출력 |
| **검증** | 상위법 정합성 체크 | 생성된 조례가 헌법, 법률, 시행령 등 상위법과 충돌하는지 분석 |
| **추천** | 유사 사례 추천 | 타 지자체에서 시행 중인 유사 목적의 우수 조례 추천 |

---

## **4. 데이터베이스 스키마 설계 (Graph Schema)**

### 노드 명세

| **노드 레이블** | **주요 속성(Property)** | **설명** |
| --- | --- | --- |
| **Statute(법령)** | id, title, category(법률/시행령), enforcement_date | 상위 법령 전체 |
| **Provision(조문)** | article_no, content_text, is_penalty_clause(boolean) | 법령의 개별 조문 |
| **Ordinance(조례)** | id, region_name, title, last_updated | 지자체 조례 |
| **LegalTerm(법률 키워드)** | term_name, definition, synonyms(list) | 핵심 법률 키워드 |

### 관계 명세

| **관계 타입(Type)** | **출발 노드 → 도착 노드** | **설명** |
| --- | --- | --- |
| **BASED_ON** | `Ordinance` → `Statute` | 해당 조례가 어떤 법령에 근거하여 제정되었는가 |
| **CONTAINS** | `Statute` → `Provision` | 법령이 가지고 있는 세부 조항들 |
| **LIMITS** | `Provision` → `LegalTerm` | 특정 조항이 행위(예: 보조금 지급)를 제한하는가 |
| **SIMILAR_TO** | `Ordinance` → `Ordinance` | 지자체 간 내용이 유사한 조례 관계 |
| **SUPERIOR_TO** | `Statute` → `Ordinance` | 법적 위계질서 정의 |
| **REFERENCES** | `Provision` → `Provision` | 조문 간 인용 관계 |

---

## 5. 서비스 워크플로우 (Service Workflow)

1. **입력 단계:** 사용자가 조례 아이디어를 자연어로 입력.
2. **인터뷰 단계 (Loop):** * `State`를 확인하여 누락된 정보(지역, 지원대상 등)를 질문.
    - 온톨로지를 통해 "유사한 조례는 이런 조건이 있는데 참고하실까요?"라고 제안.
3. **검색 및 매핑:** 확정된 정보를 바탕으로 Graph DB에서 `BASED_ON` 관계에 있는 상위법 조항을 모두 추출.
4. **초안 작성:** 추출된 법적 근거를 바탕으로 조문(제1조~최종조) 생성.
5. **법률 검증:** 작성된 초안을 다시 한번 그래프의 `Restriction(제한)` 노드와 대조하여 위험 요소 고지.

---

## 5. 기술 스택 (Tech Stack)

- **LLM:**  Gemini 2.5 Pro (추론 및 작문용).
- **Orchestration:** LangChain & LangGraph (상태 기반 워크플로우).
- **Database:** Neo4j (Graph) & OpenAI Embedding (Vector).
- **Deployment:** Cloud Functions (Serverless) & Neo4j AuraDB.

---

## 6. 향후 확장 계획 (Roadmap)

- **1단계:** 특정 도메인(예: 신산업/기업지원) 조례 데이터 적재 및 PoC.
- **2단계:** Protégé를 활용한 고도화된 SWRL 논리 규칙(추론) 반영.
- **3단계:** 실제 법률 전문가 검토 피드백 반영 및 인간 협업 인터페이스 고도화.