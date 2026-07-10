# Plan: 최종 검토 결과 파일 저장 기능

**Feature**: `final-result-export`  
**Phase**: Plan  
**Created**: 2026-07-10  
**Roles**: Frontend Developer, Backend Architect

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| **문제** | 현재 완료된 조례 초안은 `CompletedDraftModal`에서 클립보드 복사만 가능하다. 사용자는 최종안과 법률 검토 결과를 별도 파일로 보관하거나 공유하기 어렵다. |
| **해결** | 완료 모달에 `TXT 저장`, `Word 저장` 액션을 추가하고, 백엔드에 인증된 세션 기반 export API를 설계해 `.txt`와 `.docx` 파일을 내려받을 수 있게 한다. |
| **핵심 UX** | 사용자는 최종 확정 후 완료 모달에서 복사, TXT 저장, Word 저장 중 원하는 방식을 선택한다. |
| **권장 구현** | TXT는 백엔드에서 UTF-8 텍스트 파일로 생성하고, Word는 백엔드에서 `.docx`로 생성한다. 이렇게 하면 브라우저별 다운로드 차이를 줄이고, 법률 검토 결과 포맷을 일관되게 유지할 수 있다. |

---

## 1. 현재 상태

### 관련 프론트엔드

| 파일 | 현재 역할 |
|------|-----------|
| `frontend/src/components/CompletedDraftModal.tsx` | 완료된 초안과 법률 검토 결과를 표시하고 `navigator.clipboard.writeText(draft)`로 복사만 제공 |
| `frontend/src/App.tsx` | `/finalize` 응답의 `draft`, `legal_issues`를 `CompletedDraftModal`에 전달 |
| `frontend/src/api.ts` | 세션 생성, 채팅, 최종 확정 API 래퍼 제공. 다운로드 API는 없음 |
| `frontend/src/types.ts` | `LegalIssue`, `FinalizeResponse` 등 타입 정의 |

### 관련 백엔드

| 파일 | 현재 역할 |
|------|-----------|
| `app/api/routers/chat.py` | `/api/v1/session/{session_id}/finalize`에서 세션을 `completed`로 전환하고 최종 초안과 법률 검토 결과 반환 |
| `app/api/schemas.py` | `FinalizeRequest`, `FinalizeResponse` 정의 |
| `app/db/session_store.py` | 세션 소유권 및 상태 조회에 필요한 저장소 함수 제공 |
| `requirements.txt` | 문서 생성 의존성 없음. Word `.docx` 생성을 위해 `python-docx` 추가 필요 |

---

## 2. 목표 범위

### 포함

1. 완료된 세션의 최종 초안과 법률 검토 결과를 파일로 저장
2. 저장 형식:
   - `.txt`: 최종 초안 본문 + 법률 검토 결과 요약
   - `.docx`: 제목, 최종 초안, 법률 검토 결과 섹션을 가진 Word 문서
3. 기존 복사 기능 유지
4. 인증된 사용자 본인 세션만 export 가능
5. 브라우저에서 파일명이 깨지지 않도록 `Content-Disposition` 처리

### 제외

1. PDF 저장
2. 사용자가 저장 전 문서 스타일을 편집하는 기능
3. 서버 영구 파일 저장
4. 세션 목록에서 일괄 다운로드
5. 미완료 세션 export. 단, 별도 요구가 있으면 `draft_review` 상태의 임시 초안 다운로드는 후속 기능으로 분리

---

## 3. Backend Architect 계획

### 3.1 API 계약

새 엔드포인트를 추가한다.

```http
GET /api/v1/session/{session_id}/export?format=txt
GET /api/v1/session/{session_id}/export?format=docx
```

요청 조건:

| 항목 | 정책 |
|------|------|
| 인증 | 기존 `get_current_user` 사용 |
| 소유권 | 기존 `_require_ownership(entry, user_id, sid)` 재사용 |
| 세션 상태 | 기본은 `entry["stage"] == "completed"`만 허용 |
| 형식 | `txt`, `docx`만 허용. 그 외는 400 |
| 데이터 출처 | LangGraph state의 `draft_full_text`, `legal_issues`, `is_legally_valid` |

응답:

| format | Content-Type | 파일명 예 |
|--------|--------------|----------|
| `txt` | `text/plain; charset=utf-8` | `ordinance-final-{session_id}.txt` |
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `ordinance-final-{session_id}.docx` |

### 3.2 문서 구성 규칙

TXT:

```text
조례 최종안
생성일시: ...
세션 ID: ...

[최종 초안]
...

[법률 검토 결과]
- 중대도: HIGH
  관련 조항: ...
  설명: ...
  제안: ...
```

DOCX:

1. 문서 제목: `조례 최종안`
2. 메타 정보: 세션 ID, 생성일시, 법률 검토 상태
3. `최종 초안` 섹션: 조례 본문을 줄바꿈 보존 방식으로 삽입
4. `법률 검토 결과` 섹션:
   - 이슈 없음: `발견된 법률 검토 이슈가 없습니다.`
   - 이슈 있음: 중대도, 관련 법령/조항, 설명, 제안을 항목별 표시

### 3.3 백엔드 구현 파일

| 파일 | 작업 |
|------|------|
| `app/api/routers/chat.py` | `/session/{session_id}/export` 라우트 추가 |
| `app/api/schemas.py` | 필요 시 `ExportFormat = Literal["txt", "docx"]` 타입 추가 |
| `requirements.txt` | `.docx` 생성을 위해 `python-docx>=1.1.2` 추가 |

### 3.4 백엔드 설계 세부

1. `graph.aget_state(config)`로 state를 읽는다.
2. `entry["stage"] != "completed"`이면 409 Conflict로 반환한다.
3. `draft_full_text`가 없으면 400 Bad Request로 반환한다.
4. TXT는 `io.BytesIO` 또는 문자열 인코딩으로 `StreamingResponse` 반환한다.
5. DOCX는 `Document()`로 메모리에서 생성하고 `BytesIO`로 반환한다.
6. 파일명은 ASCII fallback과 RFC 5987 `filename*`을 같이 제공한다.
7. 서버 디스크에는 파일을 저장하지 않는다.

### 3.5 백엔드 리스크

| 리스크 | 대응 |
|--------|------|
| 한국어 파일명 깨짐 | `Content-Disposition: attachment; filename="ordinance-final-..."; filename*=UTF-8''...` 사용 |
| Word 문서 줄바꿈 손실 | 초안 본문을 줄 단위 paragraph로 삽입하거나 run에 line break 적용 |
| 세션 state와 DB stage 불일치 | DB stage가 `completed`이고 state에 draft가 있을 때만 허용 |
| 의존성 추가 | `python-docx`는 작은 범위의 런타임 의존성이며 서버 측 문서 생성에만 사용 |

---

## 4. Frontend Developer 계획

### 4.1 UI 변경

`CompletedDraftModal` 헤더 액션을 다음처럼 확장한다.

현재:

```text
[복사] [닫기]
```

변경:

```text
[복사] [TXT 저장] [Word 저장] [닫기]
```

모바일에서는 버튼이 줄바꿈되더라도 겹치지 않도록 flex-wrap을 허용한다.

### 4.2 프론트엔드 데이터 흐름

`CompletedDraftModal`에 `sessionId`와 다운로드 핸들러를 전달한다.

```typescript
interface Props {
  sessionId: string
  draft: string
  legalIssues: LegalIssue[] | null
  onClose: () => void
}
```

`App.tsx`에서는 현재 `sessionIdRef.current`를 완료 모달에 넘긴다.

### 4.3 API 래퍼 추가

`frontend/src/api.ts`에 다운로드 함수를 추가한다.

```typescript
export async function downloadFinalResult(
  sessionId: string,
  format: 'txt' | 'docx',
): Promise<Blob>
```

작동 방식:

1. `GET /api/v1/session/{sessionId}/export?format=${format}` 호출
2. 인증 헤더 포함
3. `res.blob()` 반환
4. 실패 시 사용자에게 보여줄 수 있는 Error throw

다운로드 트리거는 유틸 함수로 분리한다.

```typescript
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
```

### 4.4 상태 및 피드백

`CompletedDraftModal` 내부에 다운로드 상태를 둔다.

```typescript
const [downloadingFormat, setDownloadingFormat] =
  useState<'txt' | 'docx' | null>(null)
```

UX 규칙:

| 상태 | 동작 |
|------|------|
| 다운로드 중 | 해당 버튼 disabled, 라벨을 `저장 중...`으로 변경 |
| 성공 | 별도 모달 없이 브라우저 다운로드 시작 |
| 실패 | 모달 내부 또는 기존 error bar에 `파일 저장에 실패했습니다.` 표시 |

### 4.5 프론트엔드 구현 파일

| 파일 | 작업 |
|------|------|
| `frontend/src/components/CompletedDraftModal.tsx` | TXT/Word 저장 버튼, 다운로드 상태, 오류 표시 추가 |
| `frontend/src/App.tsx` | `sessionId` 전달 |
| `frontend/src/api.ts` | export API 호출 함수 추가 |
| `frontend/src/App.css` | 다운로드 버튼 스타일 및 모바일 wrap 보정 |

---

## 5. 역할별 작업 분해

### Backend Architect

1. Export API 계약 확정
2. 세션 완료 여부와 소유권 검증 정책 정의
3. TXT/DOCX 문서 포맷 정의
4. `python-docx` 의존성 추가 여부 확정
5. `StreamingResponse` 기반 파일 반환 방식 설계
6. 백엔드 테스트 케이스 정의

### Frontend Developer

1. 완료 모달 액션 영역 UI 설계
2. 다운로드 API 래퍼 추가
3. Blob 다운로드 유틸 구현
4. 다운로드 중/실패 상태 처리
5. 모바일에서 버튼 줄바꿈과 텍스트 겹침 확인
6. 프론트엔드 빌드 및 수동 QA

---

## 6. 구현 순서

1. Backend: `python-docx` 의존성 추가
2. Backend: export 라우트 추가
3. Backend: TXT 생성 함수와 DOCX 생성 함수 작성
4. Backend: 인증/소유권/완료 상태 검증 적용
5. Frontend: `downloadFinalResult` API 함수 추가
6. Frontend: `CompletedDraftModal`에 `sessionId`, 저장 버튼, 상태 처리 추가
7. Frontend: CSS 보정
8. Verification: TXT와 DOCX 다운로드 수동 확인
9. Verification: `npm run build`와 가능한 백엔드 테스트 실행

---

## 7. 테스트 계획

### Backend

| 케이스 | 기대 결과 |
|--------|----------|
| 완료된 본인 세션 + `format=txt` | 200, `.txt` 다운로드 |
| 완료된 본인 세션 + `format=docx` | 200, `.docx` 다운로드 |
| 미완료 세션 | 409 |
| 다른 사용자 세션 | 403 |
| 없는 세션 | 404 |
| 잘못된 format | 400 |
| state에 draft 없음 | 400 |

### Frontend

| 케이스 | 기대 결과 |
|--------|----------|
| 완료 모달 표시 | 복사, TXT 저장, Word 저장 버튼 모두 표시 |
| TXT 저장 클릭 | `.txt` 파일 다운로드 시작 |
| Word 저장 클릭 | `.docx` 파일 다운로드 시작 |
| 다운로드 실패 | 사용자에게 오류 표시, 버튼 상태 복구 |
| 모바일 폭 | 버튼과 닫기 아이콘이 겹치지 않음 |

---

## 8. 성공 기준

1. 최종 확정 모달에서 기존 복사 기능이 유지된다.
2. TXT 저장 버튼으로 최종 초안과 법률 검토 결과가 포함된 `.txt` 파일을 받을 수 있다.
3. Word 저장 버튼으로 동일 내용을 포함한 `.docx` 파일을 받을 수 있다.
4. 완료되지 않은 세션에서는 export가 차단된다.
5. 다른 사용자의 세션 export가 차단된다.
6. 다운로드 실패 시 UI가 멈추지 않고 오류를 표시한다.
7. 프론트엔드 빌드가 통과한다.

---

## 9. 후속 고려

1. `PDF 저장` 추가
2. 기관 로고, 문서 번호, 작성자 등 Word 템플릿 적용
3. 세션 목록 화면에서 완료된 세션 바로 다운로드
4. 법률 검토 결과만 별도 보고서로 저장
5. 서버가 아닌 브라우저 단독 TXT 저장 fallback 제공
