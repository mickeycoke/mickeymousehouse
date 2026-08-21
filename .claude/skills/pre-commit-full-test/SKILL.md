---
name: pre-commit-full-test
description: Full end-to-end verification gate — run before every commit and before every deploy. Backend suite + frontend lint/build + end-to-end tests, with evidence. Use whenever about to commit, merge, push, or deploy, or when asked "is this ready", "did you test it", or "can we ship".
---

# Pre-commit / pre-deploy full test gate

**This gate is not optional and it is not partial.** A green unit suite
proves the units are correct — it says nothing about whether an endpoint
actually enforces the access rules it's supposed to. This repo has guard
tests specifically because a passing test suite and a real security hole
have coexisted before: a static/AST check can be green while an HTTP
endpoint still leaks, because the static check never issues a request.

## The stages — all of them, every time

Never report "tests pass" unless every applicable stage ran. If a stage
can't run, **say so explicitly and name what blocked it**. Silence reads as
"it passed."

### 1. Backend suite — whole thing, no subsets

```bash
docker compose run --rm backend python -m pytest -q
```

Report `N passed / M failed`. Running a subset and calling it done defeats
the point — a change in one module can break assumptions in another that a
scoped run would never touch.

### 2. Frontend lint + build

```bash
cd frontend
npm run lint
npm run build
```

A build that fails to compile is not a deployable change, no matter how the
unit tests look.

### 3. End-to-end tests

```bash
cd frontend && npm run test:e2e
```

Needs a dev server pointed at **this** checkout and a seeded database — a
stale bundle from a different branch or checkout can produce failures that
look real but aren't. Verify what the server under test is actually serving
before trusting a failure count.

### 4. Live API probe of everything the change touches

Automated coverage that never exercises HTTP cannot catch endpoint-level
bugs — this is exactly the gap the HTTP isolation guard tests exist to close
(see `CLAUDE.md`). For each touched endpoint, verify by hand:

- the happy path returns the expected shape;
- **scoping**: send the active-scope header for one studio and confirm
  another studio's rows are absent, and that a by-id fetch of another
  studio's row returns **404**, not 200;
- **NULL-scope policy**: no row with a NULL studio-scope column appears in a
  studio-scoped list;
- any contract change (a field renamed, an endpoint that became a list,
  etc.) is actually reflected in the response.

## Distinguishing real failures from load noise

A large seeded dataset can make endpoints slow enough that a short test
timeout fails a test that is functionally correct. A failure set that
changes shape between runs — different tests fail each time — is usually a
load or timing problem, not a regression. A failure that reproduces in the
same place every run is a real bug. Diagnose which one you're looking at
before reporting either way, and check whether a failing spec is simply
stale against a UI change that already shipped.

## Before a deploy, additionally

- [ ] All stages above green
- [ ] Change reviewed (self-review at minimum; a second reviewer if one is
      available)
- [ ] A rollback path stated in writing
- [ ] Migrations rehearsed against a non-production database first, with
      row-count assertions before/after

## UI rulings become permanent tests

When a maintainer states a UI or product rule out loud — "this behavior is
correct" or "this is wrong, fix it" — that rule should become a test the
same day, not stay as something only remembered in conversation:

1. Write down the rule (a comment near the test is enough; a project-level
   ledger works too if the team wants one).
2. Write or extend the test that asserts it.
3. If it can't be tested yet, say so explicitly rather than leaving it
   silently uncovered.

A UI test passing is not proof a rule holds end-to-end — list-level coverage
can pass while a by-id endpoint still leaks the same data. Pair every UI
rule with the API-level probe in stage 4, not just a component or page test.

## Reporting rules

State real numbers. Name every stage that did not run and why. If something
is broken, say so with the output. "The suite passed" is not the same claim
as "I verified the change works" — report the one you actually did.
