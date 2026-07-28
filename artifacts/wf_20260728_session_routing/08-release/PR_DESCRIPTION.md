# PR DESCRIPTION

- Workflow ID: `wf_20260728_session_routing`
- Stage: `release_ready`
- Producing agent: `default`
- Source task ID: `task_routing_release`
- Timestamp: `2026-07-28T15:45:00+09:00`
- Summary: 목록과 작업 화면을 URL 기반으로 분리하고 Firebase Hosting에 배포
- Inputs used: 구현·테스트·리뷰 결과
- Open assumptions: 없음

## Changes

- `/`: 세션 목록
- `/sessions/new`: 신규 작업 온보딩
- `/sessions/:sessionId`: 기존 작업 복원
- 브라우저 뒤로/앞으로가기 및 직접 새로고침 지원
- 세션 생성 성공 후 실제 세션 URL로 replace 이동
- 라우트 전환 뒤 지연 비동기 응답 무시

## Verification

- TypeScript 및 Vite production build 통과
- Firebase Emulator, Preview, Production의 직접 하위 경로 응답 통과
- 최종 코드 리뷰 통과

## Deployment

- Firebase project: `ordinance-builder-b9f6c`
- Production URL: `https://ordinance-builder-b9f6c.web.app`
- Hosting version: `065514c0424d5247`

