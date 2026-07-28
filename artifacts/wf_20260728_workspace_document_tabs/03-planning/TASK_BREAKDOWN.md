# TASK_BREAKDOWN

- Workflow ID: `wf_20260728_workspace_document_tabs`
- Stage: `task_planning`
- Producing agent: `root`
- Source task ID: `planning_001`
- Timestamp: `2026-07-28T17:22:00+09:00`
- Summary: 상세 조례·초안·확정본을 통합 작업공간으로 구성하고 개정 흐름을 구현한다.
- Inputs used: `docs/01-plan/features/workspace-document-tabs-revision.plan.md`, 현행 프런트엔드 및 API 코드
- Open assumptions: LangGraph 체크포인트의 운영 보존 정책을 개정 데이터 보존 정책으로 사용한다.

## Tasks

1. Frontend Developer: 세 문서 탭, URL 복원, embedded 확정 패널, 개정 API 연결
2. Backend Architect: 개정 스냅샷, 상세/초안 수정, 재검토, 해시 기반 확정 API
3. Root: 동시 수정 직렬화, 확정본 내보내기 보존, 부분 실패 및 세션 전환 방어
4. Reviewer: 정확성·보안·회귀 검토와 차단 이슈 재검증
5. Root: 전체 테스트, Cloud Run/Firebase Hosting 배포 및 운영 확인

