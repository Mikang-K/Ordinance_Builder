# Evidence Library Task Breakdown

- Workflow ID: `wf_20260727_evidence_library`
- Stage: `task_planning`
- Producing agent: `default`
- Source task ID: `task_evidence_plan_001`
- Timestamp: `2026-07-27T17:30:00+09:00`
- Summary: Implement and deploy a session-persistent evidence library with safe current-article application.
- Inputs used: Approved implementation plan and existing Q&A/article workspace.
- Open assumptions: Evidence is stored per session in PostgreSQL JSONB; append is the default application mode.

## Tasks

1. Backend Architect: add idempotent schema migration, evidence models, persistence helpers, ownership-scoped CRUD, deduplication, and applied-state API.
2. Frontend Developer: add Q&A/evidence tabs, save/delete flows, application preview, append/replace behavior, duplicate protection, undo, and responsive accessible styling.
3. Integration: verify frontend build, Python compile/tests, authorization boundaries, session restoration, and API compatibility.
4. Review: resolve blocking correctness, security, accessibility, and regression findings.
5. Release: deploy Cloud Run backend first, verify schema/API health, deploy Firebase Hosting, and verify public endpoints.

## Completion Criteria

- Evidence survives reload and remains isolated by session owner.
- Duplicate evidence is not created.
- Evidence can be appended to or replace the current article only after preview.
- Application can be undone before article submission.
- Existing Q&A, article drafting, legal review, and session flows remain functional.
- Backend and frontend production deployments complete successfully.
