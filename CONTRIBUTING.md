# Contributing

## Workflow

1. Fork the repo (or branch, if you have write access) and create a
   feature branch off `main`.
2. Make your change. If it touches a scoped model, follow the data-layer
   rule in `CLAUDE.md` — new routes never query a model directly.
3. Open a pull request against `main` describing what changed and why.

## Before you open a PR

The guard tests in `backend/tests/` exist to catch scoping regressions
automatically — a PR that weakens or skips them to make a change pass will be
asked to fix the change instead. At minimum, before pushing:

```bash
# backend
docker compose run --rm backend python -m pytest -q

# frontend
cd frontend && npm run lint && npm run build
```

If your change touches a user-facing flow, add or update an end-to-end test
under `frontend/tests/e2e/` rather than relying on manual verification alone.

## Commit hygiene

- No secrets in commits: API keys, tokens, `.env` files, or real credentials
  of any kind. `.env.example` documents every variable the app reads —
  copy it to `.env` locally and fill in your own values.
- Keep commits scoped to one change; explain the *why* in the message body
  when it isn't obvious from the diff.
- Reference the GitHub issue your change addresses, if one exists.

## Reporting issues

Use GitHub Issues. Include repro steps, what you expected, and what actually
happened. For security-sensitive reports, do not open a public issue —
contact the maintainer directly instead.
