# Code Review — Top 4 Issues (by business impact)

Prioritized findings from a read-only review of TaskBoard. Categories match the Part 1 rubric: Security, Performance, Architecture, Data Integrity, Testing.

---

## 1. SQL injection in task search (cross-project data leak)

| | |
|---|---|
| **File / line** | `backend/projects/views.py` lines 110–123 |
| **Category** | Security |
| **Severity** | Critical |

**Description**  
`TaskListCreateView.get` builds raw SQL with an f-string and interpolates the unsanitized `q` query parameter into `ILIKE '%{q}%'` before `cursor.execute`. Any authenticated project member (including a viewer) can break out of the intended `project_id` filter with a crafted `q` value. The ORM path without `q` stays correctly scoped; only the search branch is injectable.

**Business impact**  
Tenant isolation fails: users can read task titles, descriptions, assignees, and IDs from projects they are not members of. This is a direct confidentiality breach and must be fixed before any production use.

**Recommended fix**  
Remove the raw SQL path. Filter with the ORM using parameterized lookups, e.g. `Task.objects.filter(project_id=project_id).filter(Q(title__icontains=q) | Q(description__icontains=q))`, return the same `TaskSerializer` shape, and add a regression test that a member of project A cannot retrieve project B’s tasks via `?q=`.

### Bug proof (confirmed on localhost:8000)

`dev@example.com` is a **viewer** on **Q3 Launch** only (not a member of Customer Onboarding).

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"password123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

PROJECT_ID=$(curl -s http://localhost:8000/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['projects'][0]['id'])")

# Baseline: normal search (scoped)
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=analytics" \
  -H "Authorization: Bearer $TOKEN"

# Exploit: break out of project_id filter
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=x') OR 1=1 --" \
  -H "Authorization: Bearer $TOKEN"
```

**Baseline result (this session):** HTTP 200 — **1** task on Q3 Launch only (`Set up analytics dashboards`).

**Exploit result (this session):** HTTP 200 — **12** tasks across **2** distinct `project_id` values. ORM list without `q` for the same project returned **7** tasks. Injected search also returned Customer Onboarding tasks Dev is not allowed to see, including:

```json
{
  "tasks": [
    {
      "title": "Map current onboarding funnel",
      "project_id": "6be6b57b-e6e5-4396-b23e-c3388117131b"
    },
    {
      "title": "Interview 5 recently-onboarded customers",
      "project_id": "6be6b57b-e6e5-4396-b23e-c3388117131b"
    },
    {
      "title": "Set up analytics dashboards",
      "project_id": "e885422e-bf43-4b94-b0d6-00fcca221307"
    }
  ]
}
```

*(Project UUIDs change after re-seed; resolve via `GET /api/projects` for the logged-in user.)*

---

## 2. Missing authorization on task PATCH (IDOR)

| | |
|---|---|
| **File / line** | `backend/projects/views.py` lines 164–185 (contrast delete at 187–200) |
| **Category** | Security / Data Integrity |
| **Severity** | Critical |

**Description**  
`TaskDetailView.patch` loads a task by id and applies title, description, status, and assignee updates with **no** membership or role check. `delete` on the same view correctly requires membership and `_can_edit_tasks`, so PATCH is inconsistent and over-privileged. Any authenticated user—including non-members and viewers—can rewrite another project’s tasks if they know the task UUID.

**Business impact**  
Attackers or mistaken clients can silently sabotage boards (retitle work, mark items done, reassign ownership). Role-based trust (viewer = read-only) is broken, so delivery status and auditability become unreliable.

**Recommended fix**  
Reuse the delete guards: resolve membership for `task.project_id`, reject with 403 if missing or if role is not admin/member; validate assignee is a project member before save. Add tests for non-member PATCH → 403, viewer PATCH → 403, member PATCH → 200.

---

## 3. API naming mismatch silently unassigns tasks on save

| | |
|---|---|
| **File / line** | `backend/projects/serializers.py` lines 6–26, 46–48; `frontend/src/types/index.ts` lines 10–40; `frontend/src/components/TaskDetail.tsx` lines 19, 47–52; write path `backend/projects/views.py` lines 156, 180–181 |
| **Category** | Architecture / Data Integrity |
| **Severity** | High |

**Description**  
Project list responses are hand-built in camelCase (`taskCount`, `createdAt`), while task/project detail serializers emit Django snake_case (`assignee_id`, `project_id`, `created_at`). The UI types and `TaskDetail` read `assigneeId`. Board cards still render via nested `assignee`, but edit initializes `useState(task.assigneeId ?? "")` to empty against the real API and Save sends `assigneeId: null`; the backend write path accepts camelCase `assigneeId`, so a title-only save clears the assignee.

**Business impact**  
Routine edits erase assignment without the user changing the assignee control. Workload and ownership reports become wrong, and TypeScript does not catch it because `apiFetch` asserts types without runtime parsing. Frontend fixtures use camelCase, so CI stays green.

**Recommended fix**  
Enforce one naming convention at the API boundary (explicit camelCase serializer fields, or snake_case on the frontend). Keep list and detail consistent. Add a contract test using a real `TaskSerializer` payload so `TaskDetail` initial state matches the wire format.

---

## 4. Airtable export is a stub; tests miss high-risk paths

| | |
|---|---|
| **File / line** | `backend/projects/views.py` lines 234–243; `backend/projects/tests.py` (no search / PATCH-auth / export coverage); missing `backend/projects/airtable_mock.py` referenced in README |
| **Category** | Architecture / Testing |
| **Severity** | High |

**Description**  
`ExportView.post` authorizes admin/member then always returns `exported: 0` and serialized tasks without calling Airtable/`pyairtable`, despite README Part 3c requiring a real integration and a test double. Backend tests cover create/list/delete membership cases but never search SQL, PATCH authorization, or export behavior, so CI stays green while the Critical bugs above remain uncaught.

**Business impact**  
The mandated export workflow does not sync work to Airtable, so ops/product handoffs fail silently. False confidence from the test suite increases the chance that security and data-integrity defects ship.

**Recommended fix**  
Implement export with `pyairtable` behind a small service (real client in prod, mock in tests), handle re-runs and transient vs permanent Airtable errors, and add tests for membership, export count, search isolation, and PATCH authorization. Introduce the documented `airtable_mock.py` test double.

---

## Summary

| # | Issue | Category | Severity |
|---|--------|----------|----------|
| 1 | SQL injection in task search | Security | Critical |
| 2 | Missing auth on task PATCH | Security / Data Integrity | Critical |
| 3 | snake_case API vs camelCase UI (silent unassign) | Architecture / Data Integrity | High |
| 4 | Stub Airtable export + gaps in tests | Architecture / Testing | High |

Issue **#1** is the highest-priority fix candidate for Part 2 (confirmed exploitable with the curl proof above).
