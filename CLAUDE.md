# Working in this repo

## THE RULE: all data access goes behind the data layer

**Every read of a scoped model goes through a repository in `backend/app/data/`.
Routes do not call `db.query(Model)` directly.**

This is enforced, not advised — `backend/tests/test_data_layer_contract.py`
fails the build otherwise. Do not weaken the test to make a change pass.

### Why

Raw `db.query(...)` calls scattered across route files, each hand-writing its
own studio filter, is how this class of bug ships in practice. A correct
helper can exist and still not help — if calling it is *optional*, endpoints
drift:

* some merge in an `OR studio_id IS NULL` clause that leaks studio-less rows
  into every studio's lists;
* some ship with no filter at all;
* the drift goes unnoticed until an entity-by-entity audit finds it, usually
  in the one area nobody thought to check.

An optional helper cannot prevent that class of bug. A repository that
*cannot be constructed without a scope*, and has no code path returning an
unfiltered query, can.

A repo-level guard only proves the repos themselves are correct — it never
issues an HTTP request, so it cannot see an endpoint that bypasses the repo
entirely: a by-id route that queries the model directly, or an admin action
that accepts a target id without checking who owns it. Those are privilege
escalations, not just visibility leaks, and they need their own guard — see
the HTTP isolation test below.

### How to add a new entity

1. Add the model to `MODEL_SCOPE` in `tests/test_data_layer_contract.py` with
   an explicit decision. There is no default — the test fails until you choose:
   * `studio` — has `studio_id`; read via `StudioScopedRepo` (e.g. the
     question threads in `models/user_question.py` carry `studio_id`)
   * `franchise` — has `franchise_id`; NULL means a shared standard (deliberate)
   * `derived` — no scope column; only safe through its parent's repo
   * `unscoped: <reason>` — genuinely global. The reason is mandatory (e.g.
     the login-broadcast notes in `models/user_note.py` are unscoped on
     purpose — they're meant for every signed-in staff user, not one studio)
2. Write the repo in `backend/app/data/`. See `client_exercise_notes.py` for a
   derived entity that authorizes *both* parent ids before touching a row —
   the general pattern for any entity reachable only through two owners.
3. Keep the route thin: `repo: XRepo = Depends(x_repo)`, no queries.
4. Add HTTP-level cases to `tests/test_studio_isolation_http.py`.

### The scoping rules themselves

* **Studio axis** — a row with NULL `studio_id` is **invisible**. No fallback,
  no shared bucket.
* **Franchise axis** — NULL `franchise_id` DOES mean "shared standard, visible
  to everyone." Deliberately the *opposite* of the studio axis; conflating the
  two is how the original leaks happened. Pick the NULL semantics for each
  axis on purpose, write them down, and never let a repo guess.
* **By id is not exempt.** A by-primary-key fetch of another studio's row
  must return **404**, never 200 and never 403 — whether a record exists
  elsewhere is not the caller's business.
* **`X-Studio-Id` binds admins too.** An admin operating inside a studio is
  scoped to it exactly like that studio's own staff. "Admin" means more
  visibility across studios when none is selected, never an escape hatch from
  the one currently in scope.

Forking this for a different hierarchy? Rename `studio`/`franchise` to match
yours — the two-axis *shape* (one strict scope where NULL is invisible, plus
one looser scope where NULL is a shared default) is the part worth keeping.

## The guards

| test | what it catches |
|---|---|
| `tests/test_data_layer_contract.py` | raw reads outside `app/data/`; every model must declare a scope; the legacy budget may only shrink |
| `tests/test_no_unscoped_queries.py` | AST check on `routes/` for the core scoped models |
| `tests/test_studio_isolation_http.py` | isolation **over HTTP** — catches endpoints that bypass the repo entirely |
| `tests/test_studio_scoping.py` | the repo layer's own behaviour |

`LEGACY_BUDGET` in the contract test records pre-existing debt (a fixed count
of file/model pairs that predate the rule) so it can shrink over time without
blocking unrelated work. **A number may only go down.** Never add an entry
for new code — fix the code instead.

## Running things

Backend tests run in the `backend` container against a disposable test
database — no local Python venv needed:

```bash
docker compose run --rm \
  -e TEST_DATABASE_URL=postgresql://postgres:postgres@db/mickeymouse_test \
  -e JWT_SECRET=dev-secret-change-in-production -e JWT_ALGORITHM=HS256 \
  backend python -m pytest -q
```

Frontend:

```bash
cd frontend
npm install
npm run lint
npm run build
```

Playwright end-to-end needs a dev server serving **this** checkout — point
`E2E_PORT` at it explicitly rather than assuming a default port is yours.
Verify what a port actually serves before trusting a run against it; a stale
bundle from a different checkout or branch produces failures that look like
real bugs but aren't.

## The task board

Use GitHub Issues on this repo as the live board. No work starts without an
issue, and status is updated on the issue as work moves.

```bash
gh issue list --state open                # the backlog
gh issue create --title ... --label ...   # before starting anything
```

Suggested labels: `bug` · `feature` · `tech-debt` · `owner-action` ·
`owner-decision`.

Why an Issues board and not a file in the repo: when several agents or
contributors work the same codebase in parallel (separate branches or
worktrees), a file-based board forks per copy and the copies drift. Issues
are a single shared source of truth no local checkout can fork.

An issue should carry three things, not one:

* **status** — and "done" means *ran it and read the output*, distinct from
  "done but unverified". Close an issue only with evidence in the closing
  comment;
* **evidence** — the command, the test name, the number. Not an assurance;
* **file ownership** when work is parallelised (comment on the issue), so two
  contributors don't collide on the same files.

Board claims go stale: verify an issue's premise against the current code
before building from it, and cite commit hashes or `file:line` in comments so
the next reader can re-verify without re-deriving your work.
