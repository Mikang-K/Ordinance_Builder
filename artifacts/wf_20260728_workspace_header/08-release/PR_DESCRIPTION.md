# PR DESCRIPTION

- Workflow ID: `wf_20260728_workspace_header`
- Stage: `release_ready`
- Producing agent: `default`
- Source task ID: `task_workspace_header_release`
- Timestamp: `2026-07-28T16:13:00+09:00`
- Summary: 작업 화면 헤더 UI 개선 및 프로덕션 배포
- Inputs used: 구현, 테스트, UI/UX 리뷰 결과
- Open assumptions: 없음

## Changes

- 작업 헤더를 명확한 2단 정보 구조로 재편
- 데스크톱·태블릿·모바일 반응형 레이아웃 정리
- 모바일에서 핵심 작업과 AI 상태 접근성 유지
- 글자 크기를 작업 본문에만 적용해 헤더 재배치 방지
- 드래그 중 CSS 변수 미리보기, 조작 완료 시 한 번만 상태 저장
- 헤더와 조문 편집 슬라이더의 동작 계약 통일

## Deployment

- Firebase project: `ordinance-builder-b9f6c`
- Production URL: `https://ordinance-builder-b9f6c.web.app`
- Hosting version: `91d85f82c37c1fa6`

