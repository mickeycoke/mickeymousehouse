# Skills in this repo

A skill here is a packaged playbook for a recurring task — the instructions
an AI coding agent (or a new human contributor) would otherwise have to
rediscover by reading code and asking questions every single time.

## The pattern: one operator skill per app/subsystem

As this repo grows past a single app, give each distinct app or subsystem
its own skill rather than letting one skill try to cover everything. A skill
scoped to one thing can carry that thing's *current state* — what exists,
what's wired up, what's still a stub — so an agent working on it doesn't
have to re-derive the state of the world from scratch, and doesn't have to
wade through instructions for parts of the repo it isn't touching.

Concretely:

- **Write the skill before doing repeat work, not after.** The second time
  you (or an agent) do the same multi-step task by hand — deploy a service,
  run a data import, drive a verification gate — that's the signal to
  capture it as a skill instead of doing it from memory a third time.
- **Skills carry state, not just steps.** A generic "how to deploy" doc goes
  stale the moment the deploy process changes underneath it. A skill that
  says what's *currently* true (which services exist, which are live, which
  flags are on) stays useful because it's the thing that gets updated when
  reality changes — not a separate doc someone forgets to touch.
- **One skill, one clear trigger.** The skill's description is what a
  coding agent matches against the task at hand — keep it specific enough
  that it fires for the right work and stays quiet for everything else.

## What's here

- **`pre-commit-full-test/`** — the mandatory verification gate: backend
  suite, frontend lint/build, end-to-end tests, and a live API probe of
  whatever the change touched, all evidence-based. Run it before every
  commit and before every deploy.

Add a new skill directory (`.claude/skills/<name>/SKILL.md`) per app or
subsystem as the codebase grows. Keep this file's list current when you do.
