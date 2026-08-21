# Architecture

Mickeymouse House is a store engine: a franchise owns studios, a studio sells
products, and every layer of the stack — data access, auth, and billing — is
built around keeping one studio's data invisible to another's by construction,
not by convention.

## Layered design

```
routes/  →  data/ (repositories)  →  models/
```

* **`backend/app/models/`** — SQLAlchemy models. Plain column definitions;
  no query logic lives here.
* **`backend/app/data/`** — the data layer. Every read and write of a scoped
  model goes through a repository here. A repository cannot be constructed
  without an `AccessScope` (see below), and has no code path that returns an
  unfiltered query.
* **`backend/app/routes/`** — FastAPI routers. Thin by design: a route
  depends on a repo (`repo: XRepo = Depends(x_repo)`) and calls its methods.
  It never queries a model directly. `CLAUDE.md` documents this rule and how
  to extend it to a new entity.

The dependency direction only ever points one way, top to bottom. A route
that reaches past its repo into `db.query(Model)` is the exact bug class this
layering exists to make impossible to merge — see the guard tests below.

## The two-axis scoping model

Every row that isn't global data sits on one (or both) of two axes, and the
two axes have **opposite** NULL semantics on purpose:

| axis | column | NULL means | enforced by |
|---|---|---|---|
| Studio | `studio_id` | **invisible** — no fallback, no shared bucket | `StudioScopedRepo` |
| Franchise | `franchise_id` | **shared standard** — visible to every franchise | `FranchiseScopedRepo` |

Conflating the two is the single most common way this kind of system leaks
data: a "helpful" `OR studio_id IS NULL` clause copied from a franchise-scoped
query into a studio-scoped one turns "invisible" into "visible to everyone."

A third category, **derived** entities, has no scope column of its own (for
example, a row reachable only via a client *and* an exercise). These are the
subtlest leaks — querying the model directly bypasses every check with
nothing to warn you — so `DerivedScopeRepo` enforces the parent join instead
of trusting the caller. See `backend/app/data/base.py` for all three base
classes and `backend/app/data/client_exercise_notes.py` for a derived repo
that authorizes both parent ids before touching a row.

Resolution of "what can this request see" happens once per request, in
`backend/app/data/scope.py`, and the result (`AccessScope`) is handed to every
repo the request uses — so the answer is computed the same way everywhere,
not re-derived per endpoint.

**By-id fetches are not exempt.** A request for another studio's row by
primary key returns 404, never 200 (data exists, just not for you) and never
403 (which would confirm the row exists). Whether a record exists outside the
caller's scope is not information the caller is entitled to.

**The active-scope header (`X-Studio-Id`) binds admins too.** An admin
operating inside a studio is scoped to it exactly like that studio's own
staff — admin privilege means broader visibility when no studio is selected,
never an escape hatch from the one currently active.

## Guard-test strategy

Four tests, each catching a different failure mode a single kind of test
would miss:

| test | layer | catches |
|---|---|---|
| `test_data_layer_contract.py` | static | raw `db.query()` calls outside `app/data/`; every model must declare a scope in `MODEL_SCOPE`; a shrinking legacy-debt budget |
| `test_no_unscoped_queries.py` | static (AST) | the same thing, specifically for the core scoped models, by parsing `routes/` rather than grepping it |
| `test_studio_scoping.py` | repo-level | the repositories' own filtering behavior, in isolation |
| `test_studio_isolation_http.py` | HTTP | isolation as an actual client would see it — the only layer that catches an endpoint that bypasses the repo entirely, including by-id leaks and privilege escalation on admin-assignment endpoints |

The static and repo-level tests can all be green while an endpoint still
leaks — they never issue a request. The HTTP-level suite is what actually
proves an endpoint is safe; treat the other three as necessary, not
sufficient.

## Auth roles

Base roles are `admin`, `manager`, `instructor` (staff), and a portal-only
`client` role. A user can hold more than one *kind* of standing simultaneously
— a base role, plus studio ownership/management, plus franchise ownership,
plus a client portal link — because in practice the same person often wears
several hats. `backend/app/routes/roles.py` exposes a summary of everything a
given user holds.

Staff roles (`admin`, `manager`, `instructor`) get the broader repo access an
`AccessScope` can grant; the `client` portal role never gets unrestricted
visibility even when it has no studio attachment — it's clamped to "see
nothing" at the repo layer and served through dedicated portal endpoints with
their own per-record checks instead.

### Three ways in, one audit trail

There are three distinct ways to obtain an access token, and every one of
them — success or failure — is written to a single login-event log
(`backend/app/models/login_event.py`), typed by `event_type`:

1. **Email + password** (`event_type="password"`) — the ordinary login.
2. **Admin impersonation** (`event_type="impersonation"`) — see below.
3. **Shared-device PIN** (`event_type="shared_pin"`) — a front-desk-tablet
   flow for staff who share one device: enter the studio code, pick your
   name from the instructors registered at that studio, enter your PIN
   (`POST /api/auth/shared/lookup` then `POST /api/auth/shared/login`). The
   token minted is short-lived (`SHARED_SESSION_EXPIRE_MINUTES`, default 60)
   and hard-scoped to that one studio — there is no broader session to
   escalate into. The PIN check always runs one password-hash verification,
   against either the real stored hash or a fixed dummy hash when no
   matching user exists, so a lookup miss and a wrong PIN take the same
   amount of time and can't be told apart by an attacker timing the
   response.

Having one shared log across all three means "who logged in as whom, when,
and how" is a single query rather than three inconsistent ones — see
`backend/app/routes/login_events.py`.

### Admin impersonation ("backdoor" access)

`POST /api/auth/impersonate/{user_id}` (admin-only) issues a normal access
token *for the target user*, not a special elevated one — same shape,
same claims path, same repo scoping every other token gets. Two things make
it safe to have at all rather than a silent backdoor:

- **The token carries who's really driving.** `create_access_token(...,
  impersonated_by=admin_id)` bakes the admin's own id into an `act` claim
  (named after RFC 8693's actor-token convention). `get_impersonator_id()`
  (`backend/app/dependencies.py`) reads it back, and code paths that record
  per-user state — e.g. dismissing a notice — check it first: an admin
  previewing a user's session by impersonating them must never leave a mark
  that reads as if the real user did it.
- **It's scoped, not a master key.** The impersonated session gets an `osid`
  (operating-studio-id) claim binding it to one studio — the studio passed
  explicitly or the admin's currently-selected one — so an impersonated
  instructor session sees exactly what that instructor would see, nothing
  broader.
- **Every impersonation is a login-event row** (`event_type="impersonation"`,
  `actor_user_id` = the admin, `user_id` = the target), so "who was
  impersonated, by whom, when" survives independent of application logs.

Because impersonation is just token minting, revoking it is nothing more
than the frontend discarding the token and restoring the admin's own —
there's no server-side session to tear down.

## Messaging engine

Three independent pieces, each solving a different "get information to/from
a user" problem:

1. **Broadcast announcements ("Notes")** — `backend/app/models/user_note.py`,
   `backend/app/routes/notes.py`. An admin-authored `UserNote` shown to every
   signed-in staff user at login. Dismissal is per-user and per-edit: a
   `UserNoteDismissal` row records when a user disregarded a note, and it's
   compared against the note's `updated_at` — editing the note (even just
   toggling `is_active`) bumps `updated_at`, which un-dismisses it for
   everyone. That's a deliberate design, not a bug: an announcement that
   changed content is a new thing to acknowledge. Notes carry no
   studio/franchise scope at all — they're a genuinely global broadcast,
   the `unscoped` category in `MODEL_SCOPE`.
2. **Private two-way threads ("Questions")** —
   `backend/app/models/user_question.py`, `backend/app/routes/questions.py`.
   A user opens a `UserQuestion` thread (optionally with an attachment and no
   text — a screenshot alone is a valid question); an admin answers from an
   inbox. Both sides append `UserQuestionMessage` rows to the same thread, so
   it reads as a conversation rather than a one-shot contact form. The thread
   is stamped with the asking user's `studio_id` (denormalized, so the admin
   inbox can filter/sort by studio without re-deriving it per row) and
   carries an admin-set triage `status` (`new` / `read` / `resolved`).
3. **Pluggable transactional email** — `backend/app/services/email.py`. One
   `send_email()` entry point, three interchangeable backends selected by
   `EMAIL_BACKEND`:
   * `console` (default) — logs the message and returns success; every
     invite/reset/report-link flow is fully testable with no provider
     account, and dev output surfaces the actual link.
   * `resend` — needs `RESEND_API_KEY`.
   * `smtp` — needs `SMTP_HOST`, `SMTP_PORT` (default 587), and optionally
     `SMTP_USER` / `SMTP_PASSWORD` if the host requires auth.

   Switching backends is an env change only (`EMAIL_BACKEND` plus that
   backend's secrets) — no code path changes. The one thing to know when
   running for real: `console` makes every send path "succeed" locally even
   when nothing about production mail delivery is actually configured, so
   don't mistake dev's green output for a proof that a real provider works.

## Stripe billing

Two independent Stripe integrations, deliberately kept apart because they
represent different money flows against the same Stripe account:

* **Client payments** — a studio's own customers buying from that studio.
* **Platform billing** — studios paying the platform itself a subscription.

Both follow the same shape:

* `is_enabled()` gates the feature on **both** a feature flag and the
  presence of `STRIPE_SECRET_KEY` — missing either one, every endpoint under
  it reports "not enabled" rather than erroring. A deployment with no Stripe
  account configured never trips a 500.
* Pricing is always computed server-side from the pending record, never
  trusted from the client request.
* The Stripe module is imported lazily, inside each function that needs it,
  so the app boots cleanly even when the feature is off.
* Payment truth comes from the webhook, not the checkout redirect — each
  integration has its own signing secret (`STRIPE_WEBHOOK_SECRET` /
  `STRIPE_BILLING_WEBHOOK_SECRET`) because each is a separately registered
  webhook endpoint even though both share one Stripe account and one
  `STRIPE_SECRET_KEY`.

See `backend/app/services/stripe_payments.py` and
`backend/app/services/stripe_billing.py`.

## Frontend structure

```
frontend/src/
  pages/        one file per screen/route, grouped into subfolders by area
  api/          one module per backend resource — the only place that knows
                the request/response shape; pages never call axios directly
  components/   reusable UI, grouped by area (mirrors pages/)
  components/layout/   the app shell: Sidebar, AppShell, ContextBar
                        (the active-studio switcher), PageHeader
  context/      React context providers (auth/session state)
  hooks/        shared hooks
```

The `api/` layer is the frontend's mirror of the backend's data layer: pages
depend on a typed function (`getClients()`, `createSession()`, ...), never on
a raw endpoint string, so a backend contract change has exactly one place to
update on the frontend side.

The sidebar menu (`components/layout/Sidebar.jsx`) is the map of what a given
role can reach — it filters items by role and by whether a studio is
currently selected, so it's a reasonable first stop when tracing what an
authenticated user can actually see.

An informational home page surfaces the messaging engine, shared-device
login, and impersonation as feature cards for a signed-in admin — a starting
point for exploring what the starter kit ships, not a replacement for the
per-area dashboards under `pages/admin/`, `pages/setup/`, etc.
