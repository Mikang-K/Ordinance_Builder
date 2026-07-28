# PR_DESCRIPTION

- Workflow ID: `wf_20260728_workspace_document_tabs`
- Stage: `release`
- Producing agent: `root`
- Source task ID: `release_001`
- Timestamp: `2026-07-28T17:22:00+09:00`
- Summary: 조례 문서 통합 작업공간과 안전한 재작성·재확정 흐름 배포
- Inputs used: 구현, 테스트, 리뷰 결과
- Open assumptions: 개정 스냅샷 수명은 LangGraph 체크포인트 보존 정책을 따른다.

## Changes

- 상세 조례, 조례 초안, 확정 조례를 동일 작업공간 탭으로 통합
- 탭 URL 복원과 키보드 접근성 지원
- 완료 세션에서 이전 상세 입력과 초안 조회 및 새 개정 분기
- 상세 수정 후 초안 재생성, 초안 수정 후 법률 검토 무효화·재검토
- 법률 검토를 받은 동일 초안만 확정
- 새 개정 중 기존 확정본 조회·내보내기 유지
- 동시 수정, 부분 실패, 오래된 비동기 응답 방어

## Production

- Cloud Build: `949b3061-5e41-4456-b1dd-8293f2764b39`
- Container digest: `sha256:adb1473a616b5769761ff8352eacc3e7f1a19b5ea684c6bc651c5d50cfb1b7a8`
- Cloud Run revision: `ordinance-backend-00056-w7d`, traffic 100%
- Firebase Hosting version: `a549b7ca9a8193fb`
- Production URL: `https://ordinance-builder-b9f6c.web.app`

