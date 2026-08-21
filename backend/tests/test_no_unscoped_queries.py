"""Architecture guard: request-serving code must not query scoped models directly.

This is the test that makes the data layer a rule instead of a convention.
Where `test_data_layer_contract.py` covers EVERY model with a counted budget
(a pair may have up to N raw reads), this file is a narrower, zero-tolerance
gate on the CORE studio-axis tenancy models — the four rows that decide who
can see and manage what in this franchise->studio hierarchy: `User`,
`StudioOwner`, `FranchiseStudio`, and `UserStudio`. A leak on any of these is
a privilege-escalation risk, not just a data leak, so a NEW raw read of one
of them anywhere in `app/routes` or `app/reports` fails the build outright —
it is either migrated onto a repo in `app/data/`, permanently excused with a
written reason, or added to `PENDING_MIGRATION` as counted, shrink-only debt.

Read a scoped model through `app.data`, or the build fails.
"""
import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

# Request-serving trees.
SEARCH_DIRS = ["app/routes", "app/reports"]

# Models whose reads must be scoped. Adding a model here is how a new entity
# opts into enforcement.
SCOPED_MODELS = {
    "User",
    "StudioOwner",
    "FranchiseStudio",
    "UserStudio",
}

# Deliberate, permanent exceptions. Each needs a reason. Keyed on the
# repo-relative path, not the filename.
PERMANENT_ALLOWLIST = {
    # This console's entire job is finding studio-LESS staff so an admin can
    # assign them a studio. Scoping it would hide exactly what it exists to
    # show. Admin-only (`require_admin`).
    ("app/routes/studio_assignment.py", "User"),
    # Admin-only roles summary: every user in the system with every hat they
    # hold, across every studio and franchise. Guarded by `require_admin`.
    ("app/routes/roles.py", "User"),
}

# Not yet migrated onto repos. This list may only SHRINK — a new entry means
# someone reintroduced the bug this guard exists to prevent. This starter kit
# inherited these call sites as-is from the app it was cut down from; each
# route already narrows visibility by hand (ownership/instructor-membership
# checks), it just does not yet do so through a repo in app/data/.
PENDING_MIGRATION = {
    ("app/reports/access.py", "FranchiseStudio"),
    ("app/routes/auth.py", "User"),
    ("app/routes/auth.py", "UserStudio"),
    ("app/routes/franchise_owners.py", "User"),
    ("app/routes/franchise_studios.py", "FranchiseStudio"),
    ("app/routes/login_events.py", "User"),
    ("app/routes/onboard.py", "User"),
    ("app/routes/onboard.py", "UserStudio"),
    ("app/routes/ownership.py", "User"),
    ("app/routes/questions.py", "User"),
    ("app/routes/roles.py", "StudioOwner"),
    ("app/routes/roles.py", "UserStudio"),
    ("app/routes/studio_assignment.py", "StudioOwner"),
    ("app/routes/studio_assignment.py", "UserStudio"),
    ("app/routes/studio_owners.py", "FranchiseStudio"),
    ("app/routes/studio_owners.py", "StudioOwner"),
    ("app/routes/studio_owners.py", "User"),
    ("app/routes/studios.py", "FranchiseStudio"),
    ("app/routes/users.py", "User"),
}


def _model_aliases(tree: ast.AST) -> dict:
    """Local name -> real model class name.

    Resolves `from app.models.x import Y as Z`, `import app.models.x as z`, and
    `z = aliased(Y)`. Uses `ast.walk` because an alias import in this codebase
    can live inside a function body, where a module-body scan would miss it.
    """
    direct = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("app.models"):
                for a in node.names:
                    if a.asname:
                        direct[a.asname] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname and a.name.startswith("app.models"):
                    direct[a.asname] = a.name.rsplit(".", 1)[-1]
        elif isinstance(node, ast.Assign):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "aliased"
                and value.args
                and isinstance(value.args[0], ast.Name)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        direct[target.id] = value.args[0].id

    resolved = {}
    for name in direct:
        seen = {name}
        value = direct[name]
        while value in direct and value not in seen:
            seen.add(value)
            value = direct[value]
        resolved[name] = value
    return resolved


def _direct_model_queries(path: Path):
    """Yield (model_name, lineno) for every `<something>.query(...)` call whose
    arguments mention a scoped model.

    The whole argument expression is walked, not just its top node — matching
    only `Model` and `Model.col` would miss any wrapped read, e.g.
    `db.query(User.id, func.count(StudioOwner.id))`. Import aliases and
    `aliased()` bindings are resolved first.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    aliases = _model_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "query"):
            continue
        for arg in node.args:
            found = {
                aliases.get(n.id, n.id)
                for n in ast.walk(arg)
                if isinstance(n, ast.Name)
            } & SCOPED_MODELS
            for real in sorted(found):
                yield real, node.lineno


def _search_files():
    for d in SEARCH_DIRS:
        yield from sorted((BACKEND / d).rglob("*.py"))


def _rel(path: Path) -> str:
    return str(path.relative_to(BACKEND))


def _violations():
    found = []
    for path in _search_files():
        rel = _rel(path)
        for model, lineno in _direct_model_queries(path):
            key = (rel, model)
            if key in PERMANENT_ALLOWLIST or key in PENDING_MIGRATION:
                continue
            found.append(f"{rel}:{lineno} — db.query({model})")
    return found


def test_routes_do_not_query_scoped_models_directly():
    violations = _violations()
    assert not violations, (
        "Scoped models must be read through app/data/ repos, not queried "
        "directly in request-serving code.\n\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nUse the entity's repo (e.g. `repo: XRepo = Depends(x_repo)`).\n"
        "If this really is a deliberate exception, add it to PERMANENT_ALLOWLIST "
        "with a written reason."
    )


def test_pending_migration_list_only_shrinks():
    """Entries here are debt inherited as-is. If one names a file/model pair
    that no longer queries directly, delete the entry — a stale entry would
    silently re-permit the bug later."""
    stale = []
    for rel, model in sorted(PENDING_MIGRATION):
        path = BACKEND / rel
        if not path.exists():
            stale.append(f"{rel} (file no longer exists)")
            continue
        if model not in {m for m, _ in _direct_model_queries(path)}:
            stale.append(f"{rel} — db.query({model}) is gone; remove this entry")
    assert not stale, (
        "PENDING_MIGRATION has stale entries. Remove them so the guard keeps "
        "its teeth:\n" + "\n".join(f"  {s}" for s in stale)
    )


def test_permanent_allowlist_only_covers_live_call_sites():
    stale = []
    for rel, model in sorted(PERMANENT_ALLOWLIST):
        path = BACKEND / rel
        if not path.exists():
            stale.append(f"{rel} (file no longer exists)")
        elif model not in {m for m, _ in _direct_model_queries(path)}:
            stale.append(f"{rel} — db.query({model}) is gone; remove this entry")
    assert not stale, (
        "PERMANENT_ALLOWLIST has stale entries; each is a hole the next edit "
        "can fall into:\n" + "\n".join(f"  {s}" for s in stale)
    )


def test_exception_keys_are_relative_paths_that_exist():
    """Both tables are keyed on repo-relative paths, not bare filenames — with
    more than one directory in scope a bare filename would silently merge
    unrelated files."""
    bad = []
    for rel, model in sorted(PERMANENT_ALLOWLIST | PENDING_MIGRATION):
        if "/" not in rel:
            bad.append(f"{rel!r} is a bare filename — use the repo-relative path")
        elif not (BACKEND / rel).exists():
            bad.append(f"{rel!r} does not exist (entry for {model})")
    assert not bad, "Bad exception-table keys:\n  " + "\n  ".join(bad)


def test_reports_are_in_scope():
    """app/reports/ serves requests same as app/routes/; do not drop it."""
    scanned = {_rel(p) for p in _search_files()}
    assert any(p.startswith("app/reports/") for p in scanned)
    assert any(p.startswith("app/routes/") for p in scanned)


@pytest.mark.parametrize("src,expected", [
    ("from app.models.user import User as U\ndef f(db): db.query(U)\n", ["User"]),
    ("def f(db):\n from app.models.studio_owner import StudioOwner as S\n db.query(S.id)\n",
     ["StudioOwner"]),
    ("from app.models.user import User\ndef f(db): db.query(User.id)\n", ["User"]),
    ("from sqlalchemy.orm import aliased\nfrom app.models.user import User\n"
     "a = aliased(User)\ndef f(db): db.query(a)\n", ["User"]),
])
def test_walker_sees_through_aliases_and_columns(tmp_path, src, expected):
    """Regression guard for the walker itself: if these stop passing, the gate
    is looking at identifiers instead of models again."""
    p = tmp_path / "sample.py"
    p.write_text(src)
    assert sorted(m for m, _ in _direct_model_queries(p)) == expected


@pytest.mark.parametrize("model", sorted(SCOPED_MODELS))
def test_scoped_model_is_known(model):
    """Sanity: every enforced model actually exists."""
    import app.models  # noqa: F401
    from app.database import Base

    names = {m.class_.__name__ for m in Base.registry.mappers}
    assert model in names, f"{model} is enforced but is not a mapped model"
