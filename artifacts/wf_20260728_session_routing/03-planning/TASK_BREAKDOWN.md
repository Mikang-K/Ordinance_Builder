# TASK BREAKDOWN

- Workflow ID: `wf_20260728_session_routing`
- Stage: `task_planning`
- Producing agent: `default`
- Source task ID: `task_session_routing`
- Timestamp: `2026-07-28T15:45:00+09:00`
- Summary: 세션 목록과 작업 화면을 URL 기반으로 분리한다.
- Inputs used: `docs/01-plan/features/session-list-workspace-routing.plan.md`, `frontend/src/App.tsx`, `firebase.json`
- Open assumptions: Firebase Hosting의 SPA rewrite와 기존 세션 API를 유지한다.

## Tasks

1. Backend Architect가 세션 복원·인증·Hosting rewrite 호환성을 검토한다.
2. Frontend Developer가 `/`, `/sessions/new`, `/sessions/:sessionId` 라우팅을 구현한다.
3. 비동기 요청의 라우트 전환 경합과 취소 히스토리를 검토·수정한다.
4. 프로덕션 빌드와 Firebase Hosting 하위 경로를 검증한다.
5. Preview 채널 통과 후 Live 채널에 배포한다.

