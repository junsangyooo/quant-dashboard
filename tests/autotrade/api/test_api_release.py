"""The server-side steps of deploy/deploy.sh (autotrade/api/release.py), on a throwaway git
repository under pytest's temporary folder: web releases, schema versions, the predeploy restore of
a rollback, the deploy record and the health check. No network, no npm, no systemd: those are
passed in as fakes."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from autotrade.api import release as rel

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
MIGRATIONS = "MIGRATIONS = (\n{}\n)\n"


def sh(root: Path, *args: str) -> str:
    done = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def commit(root: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", message)
    return sh(root, "rev-parse", "HEAD")


def migrations(n: int) -> str:
    return MIGRATIONS.format("\n".join(f'    ({v}, "m{v}", ""),' for v in range(1, n + 1)))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    sh(root, "init", "-q", "-b", "main")
    (root / ".gitignore").write_text("data/\nweb/releases/\nweb/dist\n")
    return root


@pytest.fixture
def two_commits(repo: Path) -> tuple[str, str]:
    base = {
        "autotrade/__init__.py": "",
        "autotrade/db/__init__.py": "",
        "web/package.json": "{}\n",
        "README.md": "quant\n",
    }
    a = commit(repo, {**base, "autotrade/db/migrations.py": migrations(2)}, "a")
    b = commit(repo, {"autotrade/db/migrations.py": migrations(3)}, "b: a migration")
    return a, b


def make_db(path: Path, version: int, sessions: int = 1, rows: Sequence[str] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name, at)")
        for v in range(1, version + 1):
            conn.execute("INSERT INTO schema_migrations VALUES (?, 'x', 'y')", (v,))
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, revoked_at TEXT, revoked_why TEXT)"
        )
        for i in range(sessions):
            conn.execute("INSERT INTO sessions VALUES (?, NULL, NULL)", (f"s{i}",))
        conn.execute("CREATE TABLE notes (text TEXT)")
        for row in rows:
            conn.execute("INSERT INTO notes VALUES (?)", (row,))
        conn.commit()
    finally:
        conn.close()


def notes(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("SELECT text FROM notes ORDER BY rowid")]
    finally:
        conn.close()


def add_live(
    path: Path,
    *,
    start: bool = False,
    mode: str | None = None,
    orders: Sequence[tuple[str, str | None]] = (),
) -> None:
    """The live ledger's traces in a database (the columns release.py reads): its start event,
    the stored mode, and broker orders as (state, cancel_state)."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS events (ledger_id TEXT, kind TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS broker_orders (state TEXT, cancel_state TEXT)")
        conn.execute("INSERT INTO events VALUES ('paper', 'start')")  # paper's is not the live one
        if start:
            conn.execute("INSERT INTO events VALUES ('live', 'start')")
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('mode', ?)", (mode or "paper",))
        conn.executemany("INSERT INTO broker_orders VALUES (?, ?)", orders)
        conn.commit()
    finally:
        conn.close()


class FakeNpm:
    """`npm ci` does nothing; `npm run build` writes dist/ with one hashed asset per build."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], cwd: Path) -> None:
        self.calls.append(list(args))
        if list(args) == ["run", "build"]:
            n = len([c for c in self.calls if c == ["run", "build"]])
            (cwd / "dist" / "assets").mkdir(parents=True)
            (cwd / "dist" / "index.html").write_text(f"<title>build {n}</title>")
            (cwd / "dist" / "assets" / f"index-{n:08d}.js").write_text(f"build {n}")


class FakeSystemd:
    def __init__(self, active: str = "active") -> None:
        self.state = active
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        self.calls.append(list(args))
        if args[0] == "stop":
            self.state = "inactive"
        elif args[0] == "start":
            self.state = "active"
        return self.state if args[0] == "is-active" else "enabled"


# ── schema ───────────────────────────────────────────────────────────────────────────────


def test_code_schema_of_a_commit_without_checking_it_out(
    repo: Path, two_commits: tuple[str, str]
) -> None:
    a, b = two_commits
    assert rel.code_schema(repo, a) == 2
    assert rel.code_schema(repo, b) == 3
    assert sh(repo, "rev-parse", "HEAD") == b  # nothing was checked out
    empty = commit(repo, {"README": "x"}, "c")
    sh(repo, "rm", "-q", "-r", "autotrade")
    no_autotrade = commit(repo, {}, "d: no autotrade")
    assert rel.code_schema(repo, empty) == 3
    assert rel.code_schema(repo, no_autotrade) is None
    with pytest.raises(rel.ReleaseError, match="rev-parse"):
        rel.commit_of(repo, "nope")


def test_code_schema_reports_broken_code(repo: Path) -> None:
    sha = commit(repo, {"autotrade/__init__.py": "", "autotrade/db/migrations.py": "x = ("}, "a")
    with pytest.raises(rel.ReleaseError, match="cannot read the schema"):
        rel.code_schema(repo, sha)


def test_stored_and_backup_schemas(tmp_path: Path) -> None:
    paths = rel.Paths(tmp_path)
    assert rel.stored_schema(paths.db) is None
    make_db(paths.db, 3)
    assert rel.stored_schema(paths.db) == 3
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert rel.stored_schema(empty) == 0
    for stamp, version in (("20261009-090000", 2), ("20261010-080000", 3), ("20261010-090000", 2)):
        make_db(paths.backups / f"autotrade-predeploy-{stamp}.db", version)
    (paths.backups / "autotrade-predeploy-20261010-100000.db").write_bytes(b"garbage" * 100)
    (paths.backups / "autotrade-2026-10-10.db").write_bytes(b"a daily backup, not a predeploy one")
    assert [p.name for p in rel.predeploy_backups(paths)][:2] == [
        "autotrade-predeploy-20261010-100000.db",
        "autotrade-predeploy-20261010-090000.db",
    ]
    # The newest predeploy backup at that schema; the broken one is skipped.
    assert rel.backup_for(paths, 2) == paths.backups / "autotrade-predeploy-20261010-090000.db"
    assert rel.backup_for(paths, 3) == paths.backups / "autotrade-predeploy-20261010-080000.db"
    assert rel.backup_for(paths, 9) is None
    assert not list(paths.backups.glob("*-wal"))  # backups are read immutable
    assert rel.backup_for(rel.Paths(tmp_path / "nothing"), 2) is None


def test_a_backup_that_fails_its_check_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "autotrade-predeploy-20261010-090000.db"
    make_db(bad, 2, rows=["x" * 5000] * 50)
    data = bytearray(bad.read_bytes())
    data[4096 * 3 : 4096 * 3 + 64] = b"\x00" * 64  # damage a page
    bad.write_bytes(bytes(data))
    with pytest.raises((rel.ReleaseError, sqlite3.DatabaseError)):
        rel.backup_schema(bad)


# ── web releases ───────────────────────────────────────────────────────────────────────────


def test_build_switch_carry_and_prune(repo: Path, two_commits: tuple[str, str]) -> None:
    a, b = two_commits
    paths = rel.Paths(repo)
    npm = FakeNpm()
    first = rel.web_build(paths, a, T0, npm)
    assert first == {"result": "ok", "release": f"20261010T090000Z-{a[:12]}", "commit": a}
    assert npm.calls == [["ci", "--ignore-scripts", "--no-audit", "--no-fund"], ["run", "build"]]
    assert not paths.dist.exists()  # building never touches the live tree
    assert sh(repo, "status", "--porcelain") == ""
    assert rel.find_release(paths, a) == first["release"]
    switched = rel.web_switch(paths, first["release"], T0)
    assert (switched["previous"], switched["carried"]) == (None, 0)
    assert os.readlink(paths.dist) == f"releases/{first['release']}"
    assert (paths.dist / "index.html").read_text() == "<title>build 1</title>"
    assert rel.live_release(paths) == first["release"]

    # The same commit again (a deploy run again after a later step failed): no second build.
    again = rel.web_build(paths, a, T0, npm)
    assert again == {**first, "reused": True}
    assert len(npm.calls) == 2

    second = rel.web_build(paths, b, T0 + timedelta(minutes=1), npm)["release"]
    switched = rel.web_switch(paths, second, T0)
    assert (switched["previous"], switched["carried"]) == (first["release"], 1)
    # A page loaded before the switch still finds its chunk (no name is overwritten).
    assert sorted(p.name for p in (paths.dist / "assets").iterdir()) == [
        "index-00000001.js",
        "index-00000002.js",
    ]
    meta = json.loads((paths.releases / f"{second}.json").read_text())
    assert meta["own"] == ["index-00000002.js"]  # carried assets are not its own

    # Back to the first (a rollback): it gets the second's assets too.
    rel.web_switch(paths, first["release"], T0)
    assert (paths.dist / "assets" / "index-00000002.js").is_file()

    built = [second]
    for i in range(2, 9):
        built.append(
            rel.web_build(paths, b, T0 + timedelta(minutes=i), npm, reuse=False)["release"]
        )
    (paths.releases / ".20261010T000000Z-0123456789ab.partial").mkdir()
    (paths.releases / "20261009T000000Z-0123456789ab.json").write_text("{}")  # orphan
    (paths.releases / "notes.txt").write_text("not ours")
    switched = rel.web_switch(paths, built[-1], T0)
    kept = sorted(r.id for r in rel.releases(paths))
    # The newest four, the live one and the one it replaced (the first, live before).
    assert kept == sorted([first["release"], *built[-4:]])
    assert ".20261010T000000Z-0123456789ab.partial" in switched["removed"]
    assert "20261009T000000Z-0123456789ab.json" in switched["removed"]
    assert (paths.releases / "notes.txt").exists()
    with pytest.raises(rel.ReleaseError, match="no complete release"):
        rel.web_switch(paths, "20200101T000000Z-0123456789ab", T0)


def test_a_plain_dist_folder_becomes_the_legacy_release(
    repo: Path, two_commits: tuple[str, str]
) -> None:
    paths = rel.Paths(repo)
    (paths.dist / "assets").mkdir(parents=True)
    (paths.dist / "index.html").write_text("<title>before releases</title>")
    (paths.dist / "assets" / "index-old00000.js").write_text("old")
    assert rel.live_release(paths) == "dir"
    new = rel.web_build(paths, two_commits[1], T0, FakeNpm())["release"]
    switched = rel.web_switch(paths, new, T0)
    assert switched["previous"] == "20261010T090000Z-legacy"
    assert (paths.releases / "20261010T090000Z-legacy" / "index.html").is_file()
    assert (paths.dist / "assets" / "index-old00000.js").read_text() == "old"  # carried
    assert rel.find_release(paths, two_commits[1]) == new


def test_a_build_needs_web_and_an_index(repo: Path, two_commits: tuple[str, str]) -> None:
    paths = rel.Paths(repo)
    sh(repo, "rm", "-q", "-r", "web")
    no_web = commit(repo, {}, "no web")
    with pytest.raises(rel.ReleaseError, match="has no web/"):
        rel.web_build(paths, no_web, T0, FakeNpm())
    with pytest.raises(rel.ReleaseError, match=r"no index\.html"):
        rel.web_build(paths, two_commits[0], T0, lambda args, cwd: None)
    first = rel.web_build(paths, two_commits[0], T0, FakeNpm())["release"]
    assert rel.web_build(paths, two_commits[0], T0, FakeNpm())["release"] == first  # reused
    with pytest.raises(rel.ReleaseError, match="exists already"):  # a forced rebuild, same second
        rel.web_build(paths, two_commits[0], T0, FakeNpm(), reuse=False)
    assert rel.releases(paths)[0].id == first


def _nvm(home: Path, *versions: str) -> None:
    for v in versions:
        folder = home / ".nvm" / "versions" / "node" / v / "bin"
        folder.mkdir(parents=True)
        (folder / "node").write_text("")
        (folder / "npm").write_text("")


def test_npm_failures_are_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(list(args[0]))
        if args[0][-1] == "-v":
            return subprocess.CompletedProcess(args[0], 0, stdout="v24.14.1\n")
        return subprocess.CompletedProcess(args[0], 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    _nvm(tmp_path, "v20.20.2", "v24.14.1", "v24.9.0")
    with pytest.raises(rel.ReleaseError, match="npm ci failed"):
        rel.npm(["ci"], tmp_path, home=tmp_path)
    newest = tmp_path / ".nvm" / "versions" / "node" / "v24.14.1" / "bin"
    assert seen == [[str(newest / "node"), "-v"], [str(newest / "npm"), "ci"]]


def test_the_web_build_needs_a_new_enough_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server's system node (v20) cannot build the web (it ran .ts scripts as
    ERR_UNKNOWN_FILE_EXTENSION on 2026-10-12): stop with the reason before npm runs."""
    calls: list[list[str]] = []

    def system_node(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(args[0]))
        return subprocess.CompletedProcess(args[0], 0, stdout="v20.20.2\n")

    monkeypatch.setattr(subprocess, "run", system_node)
    with pytest.raises(rel.ReleaseError, match=r"node v20\.20\.2 is older"):
        rel.npm(["ci"], tmp_path, home=tmp_path)  # no nvm under this home: PATH's node
    assert calls == [["node", "-v"]]  # npm itself never ran
    assert rel.node_bin(tmp_path) is None
    _nvm(tmp_path, "v24.12.0", "not-a-version")
    assert rel.node_bin(tmp_path) == tmp_path / ".nvm/versions/node/v24.12.0/bin"


# ── restore, locks, rollback ─────────────────────────────────────────────────────────────


def test_restore_db_sets_the_live_database_aside(tmp_path: Path) -> None:
    paths = rel.Paths(tmp_path)
    make_db(paths.db, 3, sessions=2, rows=["after the deploy"])
    backup = paths.backups / "autotrade-predeploy-20261010-090000.db"
    make_db(backup, 2, sessions=3, rows=["before the deploy"])
    report = rel.restore_db(paths, backup, T0)
    assert report == {
        "backup": str(backup),
        "schema": 2,
        "setAside": str(paths.backups / "autotrade-replaced-20261010-090000.db"),
        "closedSessions": 3,
    }
    assert rel.stored_schema(paths.db) == 2
    assert notes(paths.db) == ["before the deploy"]
    assert notes(Path(report["setAside"])) == ["after the deploy"]  # kept, not deleted
    conn = sqlite3.connect(paths.db)
    try:
        why = {r[0] for r in conn.execute("SELECT revoked_why FROM sessions")}
    finally:
        conn.close()
    assert why == {"rollback"}  # no session ended after the backup comes back
    conn = sqlite3.connect(paths.db)
    try:
        stamps = {r[0] for r in conn.execute("SELECT revoked_at FROM sessions")}
    finally:
        conn.close()
    # The app's storage format: the code a rollback returns to (Python 3.10) reads it with
    # datetime.fromisoformat, which refuses a trailing 'Z' (a 500 for every logged-in browser).
    assert stamps == {"2026-10-10T09:00:00+00:00"}
    assert {datetime.fromisoformat(t) for t in stamps} == {T0}
    assert (paths.db.stat().st_mode & 0o777) == 0o600
    assert not paths.db.with_name("autotrade.db.restore").exists()
    assert notes(backup) == ["before the deploy"]  # the backup itself is untouched


def test_held_waits_for_the_jobs_lock(tmp_path: Path) -> None:
    lock = tmp_path / "autotrade.db-jobs.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(rel.ReleaseError, match="stayed busy"), rel.held(lock, 0.05, 0.01):
            pytest.fail("the lock was taken twice")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    with rel.held(lock, 0.05, 0.01):
        pass


@pytest.fixture
def deployed(repo: Path, two_commits: tuple[str, str]) -> rel.Paths:
    """The server after deploying b over a: b's migration ran after a predeploy backup."""
    a, b = two_commits
    paths = rel.Paths(repo)
    npm = FakeNpm()
    rel.web_switch(paths, rel.web_build(paths, a, T0, npm)["release"], T0)
    make_db(paths.backups / "autotrade-predeploy-20261010-093000.db", 2, rows=["at a"])
    make_db(paths.db, 3, sessions=2, rows=["at a", "written by b"])
    rel.web_switch(paths, rel.web_build(paths, b, T0 + timedelta(hours=1), npm)["release"], T0)
    rel.record(paths, {"kind": "deploy", "service": "autotrade", "from": a, "to": b}, T0)
    return paths


def test_rollback_plan_restores_when_the_schema_went_back(
    deployed: rel.Paths, two_commits: tuple[str, str]
) -> None:
    a, b = two_commits
    plan = rel.rollback_plan(deployed, None, FakeSystemd())
    assert (plan["head"], plan["target"]) == (b, a)
    assert plan["schema"] == {"stored": 3, "code": 2}
    assert plan["restore"] == str(deployed.backups / "autotrade-predeploy-20261010-093000.db")
    assert plan["release"] == rel.find_release(deployed, a)
    assert (plan["autotrade"], plan["serviceActive"]) == (True, True)
    assert "dashboardChanged" not in plan
    assert "leaves the live DB" in plan["say"][1]


def test_rollback_apply_moves_code_database_and_web_back(
    deployed: rel.Paths, two_commits: tuple[str, str]
) -> None:
    a, b = two_commits
    plan = rel.rollback_plan(deployed, None, FakeSystemd())
    systemd = FakeSystemd()
    report = rel.rollback_apply(
        deployed, plan["target"], plan["restore"], plan["release"], T0, systemd, 0.1, 0.1
    )
    assert report["wasActive"] is True
    assert systemd.calls == [["is-active", "autotrade"], ["stop", "autotrade"]]
    assert sh(deployed.root, "rev-parse", "HEAD") == a
    assert sh(deployed.root, "branch", "--show-current") == ""  # detached
    assert (
        sh(deployed.root, "rev-parse", "main") == b
    )  # main keeps b: the next deploy fast-forwards
    assert notes(deployed.db) == ["at a"]
    assert notes(Path(report["restored"]["setAside"])) == ["at a", "written by b"]
    assert rel.live_release(deployed) == plan["release"]
    # Rolled back already: no default target any more.
    with pytest.raises(rel.ReleaseError, match="no deploy record ends at the server's HEAD"):
        rel.rollback_plan(deployed, None, FakeSystemd())


def test_rollback_keeps_the_database_when_the_schema_did_not_change(
    repo: Path, two_commits: tuple[str, str]
) -> None:
    _, b = two_commits
    paths = rel.Paths(repo)
    c = commit(repo, {"README.md": "quant, changed\n"}, "c: no schema change")
    make_db(paths.db, 3, rows=["kept"])
    plan = rel.rollback_plan(paths, b, FakeSystemd("inactive"))
    assert (plan["restore"], plan["serviceActive"]) == (None, False)
    assert plan["release"] is None  # never built: deploy.sh builds it first
    assert "fits that code" in plan["say"][1]
    systemd = FakeSystemd("inactive")
    report = rel.rollback_apply(paths, b, None, None, T0, systemd, 0.1, 0.1)
    assert (report["restored"], report["switched"], report["wasActive"]) == (None, None, False)
    assert systemd.calls == [["is-active", "autotrade"]]  # not running: not touched
    assert notes(paths.db) == ["kept"]
    assert sh(repo, "rev-parse", "HEAD") == b
    assert c != b


@pytest.mark.parametrize(
    ("stored", "backups", "match"),
    [
        (1, [], "older than that code"),
        (3, [], "no predeploy backup at schema 2"),
    ],
)
def test_rollback_plan_refusals(
    repo: Path, two_commits: tuple[str, str], stored: int, backups: list[int], match: str
) -> None:
    a, _ = two_commits
    paths = rel.Paths(repo)
    make_db(paths.db, stored)
    with pytest.raises(rel.ReleaseError, match=match):
        rel.rollback_plan(paths, a, FakeSystemd())


def test_rollback_plan_other_refusals(repo: Path, two_commits: tuple[str, str]) -> None:
    a, b = two_commits
    paths = rel.Paths(repo)
    with pytest.raises(rel.ReleaseError, match=r"at \w+ already"):
        rel.rollback_plan(paths, b, FakeSystemd())
    with pytest.raises(rel.ReleaseError, match="no deploy record"):
        rel.rollback_plan(paths, None, FakeSystemd())
    (repo / "README.md").write_text("edited on the server")
    with pytest.raises(rel.ReleaseError, match="working tree has changes"):
        rel.rollback_plan(paths, a, FakeSystemd())
    with pytest.raises(rel.ReleaseError, match="working tree has changes"):
        rel.rollback_apply(paths, a, None, None, T0, FakeSystemd(), 0.1, 0.1)
    sh(repo, "checkout", "-q", "--", "README.md")
    sh(repo, "rm", "-q", "-r", "autotrade")
    gone = commit(repo, {}, "no autotrade")
    make_db(paths.db, 3)
    sh(repo, "checkout", "-q", b)
    with pytest.raises(rel.ReleaseError, match="has no autotrade/"):
        rel.rollback_plan(paths, gone, FakeSystemd())


def test_rollback_apply_reports_where_it_stopped(
    deployed: rel.Paths, two_commits: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = two_commits
    plan = rel.rollback_plan(deployed, None, FakeSystemd())
    with pytest.raises(rel.ReleaseError, match="no complete release"):
        rel.rollback_apply(deployed, a, None, "20200101T000000Z-0123456789ab", T0)
    with pytest.raises(rel.ReleaseError, match="no backup"):
        rel.rollback_apply(deployed, a, "/nonexistent.db", None, T0)

    real_git = rel.git

    def failing_checkout(root: Path, *args: str) -> str:
        if args[0] == "checkout":
            raise rel.ReleaseError("git checkout: locked index")
        return real_git(root, *args)

    monkeypatch.setattr(rel, "git", failing_checkout)
    systemd = FakeSystemd()
    with pytest.raises(
        rel.ReleaseError, match=r"nothing changed; autotrade\.service started again"
    ):
        rel.rollback_apply(deployed, a, plan["restore"], plan["release"], T0, systemd, 0.1, 0.1)
    assert systemd.state == "active"
    monkeypatch.setattr(rel, "git", real_git)

    def broken_restore(*args: Any) -> Any:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(rel, "restore_db", broken_restore)
    with pytest.raises(rel.ReleaseError, match="database was NOT restored"):
        rel.rollback_apply(
            deployed, a, plan["restore"], plan["release"], T0, FakeSystemd(), 0.1, 0.1
        )
    monkeypatch.undo()
    sh(deployed.root, "checkout", "-q", b)

    def broken_switch(*args: Any) -> Any:
        raise OSError("read-only file system")

    monkeypatch.setattr(rel, "web_switch", broken_switch)
    with pytest.raises(rel.ReleaseError, match="web/dist was NOT switched"):
        rel.rollback_apply(deployed, a, None, plan["release"], T0, FakeSystemd(), 0.1, 0.1)


# ── the live ledger and a rollback's restore (autotrade/PHASE3.md) ───────────────────────


@pytest.mark.parametrize(
    ("live", "fact"),
    [
        ({"start": True}, "the live ledger has started"),
        ({"mode": "live"}, "live is on (mode 'live')"),
        ({"orders": [("sent", None)]}, "1 order(s) open at Toss or waiting for a cancel"),
        # The tick has not marked the cancel done yet: Toss may still hold the order.
        ({"orders": [("done", "requested")]}, "1 order(s) open at Toss"),
        ({"orders": [("unknown", "failed"), ("sending", None)]}, "2 order(s) open at Toss"),
    ],
)
def test_a_restore_refuses_while_the_live_db_has_the_live_ledger(
    deployed: rel.Paths, two_commits: tuple[str, str], live: dict[str, Any], fact: str
) -> None:
    """Rolling back past schema 6 used to drop the live ledger silently: the copy restored predates
    it, and the code rolled back to has no Toss link to cancel or book an order open there."""
    _, b = two_commits
    add_live(deployed.db, **live)
    with pytest.raises(rel.ReleaseError) as refused:
        rel.rollback_plan(deployed, None, FakeSystemd())
    message = str(refused.value)
    assert fact in message
    assert "has no Toss link" in message  # the target's schema 2 is before the live link (6)
    assert "Turn live off on the mode screen (실전 끄기)" in message
    assert "then roll back with --drop-live" in message
    assert sh(deployed.root, "rev-parse", "HEAD") == b  # nothing changed
    assert notes(deployed.db) == ["at a", "written by b"]


def test_drop_live_lets_the_restore_go_and_says_what_leaves(
    deployed: rel.Paths, two_commits: tuple[str, str]
) -> None:
    a, _ = two_commits
    add_live(deployed.db, start=True, mode="live", orders=[("sent", "requested"), ("done", None)])
    plan = rel.rollback_plan(deployed, None, FakeSystemd(), drop_live=True)
    assert plan["live"] == {"started": True, "on": True, "openOrders": 1}
    assert "leaves the live DB" in plan["say"][1]  # the restore line comes first, as before
    assert plan["say"][2].startswith(
        "live ledger: live is on (mode 'live'); 1 order(s) open at Toss or waiting for a cancel;"
        " the live ledger has started. --drop-live: its record (start, orders, fills,"
        " conversions) leaves the live DB"
    )
    assert plan["say"][3].startswith("that code has no Toss link")
    report = rel.rollback_apply(
        deployed, a, plan["restore"], plan["release"], T0, FakeSystemd(), 0.1, 0.1, drop_live=True
    )
    assert report["liveDropped"] == {"started": True, "on": True, "openOrders": 1}
    assert notes(deployed.db) == ["at a"]
    aside = Path(report["restored"]["setAside"])
    assert rel.live_ledger(aside) == rel.LiveLedger(True, True, 1)  # kept aside, not deleted
    assert rel.live_ledger(deployed.db) == rel.LiveLedger(False, False, 0)


def test_the_apply_looks_again_once_nothing_writes(
    deployed: rel.Paths, two_commits: tuple[str, str]
) -> None:
    """Live turned on (or an order sent) between the plan and the apply: the apply refuses too,
    after the service has stopped and the jobs are held, and starts the service again."""
    a, b = two_commits
    plan = rel.rollback_plan(deployed, None, FakeSystemd())
    assert plan["live"] is None
    add_live(deployed.db, start=True, mode="live")
    systemd = FakeSystemd()
    with pytest.raises(
        rel.ReleaseError,
        match=r"--drop-live.*\(nothing changed; autotrade\.service started again\)",
    ):
        rel.rollback_apply(deployed, a, plan["restore"], plan["release"], T0, systemd, 0.1, 0.1)
    assert systemd.calls == [
        ["is-active", "autotrade"],
        ["stop", "autotrade"],
        ["start", "autotrade"],
    ]
    assert sh(deployed.root, "rev-parse", "HEAD") == b
    assert notes(deployed.db) == ["at a", "written by b"]
    stopped = FakeSystemd("inactive")
    with pytest.raises(rel.ReleaseError, match=r"\(nothing changed\)$"):
        rel.rollback_apply(deployed, a, plan["restore"], plan["release"], T0, stopped, 0.1, 0.1)
    assert stopped.calls == [["is-active", "autotrade"]]
    report = rel.rollback_apply(
        deployed, a, plan["restore"], plan["release"], T0, FakeSystemd(), 0.1, 0.1, drop_live=True
    )
    assert report["liveDropped"] == {"started": True, "on": True, "openOrders": 0}
    assert sh(deployed.root, "rev-parse", "HEAD") == a


def test_without_a_restore_the_live_ledger_stays_where_it_is(
    repo: Path, two_commits: tuple[str, str]
) -> None:
    """A rollback that keeps the database (same schema) keeps the live ledger and its Toss code."""
    _, b = two_commits
    commit(repo, {"README.md": "quant, changed\n"}, "c: no schema change")
    paths = rel.Paths(repo)
    make_db(paths.db, 3)
    add_live(paths.db, start=True, mode="live", orders=[("sent", None)])
    plan = rel.rollback_plan(paths, b, FakeSystemd())
    assert (plan["restore"], plan["live"]) == (None, None)


def test_the_live_ledger_is_read_from_the_app_schema(tmp_path: Path) -> None:
    """release.py reads the app's tables without importing it: the names it uses are the real
    ones (a schema-6 database made by the app's migrations), and older or empty ones are empty."""
    from autotrade.db.connection import connect
    from autotrade.db.migrations import migrate

    db = tmp_path / "autotrade.db"
    conn = connect(db)
    try:
        migrate(conn, T0)
    finally:
        conn.close()
    assert rel.live_ledger(db) == rel.LiveLedger(False, False, 0)
    raw = sqlite3.connect(db)  # no foreign keys: only the columns release.py reads matter
    try:
        at = "2026-10-13T00:00:00+00:00"
        raw.execute(
            "INSERT INTO events (ledger_id, kind, event_date, occurred_at, created_at,"
            " updated_at) VALUES ('live', 'start', '2026-10-13', ?, ?, ?)",
            (at, at, at),
        )
        raw.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES ('mode', 'live', ?)", (at,)
        )
        raw.execute(
            "INSERT INTO broker_orders (order_id, ledger_id, client_order_id, state, updated_at)"
            " VALUES (1, 'live', 'at-1', 'sent', ?)",
            (at,),
        )
        raw.commit()
    finally:
        raw.close()
    assert rel.live_ledger(db) == rel.LiveLedger(True, True, 1)
    make_db(tmp_path / "old.db", 5)  # no events, settings or broker_orders tables
    assert rel.live_ledger(tmp_path / "old.db") == rel.LiveLedger(False, False, 0)
    assert rel.live_ledger(tmp_path / "none.db") == rel.LiveLedger(False, False, 0)


def test_no_predeploy_copy_names_the_daily_copies(repo: Path, two_commits: tuple[str, str]) -> None:
    """Five predeploy copies are kept; a rollback several deploys back finds none at its schema.
    The refusal names the daily copies at that schema, and its advice works."""
    a, b = two_commits
    paths = rel.Paths(repo)
    make_db(paths.db, 3, rows=["now"])
    make_db(paths.backups / "autotrade-predeploy-20261012-090000.db", 3)
    make_db(paths.backups / "autotrade-2026-10-08.db", 2, rows=["daily 10/8"])
    make_db(paths.backups / "autotrade-2026-10-09.db", 2, rows=["daily 10/9"])
    make_db(paths.backups / "autotrade-2026-10-12.db", 3)
    (paths.backups / "autotrade-2026-10-10.db").write_bytes(b"not a database" * 100)
    with pytest.raises(rel.ReleaseError) as refused:
        rel.rollback_plan(paths, a, FakeSystemd())
    message = str(refused.value)
    assert message.startswith("no predeploy backup at schema 2 (older ones are pruned)")
    assert (
        "daily copies at that schema: autotrade-2026-10-09.db, autotrade-2026-10-08.db." in message
    )
    advice = (
        "cp -p data/backup/autotrade/autotrade-2026-10-09.db"
        " data/backup/autotrade/autotrade-predeploy-20261009-000000.db"
    )
    assert advice in message
    shutil.copy2(
        paths.backups / "autotrade-2026-10-09.db",
        paths.backups / "autotrade-predeploy-20261009-000000.db",
    )
    plan = rel.rollback_plan(paths, a, FakeSystemd())
    assert plan["restore"] == str(paths.backups / "autotrade-predeploy-20261009-000000.db")
    assert b != a


# ── record, status, health, the command line ─────────────────────────────────────────────


def test_status_and_records(deployed: rel.Paths, two_commits: tuple[str, str]) -> None:
    _, b = two_commits
    report = rel.status(deployed, FakeSystemd())
    assert (report["head"], report["branch"], report["schema"]) == (
        b,
        "main",
        {"stored": 3, "code": 3},
    )
    assert report["release"] == rel.find_release(deployed, b)
    assert report["service"] == {"active": "active", "enabled": "enabled"}
    assert report["last"]["to"] == b
    assert rel.last_record(rel.Paths(deployed.root / "none")) is None


def test_health_needs_the_api_the_page_and_the_origin_rule() -> None:
    answers = iter([503, 200, 200, 200])

    def warming(path: str, method: str, origin: str | None) -> int:
        if path == "/api/auth/logout":
            return 204 if origin == rel.HEALTH_BASE else 403
        return next(answers)

    assert rel.health(warming, tries=3, pause_s=0) == {
        "result": "ok",
        "healthz": 200,
        "page": 200,
        "sameSite": 204,
        "sibling": 403,
    }
    with pytest.raises(rel.ReleaseError, match="health check failed"):
        rel.health(lambda path, method, origin: 503, tries=2, pause_s=0)
    with pytest.raises(rel.ReleaseError, match="origin rule misbehaves"):
        rel.health(lambda path, method, origin: 200 if method == "GET" else 204, pause_s=0)
    # A rollback may return to code from before the origin rule: both POSTs pass there.
    before_rule = rel.health(
        lambda path, method, origin: 200 if method == "GET" else 204,
        pause_s=0,
        origin_optional=True,
    )
    assert (before_rule["result"], before_rule["originRule"]) == ("ok", "absent")
    with pytest.raises(rel.ReleaseError, match="origin rule misbehaves"):
        rel.health(
            lambda path, method, origin: 200 if method == "GET" else 500,
            pause_s=0,
            origin_optional=True,
        )


def test_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str, str | None]] = []

    class Answer:
        status = 204

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def answer(request: Any, timeout: float) -> Answer:
        seen.append((request.full_url, request.get_method(), request.get_header("Origin")))
        if request.full_url.endswith("/refused"):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", Message(), None)
        if request.full_url.endswith("/down"):
            raise urllib.error.URLError("connection refused")
        return Answer()

    monkeypatch.setattr(urllib.request, "urlopen", answer)
    assert rel.http_status("/api/auth/logout", "POST", "https://x.example") == 204
    assert rel.http_status("/refused") == 403
    assert rel.http_status("/down") == 0  # nothing answers
    assert seen[0] == (f"{rel.HEALTH_BASE}/api/auth/logout", "POST", "https://x.example")


def test_the_command_line(
    deployed: rel.Paths, two_commits: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = two_commits

    def run(*argv: str) -> tuple[int, dict[str, Any]]:
        code = rel.main(list(argv), root=deployed.root)
        return code, json.loads(capsys.readouterr().out)

    assert run("code-schema", a) == (0, {"result": "ok", "schema": 2})
    assert run("web-find", a)[1]["release"] == rel.find_release(deployed, a)
    code, out = run("record", json.dumps({"kind": "rollback", "from": b, "to": a}))
    assert (code, out["record"]["kind"]) == (0, "rollback")
    assert run("rollback-plan")[1]["result"] == "failed"  # the last record is a rollback
    code, out = run("web-switch", "20200101T000000Z-0123456789ab")
    assert (code, out["result"]) == (1, "failed")
    assert "no complete release" in out["error"]
    assert run("code-schema", "nope")[0] == 1


def test_the_command_line_passes_drop_live(
    deployed: rel.Paths,
    two_commits: tuple[str, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, _ = two_commits
    add_live(deployed.db, start=True)
    assert rel.main(["rollback-plan", a], root=deployed.root) == 1
    assert "then roll back with --drop-live" in json.loads(capsys.readouterr().out)["error"]
    seen: list[tuple[str, bool]] = []

    def plan(paths: rel.Paths, commit: str | None, *, drop_live: bool = False) -> dict[str, Any]:
        seen.append(("plan", drop_live))
        return {"result": "ok"}

    def apply(*args: Any, drop_live: bool = False, **kwargs: Any) -> dict[str, Any]:
        seen.append(("apply", drop_live))
        return {"result": "ok"}

    monkeypatch.setattr(rel, "rollback_plan", plan)
    monkeypatch.setattr(rel, "rollback_apply", apply)
    for argv in (["rollback-plan", "--drop-live"], ["rollback-apply", a, "--drop-live"]):
        assert rel.main(argv, root=deployed.root) == 0
    assert rel.main(["rollback-apply", a], root=deployed.root) == 0
    assert seen == [("plan", True), ("apply", True), ("apply", False)]
