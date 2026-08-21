"""THE ARCHITECTURAL RULE — new data cannot enter the model unscoped.

    "If we ever introduce NEW data into the data model it has to be behind an
     API / a data layer. If you come across code that is not behind a data
     layer it must be addressed and fixed immediately."

A convention cannot enforce that; a test can. This file is the enforcement.

HOW IT WORKS — three gates:

  1. REGISTRY COMPLETENESS. Every SQLAlchemy model under `app/models/` must
     appear in MODEL_SCOPE below with an explicit decision. Add a new model and
     this test fails until you say how it is scoped. There is no default, and
     "unscoped" is a legal answer only with a written reason. This is the gate
     that makes the rule automatic rather than remembered.

  2. NO RAW READS OF SCOPED MODELS. Anything registered `studio`, `franchise`
     or `derived` may not be read via `db.query(Model)` outside `app/data/`.
     It goes through a repository, which is the only place a scope filter is
     written.

  3. THE EXCEPTION LIST MAY ONLY SHRINK. Legacy call sites are counted, not
     just listed, so a file already on the list cannot quietly grow new
     violations.

WHEN THIS TEST FAILS, FIX THE CODE — never the test.

─────────────────────────────────────────────────────────────────────────────
This is the starter-kit baseline (mickeymouse-house): the app this was cut
down from carried a much larger MODEL_SCOPE/LEGACY_BUDGET (over 90 models and
137 file/model debt pairs, the product of a fitness-studio domain this kit
does not include). Every entry below was recomputed from scratch against the
surviving 15 models and 18 routes — auth + a franchise->studio hierarchy that
scopes pricing tiers, plus a small communication engine (notes/questions/
attachments). The AST walker itself (alias resolution, whole-argument
matching, path-keyed exception tables) is unchanged from the app it came
from — only the registry and the counted debt were re-baselined.
"""
import ast
import inspect
import pkgutil
import importlib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

# Directories a request can reach. `app/data/` is excluded — it IS the layer.
SEARCH_DIRS = ["app/routes", "app/utils", "app/services", "app/reports"]

# Individual modules outside those trees that still serve requests.
SEARCH_FILES = ["app/dependencies.py"]

# ─────────────────────────────────────────────────────────────────────────────
# THE REGISTRY. Every model gets a decision. No default.
#
#   "studio"    — has studio_id; read through a StudioScopedRepo
#   "franchise" — has franchise_id; NULL means shared standard (deliberate)
#   "derived"   — no scope column; only safe via its parent's repo
#   "unscoped: <reason>" — genuinely global. The reason is mandatory.
# ─────────────────────────────────────────────────────────────────────────────
MODEL_SCOPE = {
    # --- studio axis ---
    "User": "studio",
    "LoginEvent": "studio",
    "UserQuestion": "studio",
    "UserStudio": "studio",
    "StudioOwner": "studio",
    "FranchiseStudio": "studio",
    # Stripe Studio Billing. One row per studio's Stripe billing relationship;
    # routes are admin-only, but the studio scope still applies so a foreign
    # studio's row is never reachable by id.
    "StudioSubscription": "studio",
    # --- franchise axis (NULL = shared standard) ---
    "FranchiseOwner": "franchise",
    # --- derived: no scope column, inherits from a parent ---
    # An admin-authored announcement shown to every signed-in staff user —
    # deliberately NOT studio-scoped (it's a broadcast), but still not a
    # bare raw read: it goes through the same request-serving code every
    # other model here does, so it is tracked, not exempted.
    "UserNote": "derived",
    "UserNoteDismissal": "derived",
    "UserQuestionMessage": "derived",
    "Attachment": "derived",
    # Pricing tiers admin feature. The SaaS price BOOK itself — a
    # reference/config table, not tenant data, and not wired to any studio's
    # actual billing (that's StudioSubscription above). No studio_id/
    # franchise_id column exists to scope by.
    "PricingTier": "unscoped: platform-wide pricing configuration; not tenant data, admin-only writes",
    # --- genuinely global ---
    "Studio": "unscoped: the studio directory itself; membership is what scopes",
    "Franchise": "unscoped: franchise directory; read-only reference data",
}

ENFORCED = {"studio", "franchise", "derived"}

# Call sites inherited as-is from the app this starter kit was cut down from.
# Each route already narrows visibility by hand (ownership/instructor-
# membership checks, admin-only gates) — it just doesn't yet do so through a
# repo in app/data/. COUNTS, so a listed file cannot grow new violations.
#
# KEYS ARE REPO-RELATIVE PATHS, not filenames.
#
# Recomputed from scratch for the surviving 15-model registry (see module
# docstring) — every number here is the exact, verified count in this
# checkout, not carried over from the original app's larger budget.
LEGACY_BUDGET = {
    # (repo-relative path, model): max raw db.query(...) calls still tolerated.
    ("app/dependencies.py", "FranchiseOwner"): 1,
    ("app/dependencies.py", "StudioOwner"): 1,
    ("app/dependencies.py", "User"): 1,

    ("app/reports/access.py", "FranchiseStudio"): 1,

    ("app/routes/attachments.py", "Attachment"): 6,
    ("app/routes/attachments.py", "UserQuestion"): 1,
    ("app/routes/auth.py", "User"): 7,
    ("app/routes/auth.py", "UserStudio"): 2,
    ("app/routes/franchise_owners.py", "FranchiseOwner"): 4,
    ("app/routes/franchise_owners.py", "User"): 1,
    ("app/routes/franchise_studios.py", "FranchiseStudio"): 3,
    ("app/routes/login_events.py", "LoginEvent"): 1,
    ("app/routes/login_events.py", "User"): 2,               # aliased(User) x2
    ("app/routes/notes.py", "UserNote"): 6,
    ("app/routes/notes.py", "UserNoteDismissal"): 4,
    ("app/routes/onboard.py", "User"): 4,
    ("app/routes/onboard.py", "UserStudio"): 1,
    ("app/routes/ownership.py", "User"): 1,
    ("app/routes/questions.py", "User"): 4,
    ("app/routes/questions.py", "UserQuestion"): 4,
    ("app/routes/questions.py", "UserQuestionMessage"): 1,
    ("app/routes/roles.py", "FranchiseOwner"): 6,
    ("app/routes/roles.py", "StudioOwner"): 3,
    ("app/routes/roles.py", "User"): 2,
    ("app/routes/roles.py", "UserStudio"): 4,
    ("app/routes/studio_assignment.py", "StudioOwner"): 1,
    ("app/routes/studio_assignment.py", "User"): 2,
    ("app/routes/studio_assignment.py", "UserStudio"): 2,
    ("app/routes/studio_owners.py", "FranchiseStudio"): 1,
    ("app/routes/studio_owners.py", "StudioOwner"): 3,
    ("app/routes/studio_owners.py", "User"): 1,
    ("app/routes/studios.py", "FranchiseStudio"): 5,
    ("app/routes/users.py", "User"): 7,

    ("app/utils/backend_user.py", "User"): 1,
    ("app/utils/ownership.py", "FranchiseOwner"): 5,
    ("app/utils/ownership.py", "FranchiseStudio"): 4,
    ("app/utils/ownership.py", "StudioOwner"): 3,
    ("app/utils/ownership.py", "UserStudio"): 1,
    ("app/utils/ownership_validation.py", "FranchiseOwner"): 1,
    ("app/utils/ownership_validation.py", "FranchiseStudio"): 1,
    ("app/utils/ownership_validation.py", "StudioOwner"): 1,
    ("app/utils/ownership_validation.py", "User"): 1,
}

# Deliberate, permanent — each needs a reason. Keyed on the repo-relative path.
# None yet in this starter kit; every current raw read is tracked as counted
# debt in LEGACY_BUDGET above instead. Add here only for a call site that is
# CORRECT to leave unscoped forever (e.g. an admin-only cross-studio console),
# not merely not-yet-migrated.
PERMANENT_ALLOWLIST = {}

# How many scoped models still have no repository.
# Recomputed for the surviving registry: 12 models are enforced
# (studio/franchise/derived); FranchiseStudio, LoginEvent, StudioSubscription
# and User already have one (app/data/franchise_studio_repo.py,
# app/data/login_events.py, app/data/studio_subscriptions.py,
# app/data/auth_lookup.py) — 8 remain. Tighten this number as each lands;
# never raise it.
MAX_MODELS_WITHOUT_A_REPO = 8


# ─────────────────────────────────────────────────────────────────────────────
# AST plumbing
# ─────────────────────────────────────────────────────────────────────────────

def _model_aliases(tree: ast.AST) -> dict:
    """Map every local name that stands for a model class -> real class name.

    Three binding forms are resolved:

      from app.models.user import User as UserModel   ->  User
      import app.models.user as um                    ->  user (module; harmless)
      subject = aliased(User)                          ->  User

    `ast.walk`, not `tree.body`: an alias import inside a function body would
    be missed by a module-body-only scan.
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
            # `subject = aliased(User)` — a second, non-import way to hide a
            # scoped model behind a local name.
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

    # Chase chains (`X as Y` then `Z = aliased(Y)`) without looping forever.
    resolved = {}
    for name in direct:
        seen = {name}
        value = direct[name]
        while value in direct and value not in seen:
            seen.add(value)
            value = direct[value]
        resolved[name] = value
    return resolved


def _names_in(expr: ast.AST, aliases: dict) -> set:
    """Every model-ish name referenced anywhere inside one `.query()` argument.

    Walks the whole argument subtree, not just its top node, so
    `func.x(Model.col)` / `Model.col.label(...)` / any future wrapper is still
    seen. Counted once per argument: `db.query(Model.a, Model.b)` counts 2,
    `db.query(func.sum(Model.a))` counts 1.
    """
    return {
        aliases.get(node.id, node.id)
        for node in ast.walk(expr)
        if isinstance(node, ast.Name)
    }


def _raw_queries(path: Path):
    """Yield (real_model_name, lineno) for each `<something>.query(Model)`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    aliases = _model_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "query"):
            continue
        for arg in node.args:
            for name in sorted(_names_in(arg, aliases)):
                yield name, node.lineno


def _search_files():
    for d in SEARCH_DIRS:
        yield from sorted((BACKEND / d).rglob("*.py"))
    for f in SEARCH_FILES:
        p = BACKEND / f
        assert p.exists(), f"SEARCH_FILES names a file that does not exist: {f}"
        yield p


def _rel(path: Path) -> str:
    return str(path.relative_to(BACKEND))


def _counts() -> dict:
    """(relative path, model) -> number of raw reads."""
    counts: dict = {}
    for path in _search_files():
        rel = _rel(path)
        for model, _ in _raw_queries(path):
            counts[(rel, model)] = counts.get((rel, model), 0) + 1
    return counts


def _model_classes():
    """Every mapped class under app/models, discovered — not hand-listed, so a
    new file cannot dodge the registry by not being imported anywhere."""
    from app.database import Base
    import app.models as models_pkg

    for m in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{m.name}")
    found = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if inspect.getmodule(cls).__name__.startswith("app.models"):
            found[cls.__name__] = cls
    return found


def _models_the_data_layer_actually_uses() -> set:
    """Models that some repo in app/data/ genuinely binds or queries.

    A model counts only if a class in app/data/ sets it as its repo `model`,
    or app/data/ calls `.query()` on it, AND the name was imported from
    `app.models` in that file.
    """
    used = set()
    for path in sorted((BACKEND / "app" / "data").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.models"):
                imported.update(a.name for a in node.names)
        if not imported:
            continue
        for node in ast.walk(tree):
            # `model = Client` on a repo class
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                if any(isinstance(t, ast.Name) and t.id == "model" for t in node.targets):
                    if node.value.id in imported:
                        used.add(node.value.id)
            # `self.db.query(Client)` inside the layer
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "query"
            ):
                for arg in node.args:
                    name = None
                    if isinstance(arg, ast.Name):
                        name = arg.id
                    elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                        name = arg.value.id
                    if name in imported:
                        used.add(name)
    return used


# ─── the walker itself must work ─────────────────────────────────────────────
# Regression tests for the blind spots the original app found. If someone
# "simplifies" _raw_queries back to a naive name lookup, these fail before any
# baseline does.

def _queries_of_source(src: str, tmp_path: Path):
    p = tmp_path / "sample.py"
    p.write_text(src)
    return sorted(m for m, _ in _raw_queries(p))


def test_walker_resolves_a_module_level_import_alias(tmp_path):
    src = (
        "from app.models.user import User as UserModel\n"
        "def f(db):\n"
        "    return db.query(UserModel).all()\n"
    )
    assert _queries_of_source(src, tmp_path) == ["User"]


def test_walker_resolves_a_function_local_import_alias(tmp_path):
    src = (
        "def f(db):\n"
        "    from app.models.user import User as UserModel\n"
        "    return db.query(UserModel.id).all()\n"
    )
    assert _queries_of_source(src, tmp_path) == ["User"]


def test_walker_resolves_aliased_bindings(tmp_path):
    """app/routes/login_events.py does `subject = aliased(User)`."""
    src = (
        "from sqlalchemy.orm import aliased\n"
        "from app.models.user import User\n"
        "subject = aliased(User)\n"
        "def f(db):\n"
        "    return db.query(subject.id).all()\n"
    )
    assert _queries_of_source(src, tmp_path) == ["User"]


def test_walker_still_sees_the_plain_and_column_forms(tmp_path):
    src = (
        "from app.models.user import User\n"
        "def f(db):\n"
        "    db.query(User)\n"
        "    db.query(User.id, User.name)\n"
    )
    assert _queries_of_source(src, tmp_path) == ["User", "User", "User"]


def test_walker_sees_models_wrapped_in_function_calls(tmp_path):
    """`db.query(func.count(UserModel.id))` must not be invisible: the
    argument is a Call, and only Name / Name.attr being matched would miss it."""
    src = (
        "from sqlalchemy import func, distinct\n"
        "from app.models.user import User as UserModel\n"
        "def f(db):\n"
        "    db.query(func.count(distinct(UserModel.studio_id)))\n"
    )
    assert "User" in _queries_of_source(src, tmp_path)


def test_one_argument_counts_once_however_deeply_nested(tmp_path):
    """The arithmetic of every existing budget number depends on this: a model
    referenced twice inside ONE argument is one read, and two arguments are two."""
    src = (
        "from sqlalchemy import func\n"
        "from app.models.studio import Studio\n"
        "def f(db):\n"
        "    db.query(func.coalesce(func.sum(Studio.id), Studio.id))\n"
        "    db.query(Studio.id, Studio.name)\n"
    )
    assert _queries_of_source(src, tmp_path).count("Studio") == 3


def test_the_search_set_actually_covers_reports_and_dependencies():
    scanned = {_rel(p) for p in _search_files()}
    assert "app/dependencies.py" in scanned
    assert any(p.startswith("app/reports/") for p in scanned), (
        "app/reports/ is not being scanned. Do not remove it from SEARCH_DIRS."
    )


def test_user_enforcement_is_alive():
    """`User` is this starter kit's most-read scoped model, and the one real
    exercise of `aliased()` resolution (app/routes/login_events.py). If this
    finds too few reads, alias resolution in `_model_aliases()` is probably
    broken again."""
    counts = _counts()
    user_reads = sum(n for (_, model), n in counts.items() if model == "User")
    assert user_reads >= 30, (
        f"only {user_reads} raw reads of User are visible; alias resolution "
        "in _model_aliases() is probably broken again"
    )
    assert not any(model == "UserModel" for _, model in counts), (
        "the alias 'UserModel' leaked through unresolved"
    )


# ─── gate 1 ──────────────────────────────────────────────────────────────────

def test_every_model_declares_its_scope():
    """NEW DATA MUST DECLARE ITS SCOPE.

    Adding a model without a MODEL_SCOPE entry fails here. That is the point:
    you cannot introduce data into this system without stating who may see it.
    """
    undeclared = sorted(set(_model_classes()) - set(MODEL_SCOPE))
    assert not undeclared, (
        "These models have no scope decision:\n  " + "\n  ".join(undeclared) +
        "\n\nAdd each to MODEL_SCOPE in this file as 'studio', 'franchise', "
        "'derived', or 'unscoped: <reason>'. If it is scoped, it also needs a "
        "repository in app/data/ — routes must never query it directly."
    )


def test_registry_has_no_phantom_entries():
    """A registry entry for a model that no longer exists is stale and hides
    the fact that nothing is being enforced."""
    phantom = sorted(set(MODEL_SCOPE) - set(_model_classes()))
    assert not phantom, f"MODEL_SCOPE lists models that do not exist: {phantom}"


def test_unscoped_entries_state_a_reason():
    bare = [m for m, v in MODEL_SCOPE.items() if v == "unscoped" or v.strip() == "unscoped:"]
    assert not bare, (
        f"'unscoped' needs a written justification: {bare}. "
        "Write 'unscoped: <why this data is safe to show everyone>'."
    )


def test_every_scoped_model_is_reachable_through_the_data_layer():
    """A model declared studio/franchise/derived must actually have a repo, or
    the declaration is aspirational. Reported as a to-do list, not a hard fail
    — but it can only get shorter.
    """
    enforced_models = {m for m, v in MODEL_SCOPE.items() if v in ENFORCED}
    missing = sorted(enforced_models - _models_the_data_layer_actually_uses())
    assert len(missing) <= MAX_MODELS_WITHOUT_A_REPO, (
        f"{len(missing)} scoped models have no representation in app/data/: {missing}"
    )


# ─── gate 2 ──────────────────────────────────────────────────────────────────

def test_scoped_models_are_never_queried_outside_the_data_layer():
    violations = []
    for path in _search_files():
        rel = _rel(path)
        for model, lineno in _raw_queries(path):
            if MODEL_SCOPE.get(model) not in ENFORCED:
                continue
            if (rel, model) in PERMANENT_ALLOWLIST:
                continue
            if (rel, model) in LEGACY_BUDGET:
                continue
            violations.append(f"{rel}:{lineno}  db.query({model})")

    assert not violations, (
        f"{len(violations)} raw reads of scoped models outside app/data/:\n  "
        + "\n  ".join(violations[:60])
        + "\n\nRoute these through a repository in app/data/. If a call site is "
        "genuinely exempt, add it to PERMANENT_ALLOWLIST with a reason — never "
        "delete the assertion."
    )


# ─── gate 3 ──────────────────────────────────────────────────────────────────

def test_budget_keys_are_relative_paths_that_exist():
    """Keys are repo-relative paths, not bare filenames — a bare filename or a
    dead path would silently switch enforcement off for that pair."""
    bad = []
    for rel, model in sorted(set(LEGACY_BUDGET) | set(PERMANENT_ALLOWLIST)):
        if "/" not in rel:
            bad.append(f"{rel!r} is a bare filename — use the repo-relative path")
        elif not (BACKEND / rel).exists():
            bad.append(f"{rel!r} does not exist (entry for {model})")
    assert not bad, "Bad exception-table keys:\n  " + "\n  ".join(bad)


def test_every_searched_dir_and_file_exists():
    for d in SEARCH_DIRS:
        assert (BACKEND / d).is_dir(), f"SEARCH_DIRS names a missing dir: {d}"
    for f in SEARCH_FILES:
        assert (BACKEND / f).is_file(), f"SEARCH_FILES names a missing file: {f}"


def test_legacy_budget_only_shrinks():
    """A file on the legacy list must not grow new violations."""
    counts = _counts()
    over = []
    for key, allowed in LEGACY_BUDGET.items():
        actual = counts.get(key, 0)
        if actual > allowed:
            over.append(f"{key[0]} db.query({key[1]}): {actual} > budget {allowed}")
    assert not over, (
        "Legacy debt grew — new unscoped queries were added to a file that was "
        "already on the list:\n  " + "\n  ".join(over)
    )


def test_legacy_budget_entries_are_still_needed():
    """A budget that is higher than reality should be lowered so the ratchet
    keeps working."""
    counts = _counts()
    slack = {k: (counts.get(k, 0), v) for k, v in LEGACY_BUDGET.items() if counts.get(k, 0) < v}
    assert not slack, (
        "These budgets are looser than the code needs — lower them to lock in "
        f"the progress: {slack}"
    )


def test_permanent_allowlist_entries_are_still_needed():
    """A permanent exception for a call site that no longer exists is a hole
    waiting for the next edit to fall into."""
    counts = _counts()
    stale = [k for k in PERMANENT_ALLOWLIST if counts.get(k, 0) == 0]
    assert not stale, (
        f"PERMANENT_ALLOWLIST names call sites that are gone: {sorted(stale)}"
    )
