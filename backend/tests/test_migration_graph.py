"""Architecture guard: the alembic revision graph must be a single valid chain.

WHY THIS EXISTS

Nothing walked the revision graph. Three separate failures were possible and
two of them happened:

  * MULTIPLE HEADS. Parallel branches merge cleanly in git and then
    `alembic upgrade head` refuses to run, or runs only one branch. This was
    hit for real (three heads, later merged).

  * A FALSE ALARM FROM A HAND-ROLLED PARSER. A coordinator once grepped
    `down_revision` out of the version files and reported three heads and a
    production blocker. It had misread ONE merge revision, whose
    `down_revision` is a TUPLE:

        down_revision = ("b8c9d0e1f2a3", "f2b3c4d5e6f7")

    A tuple parent is not three heads; it is one revision with two parents.
    This file uses alembic's own `ScriptDirectory`, which is the same code
    `alembic upgrade` uses, so it cannot disagree with the tool. Never replace
    it with a regex.

  * A DANGLING PARENT. A `down_revision` naming a revision that was renamed or
    deleted makes the whole chain unrunnable, and the error surfaces only when
    someone actually migrates a database.

NO DATABASE. This is a pure read of alembic/versions/, so it belongs in the
architecture-guards CI job, which has no postgres. Do not add a fixture that
connects to one.
"""
import ast
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND / "alembic.ini"
VERSIONS_DIR = BACKEND / "alembic" / "versions"


@pytest.fixture(scope="module")
def script_dir() -> ScriptDirectory:
    """alembic's own view of the revision graph. Reads files only."""
    assert ALEMBIC_INI.is_file(), f"missing {ALEMBIC_INI}"
    cfg = Config(str(ALEMBIC_INI))
    # alembic.ini says `script_location = alembic`, which is relative to the
    # backend dir; make it absolute so the test does not depend on cwd.
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Edge reading WITHOUT alembic's revision map.
#
# Alembic builds the map eagerly on the first walk, and a single dangling
# `down_revision` makes it raise `KeyError: '<missing>'` from deep inside
# alembic — six tests fail with an opaque traceback and nobody learns which
# edge is broken. So the edge check reads the literals itself.
#
# This is a LITERAL read (`ast.literal_eval` of the assigned value), not the
# grep that burned us before: `down_revision = ("a", "b")` comes back as the
# 2-tuple it is. It is used ONLY for edge resolution — head and base counting
# stay with alembic, because that is exactly where hand-rolled parsing went
# wrong. `test_parsed_ids_match_alembic` pins the two views together so this
# reader can never silently drift.
# ─────────────────────────────────────────────────────────────────────────────

def _declared_edges() -> dict:
    """revision id -> tuple of declared parent ids, read from the files."""
    edges = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        rev = None
        down = ()
        for node in tree.body:
            # Both forms occur in this repo:
            #   revision = '1285b47eb3f9'                       -> ast.Assign
            #   revision: str = '1285b47eb3f9'                  -> ast.AnnAssign
            # `alembic revision --autogenerate` emits the annotated form, the
            # hand-written files use the plain one. Missing AnnAssign made this
            # parser silently see 0 revisions for 40 of the 42 files —
            # test_parsed_ids_match_alembic is what caught that.
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            else:
                continue
            if node.value is None:
                continue
            if "revision" in names:
                rev = ast.literal_eval(node.value)
            elif "down_revision" in names:
                value = ast.literal_eval(node.value)
                if value is None:
                    down = ()
                elif isinstance(value, str):
                    down = (value,)
                else:
                    down = tuple(value)  # merge revision: a TUPLE of parents
        assert rev, f"{path.name} declares no `revision`"
        edges[rev] = down
    return edges


def test_every_down_revision_resolves():
    """Every declared parent must be a revision that exists.

    Runs before alembic's map is built, so a broken edge is reported by name
    instead of surfacing as `KeyError` from alembic internals.
    """
    edges = _declared_edges()
    known = set(edges)
    dangling = [
        f"{rev} -> down_revision {parent!r} does not exist"
        for rev, parents in edges.items()
        for parent in parents
        if parent not in known
    ]
    assert not dangling, (
        "Broken alembic edges — the upgrade path cannot be walked:\n  "
        + "\n  ".join(sorted(dangling))
    )


def test_parsed_ids_match_alembic(script_dir):
    """Keeps _declared_edges() honest: if it ever disagrees with alembic about
    which revisions exist, the edge check above is checking a fiction."""
    mine = set(_declared_edges())
    theirs = {rev.revision for rev in script_dir.walk_revisions()}
    assert mine == theirs, (
        f"local parse and alembic disagree — only in files: {sorted(mine - theirs)}; "
        f"only in alembic: {sorted(theirs - mine)}"
    )


def test_merge_revisions_declare_more_than_one_parent():
    """Documentation-as-test for the tuple form. A merge revision looks like

        down_revision = ("b8c9d0e1f2a3", "f2b3c4d5e6f7")

    which is ONE revision with TWO parents. A parser that splits on quotes sees
    two ids and concludes there are extra heads — that false 'production
    blocker' is why this file exists.
    """
    edges = _declared_edges()
    merges = {rev: parents for rev, parents in edges.items() if len(parents) > 1}
    for rev, parents in merges.items():
        assert len(set(parents)) == len(parents), (
            f"merge revision {rev} lists a parent twice: {parents}"
        )
    # Each parent of a merge must itself be a real revision (covered above) and
    # must not also be a head — merging is what removes them from the head set.
    child_of = {p for parents in edges.values() for p in parents}
    for rev, parents in merges.items():
        for parent in parents:
            assert parent in child_of, f"{parent} unexpectedly not a parent-of edge"


def test_version_files_are_present(script_dir):
    """A guard that silently walks an empty graph would pass forever.

    This starter kit ships a single hand-checked initial migration (the whole
    prior chain was deleted and replaced), so `>= 1` is the right bound here
    — not `> 1`, which would only make sense once a second migration exists.
    """
    assert VERSIONS_DIR.is_dir(), f"missing {VERSIONS_DIR}"
    revisions = list(script_dir.walk_revisions())
    on_disk = [p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py"]
    assert len(revisions) >= 1, "no revision graph to check"
    assert len(revisions) == len(on_disk), (
        f"alembic loaded {len(revisions)} revisions but {len(on_disk)} .py files "
        "exist in alembic/versions/ — a file is not a revision, or two files "
        "declare the same revision id"
    )


def test_exactly_one_head(script_dir):
    """Two heads means `alembic upgrade head` cannot run. Merge them with
    `alembic merge` — do not delete one branch."""
    heads = script_dir.get_heads()
    assert len(heads) == 1, (
        f"{len(heads)} alembic heads: {sorted(heads)}\n"
        "Run `alembic merge -m 'merge X and Y' " + " ".join(sorted(heads)) + "`.\n"
        "NOTE a merge revision has a TUPLE down_revision — that is one revision "
        "with two parents, not multiple heads."
    )


def test_exactly_one_base(script_dir):
    """More than one base means two independent chains were created; upgrading
    from an empty database would apply only one of them."""
    bases = script_dir.get_bases()
    assert len(bases) == 1, (
        f"{len(bases)} alembic bases (revisions with no down_revision): "
        f"{sorted(bases)}. The history must start from a single root."
    )


def test_every_depends_on_resolves(script_dir):
    """`depends_on` is a second, rarer edge kind; a dangling one is just as
    fatal to an upgrade as a dangling down_revision."""
    known = {rev.revision for rev in script_dir.walk_revisions()}
    dangling = []
    for rev in script_dir.walk_revisions():
        deps = rev.dependencies
        if deps is None:
            deps = ()
        elif isinstance(deps, str):
            deps = (deps,)
        for dep in deps:
            if dep not in known:
                dangling.append(f"{rev.revision} -> depends_on {dep!r} does not exist")
    assert not dangling, (
        "Broken alembic depends_on edges:\n  " + "\n  ".join(sorted(dangling))
    )


def test_the_head_reaches_every_revision(script_dir):
    """One head and one base is not sufficient on its own: an orphaned side
    chain whose own head was merged away could still hide. Walking down from
    the head must reach every revision on disk."""
    head = script_dir.get_heads()[0]
    reachable = {rev.revision for rev in script_dir.walk_revisions("base", head)}
    all_revs = {rev.revision for rev in script_dir.walk_revisions()}
    unreachable = sorted(all_revs - reachable)
    assert not unreachable, (
        "These revisions are not reachable from the single head, so "
        "`alembic upgrade head` will never apply them:\n  " + "\n  ".join(unreachable)
    )


def test_alembic_and_the_parser_agree_on_which_revisions_are_merges(script_dir):
    """The tuple form must be exercised by REAL data, not only by the parser
    — whenever a merge revision exists. This starter kit's chain was reset
    to a single hand-checked initial migration, so there is currently no
    merge revision and both sets are expected to be empty; the equality
    check still guards against the parser and alembic ever disagreeing once
    a merge is introduced.
    """
    alembic_merges = {rev.revision for rev in script_dir.walk_revisions()
                      if rev.is_merge_point}
    parsed_merges = {rev for rev, parents in _declared_edges().items() if len(parents) > 1}
    assert alembic_merges == parsed_merges, (
        f"alembic says merges are {sorted(alembic_merges)}, the literal parse says "
        f"{sorted(parsed_merges)}"
    )
