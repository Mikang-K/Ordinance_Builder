# TEST_REPORT

- Workflow ID: `wf_20260728_workspace_document_tabs`
- Stage: `test`
- Producing agent: `root`
- Source task ID: `test_001`
- Timestamp: `2026-07-28T17:22:00+09:00`
- Summary: 백엔드 전체 테스트와 프런트엔드 프로덕션 빌드 통과
- Inputs used: 최종 구현 소스
- Open assumptions: 인증이 필요한 전체 사용자 E2E는 배포 후 실제 계정 회귀 확인 대상으로 남긴다.

## Results

- `python -m pytest -q`: 10 passed, Pydantic V2 deprecation warning 1건
- `python -m compileall -q app`: passed
- `frontend/npm.cmd run build`: passed
- 배포 정적 자산 확인: HTTP 200, `index-CPw1OzQl.js` 확인
- Hosting `/api/**` rewrite 확인: 인증 없는 API 요청이 백엔드 검증 응답 HTTP 422 반환

