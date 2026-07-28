# PR Description

- Workflow ID: `wf_20260727_evidence_library`
- Stage: `release`
- Producing agent: `default`
- Source task ID: `task_evidence_release_001`
- Timestamp: `2026-07-27T17:45:00+09:00`
- Summary: Add a session-persistent evidence library and safe current-article application workflow.
- Inputs used: Approved feature plan, implementation, tests, and review.
- Open assumptions: Cloud Run deployment triggers the idempotent PostgreSQL migration during startup.

## Changes

- Add `evidence_library` JSONB storage to sessions.
- Add ownership-protected evidence list, create, update, delete, and applied-state APIs.
- Add Q&A and evidence tabs with source saving and deletion.
- Add editable append/replace preview, duplicate warning, undo, and applied-state tracking.
- Add responsive and accessible evidence UI.
- Expand CORS methods for evidence updates.

## Verification

- Backend focused tests: 5 passed.
- Python compilation: passed.
- Frontend production build: passed.

## Deployment Order

1. Deploy Cloud Run backend and verify readiness.
2. Confirm the evidence API is reachable through the hosting rewrite.
3. Deploy Firebase Hosting.
4. Verify the public frontend response and backend health.
