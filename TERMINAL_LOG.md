# TERMINAL_LOG.md

Chronological log of this assessment session. Commands and outputs below were captured from the live environment on this machine. Secrets are not printed.

---

## 1. Baseline verification

Services were already running:

```text
NAME                     IMAGE                  SERVICE    STATUS
q-taskboard-backend-1    q-taskboard-backend    backend    Up
q-taskboard-db-1         postgres:16-alpine     db         Up
q-taskboard-frontend-1   q-taskboard-frontend   frontend   Up
```

```bash
curl -s http://localhost:8000/api/health
```

```json
{"ok": true}
```

Migrations (later in session, after Part 3a/3c):

```text
projects
 [X] 0001_initial
 [X] 0002_comment
 [X] 0003_task_airtable_record_id
```

---

## 2. Baseline tests (before SQLi fix)

```bash
docker compose exec backend python -m pytest
```

```text
collected 15 items
projects/tests.py .......
users/tests.py ........
15 passed, 16 warnings in 8.82s
```

```bash
docker compose exec frontend npm test -- --run
```

```text
✓ src/tests/TaskCard.test.tsx (3)
✓ src/tests/schemas.test.ts (6)
Test Files  2 passed (2)
Tests  9 passed (9)
```

---

## 3. Bug reproduction (SQL injection — before fix)

Authenticated as viewer `dev@example.com` on Q3 Launch only.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"password123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

PROJECT_ID=$(curl -s http://localhost:8000/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['projects'][0]['id'])")
# PROJECT_ID=e885422e-bf43-4b94-b0d6-00fcca221307  (Q3 Launch)
```

Safe search:

```bash
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=analytics" \
  -H "Authorization: Bearer $TOKEN"
```

**Result:** `count=1` — `Set up analytics dashboards` (project `e885422e-…` only).

ORM list (no `q`):

```text
count=7
```

Injection:

```bash
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=x') OR 1=1 --" \
  -H "Authorization: Bearer $TOKEN"
```

**Result (before fix):** HTTP 200 — `count=12`, `distinct_project_ids=2`  
(`e885422e-…` Q3 Launch + `6be6b57b-…` Customer Onboarding). Titles included Onboarding tasks Dev is not a member of (e.g. `Map current onboarding funnel`).

---

## 4. Fix curl and response (after SQLi fix)

Same commands as above, after replacing raw SQL search with ORM `icontains` filters.

```bash
# analytics
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=analytics" \
  -H "Authorization: Bearer $TOKEN"
```

**Result:** `count=1` — `['Set up analytics dashboards']`

```bash
# injection payload
curl -s -G "http://localhost:8000/api/projects/${PROJECT_ID}/tasks" \
  --data-urlencode "q=x') OR 1=1 --" \
  -H "Authorization: Bearer $TOKEN"
```

**Result (after fix):** `count=0`, `projects=[]` (literal search; no cross-project leak).

Regression tests added and run:

```bash
docker compose exec backend python -m pytest projects/tests.py -q
```

```text
9 passed   # projects suite right after fix (includes search tests)
```

User terminal after fix commit:

```bash
docker compose exec backend python -m pytest
```

```text
collected 17 items
17 passed, 20 warnings in 7.90s
```

---

## 5. Implementation testing — Part 3a comments

```bash
git commit -m "feat: add project comments"
# 9fc24a1
```

```bash
docker compose exec backend python -m pytest
```

```text
collected 25 items
projects/tests.py .................
users/tests.py ........
25 passed, 32 warnings in 11.60s
```

(Frontend comment tests appeared in later full frontend runs — see final tests.)

---

## 6. Airtable config check (no secrets printed)

```bash
docker compose up -d --force-recreate backend
```

```text
Container q-taskboard-backend-1  Recreated
Container q-taskboard-backend-1  Started
```

```text
health={"ok": true}
AIRTABLE_API_KEY_set= True
AIRTABLE_BASE_ID_prefix= appGjMKi
AIRTABLE_TABLE_NAME= tblLQ0unmCM0VOAEt
```

Meera’s projects at export time:

```text
5471f00e-… Internal Tools Cleanup          taskCount=1  admin
6be6b57b-… Customer Onboarding Revamp      taskCount=5  member
e885422e-… Q3 Launch                       taskCount=7  admin
```

---

## 7. Airtable first export (Q3 Launch)

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"meera@taskboard.dev","password":"password123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

Q3=e885422e-bf43-4b94-b0d6-00fcca221307

curl -s -X POST "http://localhost:8000/api/projects/${Q3}/export" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```python
{'exported': 7, 'created': 7, 'updated': 0, 'failed': [], 'error': None}
```

---

## 8. Airtable second export (same project — repeat-safe)

```bash
curl -s -X POST "http://localhost:8000/api/projects/${Q3}/export" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```python
{'exported': 7, 'created': 0, 'updated': 7, 'failed': [], 'error': None}
```

(Second run updated existing Airtable records; no duplicate creates.)

Also observed earlier when exporting `projects[0]` (Internal Tools Cleanup, 1 task): both runs returned `exported: 1, created: 0, updated: 1, failed: []` HTTP 200.

---

## 9. Final tests

```bash
docker compose exec -T backend python -m pytest -q
```

```text
25 passed, 32 warnings in 12.15s
```

```bash
docker compose exec -T frontend npm test -- --run
```

```text
✓ src/tests/schemas.test.ts (6)
✓ src/tests/ExportTasksButton.test.tsx (2)
✓ src/tests/TaskCard.test.tsx (3)
✓ src/tests/TaskComments.test.tsx (3)
Test Files  4 passed (4)
Tests  14 passed (14)
```

---

## 10. Final git status

```bash
git status
git log --oneline -8
```

```text
On branch master
Your branch and 'origin/master' have diverged,
and have 4 and 5 different commits each, respectively.

nothing to commit, working tree clean

631aa09 feat: add airtable export feature
9fc24a1 feat: add project comments
56150ad fix: enforce task authorization
7e8b951 docs: add engineering review
d85576b chore: fix frontend type dependencies
5ae6587 remove ASSIGNMENT.md
84cb1a6 fix: use API_TARGET env var for Vite proxy so Docker networking works
32caa63 Initial commit
```

---

## Session commit trail (this assessment)

| Commit     | Message |
|------------|---------|
| `7e8b951`  | docs: add engineering review |
| `56150ad`  | fix: enforce task authorization |
| `9fc24a1`  | feat: add project comments |
| `631aa09`  | feat: add airtable export feature |
