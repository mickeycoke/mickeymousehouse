# Mickeymouse House

A store-engine starter kit: a FastAPI + React application with franchise →
studio → product multi-tenancy, Stripe billing wired in from day one, and an
AI-assisted development framework baked into the repo so an agent working on
your fork inherits the same guardrails a human contributor would follow.

Fork it, rename the hierarchy to match your business, and start adding your
own models — the scoping pattern and the guard tests that enforce it come
along for free.

## Why this exists

Most multi-tenant apps leak data the same way: a raw query somewhere forgets
the tenant filter, or a by-id endpoint doesn't check who owns the row. Here
that class of bug is structurally hard to introduce — see
[`CLAUDE.md`](CLAUDE.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for the full reasoning, but the short version: no repository can be
constructed without an access scope, and a battery of tests fails the build
if a route reaches around the data layer to query a model directly.

## Features

- **A data layer that can't be bypassed** — every scoped read goes through a
  repository in `backend/app/data/`; routes stay thin. Four guard tests
  (static analysis, an AST check, repo-level tests, and HTTP-level isolation
  tests) fail the build on any regression.
- **Two-axis scoping, NULL semantics chosen on purpose** — a studio-scoped
  row with no studio is invisible; a franchise-scoped row with no franchise
  is a shared standard visible to everyone. Deliberately opposite, and
  documented so nobody has to guess.
- **Franchise → studio → product hierarchy** with role-based access (admin /
  manager / instructor staff roles, plus a separate customer portal role).
- **Stripe billing wired in**, keys read from environment only, dormant (not
  erroring) until both a feature flag and a key are configured.
- **A messaging engine, three parts**: broadcast announcements shown to
  every signed-in staff user at login; private two-way question threads
  (with file attachments) between a user and admin support; and pluggable
  transactional email for invites/password resets — logged to the console
  with zero provider setup by default, switched to a real provider with an
  env var and no code change.
- **Admin impersonation, with an audit trail** — an admin can act as another
  user for support/debugging; the session is a normal scoped token, not a
  standing backdoor, and it always carries the driving admin's identity so
  what they did is attributable after the fact.
- **Shared-device login** — a front-desk-tablet flow (studio code → pick your
  name → PIN) for staff who share one device, minting a short-lived,
  studio-scoped token. PIN checks run at constant time whether or not the
  user exists, so a login attempt can't be used to enumerate valid names.
- **An AI development framework** — `CLAUDE.md` conventions plus Claude Code
  skills under `.claude/skills/`, so an AI coding agent working in this repo
  picks up the same rules and guardrails a human contributor follows.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  frontend/   │ ───▶ │   backend/   │ ───▶ │  Postgres   │
│  React+Vite  │ HTTP │   FastAPI    │ ORM  │             │
└─────────────┘      └──────────────┘      └─────────────┘
                             │
                             ▼
                        Stripe API
```

- **Backend**: FastAPI, SQLAlchemy, Alembic migrations, pytest. Layered as
  `routes/` → `data/` (repositories) → `models/` — see
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **Frontend**: React + Vite, with a thin `api/` layer mirroring the
  backend's resources so pages never talk to raw endpoints directly.
- **Database**: Postgres, run via Docker Compose for local dev.
- **Billing**: Stripe, keys from environment (`.env`) only — never
  hardcoded, never committed.

## Quickstart

```bash
# 1. Bring up Postgres + the backend
docker compose up -d

# 2. Apply the schema
docker compose run --rm backend alembic upgrade head

# 3. Seed demo data
docker compose run --rm backend python scripts/seed_demo.py

# 4. Run the frontend
cd frontend
npm install
npm run dev
```

The seed script creates a franchise ("Demo Franchise"), a studio under it
("Demo Studio"), a product ("Sample Product"), and a welcome announcement
note (so the login broadcast has something to show immediately), plus:

```
Admin login:
  email:    admin@example.com
  password: admin123

Shared-device login (front-desk tablet flow):
  studio code:    DEMO1
  instructor PIN: 1234
```

Open the frontend dev server (printed on `npm run dev`, typically
`http://localhost:5173`) and sign in — or try the shared-device flow to see a
studio-scoped session minted without a password.

Copy [`.env.example`](.env.example) to `.env` first and fill in anything you
need beyond the defaults — the app runs with Stripe billing off out of the
box, so you only need real keys once you're ready to test payments.

## How the guard tests work

The data-layer rule (`CLAUDE.md`) is enforced by four tests in
`backend/tests/`, not just documented:

- a static check that every scoped model is declared in `MODEL_SCOPE` and
  that no route reads it outside `app/data/`;
- an AST-based check over `routes/` for the core scoped models;
- repo-level tests of the scoping logic itself;
- HTTP-level isolation tests that catch an endpoint bypassing the repo
  entirely — including by-id leaks and privilege escalation, which the
  static and repo-level tests can't see because they never issue a request.

Run them with `docker compose run --rm backend python -m pytest -q`. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for what each one catches.

## AI development framework

[`CLAUDE.md`](CLAUDE.md) is the entry point an AI coding agent (or a human)
reads first: the data-layer rule, how to add a new scoped entity, and how to
run the test suite. [`.claude/skills/`](.claude/skills/) holds operator
skills — packaged, repo-specific playbooks an agent loads for a recurring
task (see `pre-commit-full-test`, the mandatory pre-commit verification gate,
and `.claude/skills/README.md` for the pattern behind writing your own).
`.claude/settings.json` and `.claude/launch.json` configure a sensible
default permission allowlist and a frontend dev-server launch config.

The idea: an agent cloning this repo to build a different product should
inherit real guardrails from the first prompt, not rediscover them by
tripping the guard tests.

## Make it yours

1. **Rename the hierarchy.** `franchise` / `studio` / product are this
   starter's business shape. Rename the models, routes, and the two scoping
   axes in `MODEL_SCOPE` to match yours — the pattern that's worth keeping is
   the *shape* (one strict scope where NULL is invisible, one looser scope
   where NULL is a shared default), not the specific names.
2. **Add your own models** through the same flow every time: declare the
   scope in `backend/tests/test_data_layer_contract.py`'s `MODEL_SCOPE`,
   write a repository in `backend/app/data/`, keep the route thin, add HTTP
   isolation test cases. `CLAUDE.md` has the full steps.
3. **Plug in your own Stripe keys** via `.env` (see `.env.example`) — nothing
   Stripe-related is hardcoded, and the billing routes stay dormant until
   both a feature flag and `STRIPE_SECRET_KEY` are set.

## License

MIT — see [`LICENSE`](LICENSE).
