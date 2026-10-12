"""The server-side steps of deploy/deploy.sh: web releases, schema versions, the restore of a
rollback, the deploy record and the health check. Standard library only; never imported by the app.

deploy.sh pipes this file to the server's Python:

    ssh oracle-instance 'cd ~/portfolio-dashboard && .venv/bin/python - <command> …' < this file

so a rollback runs this (the laptop's) version, not the one of the commit it checks out. Every
command prints one JSON object on stdout ({"result": "failed", "error": …} and exit 1 on failure);
build output goes to stderr.

Layout on the server (paths relative to the repository root, the working directory):
  web/releases/<id>/         one build of web/; id = <UTC yyyymmddTHHMMSSZ>-<commit, 12 hex>
                             (or <UTC…>-legacy: the web/dist folder of before releases existed)
  web/releases/<id>.json     {id, commit, builtAt, own: the hashed asset names this build made}
  web/dist -> releases/<id>  the live release: a symlink, switched by one rename(2)
  data/deploy/history.jsonl  one line per deploy and rollback
  data/backup/autotrade/autotrade-predeploy-<UTC yyyymmdd-HHMMSS>.db
                             written by `python -m autotrade.jobs migrate --predeploy` (deploy.sh)

Releases: a build is made from `git archive <commit> web` in a temporary folder (npm ci
--ignore-scripts, npm run build), never in the live tree, so a failed build changes nothing. The
newest KEEP releases stay, plus the live one and the one before it. On every switch the new live
release also gets the hashed assets of the releases it replaces (no name is overwritten: a hash
names its content), so a page loaded before the switch still finds its lazy chunks.

Rollback: `rollback-plan` reads (nothing changes); `rollback-apply` takes the jobs and AI locks of
data/autotrade.db (a tick or an AI run never sees the switch), stops autotrade.service, checks out
the commit (detached HEAD: main keeps the rolled-back commit, so the next deploy fast-forwards from
it), restores the newest predeploy backup at that commit's schema when the database is newer than
that code — the replaced database is moved aside, not deleted, and every session in the restored
copy is closed (sessions the owner ended after the backup must not come back) — and switches
web/dist back. deploy.sh then starts the services and checks them.
"""

from __future__ import annotations

import argparse
import fcntl
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEEP = 4  # releases kept besides the live one and the one before it
RELEASE_ID = re.compile(r"^\d{8}T\d{6}Z-(?:[0-9a-f]{12}|legacy)$")
PREDEPLOY = re.compile(r"^autotrade-predeploy-(\d{8}-\d{6})\.db$")
JOBS_LOCK_WAIT_S = 120.0  # a tick finishes within this
AI_LOCK_WAIT_S = 900.0  # an AI call has no time limit; wait this long, then give up unchanged
SERVICE = "autotrade"
HEALTH_BASE = "http://127.0.0.1:8890"

Runner = Callable[[Sequence[str], Path], None]  # npm <args> in <folder>
Systemctl = Callable[[Sequence[str]], str]  # systemctl <args> -> its first line of output
Fetch = Callable[[str, str, str | None], int]  # (path, method, Origin) -> HTTP status


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def web(self) -> Path:
        return self.root / "web"

    @property
    def releases(self) -> Path:
        return self.web / "releases"

    @property
    def dist(self) -> Path:
        return self.web / "dist"

    @property
    def db(self) -> Path:
        return self.root / "data" / "autotrade.db"

    @property
    def backups(self) -> Path:
        return self.root / "data" / "backup" / "autotrade"

    @property
    def history(self) -> Path:
        return self.root / "data" / "deploy" / "history.jsonl"

    def lock(self, kind: str) -> Path:
        return self.db.with_name(f"{self.db.name}-{kind}.lock")


def _utc(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _db_time(at: datetime) -> str:
    """A timestamp written into the app's database: its own storage format (autotrade/timeutil.py
    to_iso, '+00:00'). Python 3.10's datetime.fromisoformat refuses a trailing 'Z', and the code a
    rollback returns to reads these columns that way."""
    return at.astimezone(timezone.utc).isoformat(timespec="seconds")


# ── git ────────────────────────────────────────────────────────────────────────────────────


def _git_env() -> dict[str, str]:
    """Untranslated git messages (they go into errors and logs)."""
    return {**os.environ, "LC_ALL": "C"}


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=_git_env()
    )
    if done.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    return done.stdout.strip()


def commit_of(root: Path, ref: str) -> str:
    return git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def export(root: Path, commit: str, subdir: str, dest: Path) -> bool:
    """`git archive <commit> <subdir>` unpacked under dest. False when the commit has no subdir."""
    exists = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}:{subdir}"],
        capture_output=True,
        env=_git_env(),
    )
    if exists.returncode != 0:
        commit_of(root, commit)  # an unknown commit is an error, a missing folder is not
        return False
    done = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", commit, subdir],
        capture_output=True,
        env=_git_env(),
    )
    if done.returncode != 0:
        raise ReleaseError(f"git archive {commit} {subdir}: {done.stderr.decode().strip()}")
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:
        if hasattr(tarfile, "data_filter"):  # 3.10.12+ (the server's): plain files only
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover — an older 3.10; the archive is our own repository's
            tar.extractall(dest)
    return True


# ── schema ─────────────────────────────────────────────────────────────────────────────────


def _read_schema(uri: str) -> int:
    conn = sqlite3.connect(uri, uri=True)
    try:
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.OperationalError:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
            if exists is None:
                return 0
            raise
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def stored_schema(db: Path) -> int | None:
    """The live database's schema version (read-only); None when there is no database."""
    if not db.exists():
        return None
    return _read_schema(db.resolve().as_uri() + "?mode=ro")


def backup_schema(backup: Path) -> int:
    """A backup's schema version, after SQLite's quick_check (immutable: no -wal/-shm made)."""
    uri = backup.resolve().as_uri() + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        verdict = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        conn.close()
    if verdict != "ok":
        raise ReleaseError(f"{backup.name} fails quick_check: {verdict}")
    return _read_schema(uri)


def code_schema(root: Path, commit: str) -> int | None:
    """The schema version the code of <commit> expects (its MIGRATIONS), without checking it
    out; None when that commit has no autotrade/."""
    with tempfile.TemporaryDirectory(prefix="autotrade-schema-") as tmp:
        if not export(root, commit, "autotrade", Path(tmp)):
            return None
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        done = subprocess.run(
            [
                sys.executable,
                "-c",
                "from autotrade.db.migrations import MIGRATIONS; print(MIGRATIONS[-1][0])",
            ],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
        )
    if done.returncode != 0:
        raise ReleaseError(f"cannot read the schema of {commit[:12]}: {done.stderr.strip()}")
    return int(done.stdout.strip())


def predeploy_backups(paths: Paths) -> list[Path]:
    """Predeploy backups, newest first."""
    if not paths.backups.is_dir():
        return []
    found = [p for p in paths.backups.iterdir() if PREDEPLOY.match(p.name)]
    return sorted(found, key=lambda p: p.name, reverse=True)


def backup_for(paths: Paths, version: int) -> Path | None:
    """The newest predeploy backup at schema `version`: the last state that code can read."""
    for backup in predeploy_backups(paths):
        try:
            if backup_schema(backup) == version:
                return backup
        except (sqlite3.Error, ReleaseError):
            continue
    return None


# ── web releases ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Release:
    id: str
    commit: str
    own: tuple[str, ...]


def _read_meta(paths: Paths, rid: str) -> Release | None:
    meta = paths.releases / f"{rid}.json"
    if not (paths.releases / rid / "index.html").is_file() or not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text())
        return Release(rid, str(data["commit"]), tuple(str(n) for n in data.get("own", [])))
    except (ValueError, KeyError, TypeError):
        return None


def releases(paths: Paths) -> list[Release]:
    """Complete releases (folder with index.html and its .json), newest first."""
    if not paths.releases.is_dir():
        return []
    ids = sorted(
        (p.name for p in paths.releases.iterdir() if RELEASE_ID.match(p.name)), reverse=True
    )
    return [r for r in (_read_meta(paths, rid) for rid in ids) if r is not None]


def live_release(paths: Paths) -> str | None:
    """The release web/dist points at; 'dir' for a plain folder (before releases); None."""
    if paths.dist.is_symlink():
        target = Path(os.readlink(paths.dist))
        return target.name if RELEASE_ID.match(target.name) else None
    if paths.dist.is_dir():
        return "dir"
    return None


def find_release(paths: Paths, commit: str) -> str | None:
    return next((r.id for r in releases(paths) if r.commit == commit), None)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def _asset_names(folder: Path) -> tuple[str, ...]:
    assets = folder / "assets"
    if not assets.is_dir():
        return ()
    return tuple(sorted(p.name for p in assets.iterdir() if p.is_file()))


def install_release(paths: Paths, built: Path, commit: str, now: datetime) -> str:
    """Copy a finished build into web/releases/<id> (with its .json); returns the id."""
    if not (built / "index.html").is_file():
        raise ReleaseError("the build has no index.html")
    paths.releases.mkdir(parents=True, exist_ok=True)
    rid = f"{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}-{commit[:12]}"
    final = paths.releases / rid
    if final.exists():
        raise ReleaseError(f"release {rid} exists already")
    partial = paths.releases / f".{rid}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    shutil.copytree(built, partial)
    meta = {"id": rid, "commit": commit, "builtAt": _utc(now), "own": list(_asset_names(partial))}
    _write_json(paths.releases / f"{rid}.json", meta)
    os.rename(partial, final)
    return rid


NODE_MAJOR = 24  # web/package.json "engines": {"node": ">=24"}
NODE_VERSION = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def node_bin(home: Path | None = None) -> Path | None:
    """The newest nvm node's bin folder (~/.nvm/versions/node/v<x.y.z>/bin), picked the way the
    server's /usr/local/bin/claude wrapper picks it. A non-interactive ssh command (deploy.sh)
    gets only the system node on PATH, Ubuntu's v20 on the server, which cannot run the web build
    (it runs .ts scripts directly, and its packages want node >= 24). None without nvm."""
    root = (home or Path.home()) / ".nvm" / "versions" / "node"
    found: list[tuple[tuple[int, int, int], Path]] = []
    for folder in root.glob("v*/bin") if root.is_dir() else ():
        m = NODE_VERSION.fullmatch(folder.parent.name)
        if m and (folder / "node").is_file() and (folder / "npm").exists():
            found.append(((int(m[1]), int(m[2]), int(m[3])), folder))
    return max(found)[1] if found else None


def npm(args: Sequence[str], cwd: Path, home: Path | None = None) -> None:
    """npm of the newest nvm node (else PATH's), with its output on stderr (stdout is this
    command's JSON). A node older than the web's engines stops here with a plain reason instead of
    a build error deep in the toolchain."""
    env = dict(os.environ)
    folder = node_bin(home)
    if folder is not None:
        env["PATH"] = f"{folder}{os.pathsep}{env.get('PATH', '')}"
    node = str(folder / "node") if folder is not None else "node"
    try:
        version = subprocess.run(
            [node, "-v"], capture_output=True, text=True, env=env, check=False
        ).stdout.strip()
    except OSError as exc:
        raise ReleaseError(f"no node to build the web with: {exc}") from None
    m = NODE_VERSION.fullmatch(version)
    if m is None or int(m[1]) < NODE_MAJOR:
        raise ReleaseError(
            f"node {version or '?'} is older than the web needs (>= {NODE_MAJOR}): install a"
            " newer one with nvm on the server"
        )
    npm_cmd = str(folder / "npm") if folder is not None else "npm"
    done = subprocess.run(
        [npm_cmd, *args], cwd=cwd, stdout=sys.stderr, stderr=sys.stderr, env=env, check=False
    )
    if done.returncode != 0:
        raise ReleaseError(f"npm {' '.join(args)} failed (exit {done.returncode})")


def web_build(
    paths: Paths, commit: str, now: datetime, run: Runner = npm, reuse: bool = True
) -> dict[str, Any]:
    """Build web/ of <commit> outside the live tree into a new release.

    A complete release of the same commit is used again (reuse): a deploy run again after a later
    step failed (a busy lock at migrate, say) needs no second build, and the same second's id
    would collide. The build is the same either way (byte-identical from one commit), and the
    carrying of older assets happens at the switch, not here."""
    sha = commit_of(paths.root, commit)
    existing = find_release(paths, sha) if reuse else None
    if existing is not None:
        return {"result": "ok", "release": existing, "commit": sha, "reused": True}
    with tempfile.TemporaryDirectory(prefix="autotrade-web-") as tmp:
        if not export(paths.root, sha, "web", Path(tmp)):
            raise ReleaseError(f"{sha[:12]} has no web/")
        web = Path(tmp) / "web"
        run(["ci", "--ignore-scripts", "--no-audit", "--no-fund"], web)
        run(["run", "build"], web)
        rid = install_release(paths, web / "dist", sha, now)
    return {"result": "ok", "release": rid, "commit": sha}


def _adopt_plain_dist(paths: Paths, now: datetime) -> str:
    """The web/dist folder of before releases becomes the release <UTC>-legacy."""
    rid = f"{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}-legacy"
    paths.releases.mkdir(parents=True, exist_ok=True)
    os.rename(paths.dist, paths.releases / rid)
    own = list(_asset_names(paths.releases / rid))
    _write_json(paths.releases / f"{rid}.json", {"id": rid, "commit": "", "own": own})
    return rid


def _carry_assets(paths: Paths, rid: str, sources: Sequence[str]) -> list[str]:
    """Copy into release rid the own hashed assets of `sources` that it does not have."""
    target = paths.releases / rid / "assets"
    target.mkdir(exist_ok=True)
    carried: list[str] = []
    for source in sources:
        meta = _read_meta(paths, source)
        if meta is None or source == rid:
            continue
        for name in meta.own:
            src = paths.releases / source / "assets" / name
            dst = target / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
                carried.append(name)
    return carried


def _prune(paths: Paths, keep: set[str]) -> list[str]:
    """Delete releases beyond the newest KEEP (never one in `keep`), half-made builds and orphan
    .json files. Only names this module makes are touched."""
    keep = keep | {r.id for r in releases(paths)[:KEEP]}
    removed: list[str] = []
    for entry in sorted(paths.releases.iterdir()):
        name = entry.name
        if name.startswith("."):
            if not name.endswith((".partial", ".tmp")):
                continue
        elif not RELEASE_ID.match(name.removesuffix(".json")) or name.removesuffix(".json") in keep:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(name)
    return removed


def web_switch(paths: Paths, rid: str, now: datetime) -> dict[str, Any]:
    """Point web/dist at release rid with one rename; carry assets; prune."""
    if _read_meta(paths, rid) is None:
        raise ReleaseError(f"no complete release {rid}")
    previous = live_release(paths)
    if previous == "dir":
        previous = _adopt_plain_dist(paths, now)
    others = [r.id for r in releases(paths) if r.id != rid]
    sources = ([previous] if previous else []) + [r for r in others if r != previous][: KEEP - 1]
    carried = _carry_assets(paths, rid, sources)
    tmp = paths.web / f".dist-{os.getpid()}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(Path("releases") / rid, tmp)
    os.replace(tmp, paths.dist)
    removed = _prune(paths, {rid} | ({previous} if previous else set()))
    return {
        "result": "ok",
        "release": rid,
        "previous": previous,
        "carried": len(carried),
        "removed": removed,
    }


# ── locks, the database restore, systemd ─────────────────────────────────────────────────


@contextmanager
def held(path: Path, wait_s: float, poll_s: float = 1.0) -> Iterator[None]:
    """flock(2) on the jobs' own lock file (autotrade/jobs/lock.py uses the same)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ReleaseError(f"{path.name} stayed busy for {wait_s:.0f}s") from None
                time.sleep(poll_s)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def restore_db(paths: Paths, backup: Path, now: datetime) -> dict[str, Any]:
    """Put a predeploy backup in place of data/autotrade.db. The caller holds the locks and has
    stopped the service: nothing else has the database open. The replaced database (with its -wal
    and -shm, if any are left) is moved to data/backup/autotrade/autotrade-replaced-<UTC>.db."""
    version = backup_schema(backup)
    tmp = paths.db.with_name(f"{paths.db.name}.restore")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out, backup.open("rb") as src:
        shutil.copyfileobj(src, out)
        out.flush()
        os.fsync(out.fileno())
    conn = sqlite3.connect(tmp)
    try:
        has_sessions = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
        ).fetchone()
        closed = 0
        if has_sessions:
            closed = conn.execute(
                "UPDATE sessions SET revoked_at = ?, revoked_why = 'rollback'"
                " WHERE revoked_at IS NULL",
                (_db_time(now),),
            ).rowcount
        conn.commit()
    finally:
        conn.close()
    aside: Path | None = None
    if paths.db.exists():
        live = sqlite3.connect(paths.db)
        try:
            live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            live.close()
        paths.backups.mkdir(parents=True, exist_ok=True)
        aside = (
            paths.backups / f"autotrade-replaced-{now.astimezone(timezone.utc):%Y%m%d-%H%M%S}.db"
        )
        os.rename(paths.db, aside)
        for suffix in ("-wal", "-shm"):
            leftover = paths.db.with_name(paths.db.name + suffix)
            if leftover.exists():
                os.rename(leftover, aside.with_name(aside.name + suffix))
    os.replace(tmp, paths.db)
    return {
        "backup": str(backup),
        "schema": version,
        "setAside": None if aside is None else str(aside),
        "closedSessions": closed,
    }


def systemctl(args: Sequence[str]) -> str:
    """`systemctl …` (with sudo -n for changes); the first line of its output."""
    query = args[0] in ("is-active", "is-enabled")
    command = ["systemctl", *args] if query else ["sudo", "-n", "systemctl", *args]
    done = subprocess.run(command, capture_output=True, text=True)
    if not query and done.returncode != 0:
        raise ReleaseError(f"{' '.join(command)}: {done.stderr.strip() or done.returncode}")
    return (done.stdout.strip().splitlines() or [""])[0]


# ── commands ───────────────────────────────────────────────────────────────────────────────


def last_record(paths: Paths) -> dict[str, Any] | None:
    if not paths.history.is_file():
        return None
    lines = [line for line in paths.history.read_text().splitlines() if line.strip()]
    return dict(json.loads(lines[-1])) if lines else None


def record(paths: Paths, entry: dict[str, Any], now: datetime) -> dict[str, Any]:
    paths.history.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": _utc(now), **entry}
    with paths.history.open("a") as out:
        out.write(json.dumps(line, ensure_ascii=False) + "\n")
    return {"result": "ok", "record": line}


def status(paths: Paths, sysctl: Systemctl = systemctl) -> dict[str, Any]:
    head = commit_of(paths.root, "HEAD")
    branch = git(paths.root, "branch", "--show-current") or None
    return {
        "result": "ok",
        "head": head,
        "branch": branch,
        "schema": {"stored": stored_schema(paths.db), "code": code_schema(paths.root, head)},
        "release": live_release(paths),
        "service": {
            "active": sysctl(["is-active", SERVICE]),
            "enabled": sysctl(["is-enabled", SERVICE]),
        },
        "last": last_record(paths),
    }


def default_target(paths: Paths, head: str) -> str:
    """The commit before the last deploy, when HEAD is still what that deploy left."""
    last = last_record(paths)
    if last is None or last.get("kind") != "deploy" or last.get("to") != head:
        raise ReleaseError(
            "no deploy record ends at the server's HEAD (rolled back already, or deployed before"
            " records existed): give the commit, ./deploy/deploy.sh rollback <commit>"
        )
    return str(last["from"])


def rollback_plan(
    paths: Paths, commit: str | None, sysctl: Systemctl = systemctl
) -> dict[str, Any]:
    head = commit_of(paths.root, "HEAD")
    target = commit_of(paths.root, commit) if commit else default_target(paths, head)
    if target == head:
        raise ReleaseError(f"the server is at {head[:12]} already")
    if git(paths.root, "status", "--porcelain", "--untracked-files=no"):
        raise ReleaseError("the server's working tree has changes: resolve them by hand first")
    code = code_schema(paths.root, target)
    stored = stored_schema(paths.db)
    say = [f"server at {head[:12]}, back to {target[:12]}"]
    restore: Path | None = None
    if stored is not None:
        if code is None:
            raise ReleaseError(f"{target[:12]} has no autotrade/ but the server has its database")
        if stored < code:
            raise ReleaseError(
                f"the database (schema {stored}) is older than that code ({code}): deploy instead"
            )
        if stored > code:
            restore = backup_for(paths, code)
            if restore is None:
                raise ReleaseError(f"no predeploy backup at schema {code}: restore by hand")
            say.append(
                f"autotrade DB: schema {stored} -> {code}: restore {restore.name}; everything"
                " written since it (runs, orders, fills, snapshots, events, AI calls, logins,"
                " PIN and lockout changes) leaves the live DB, which is kept aside, and every"
                " session is closed (log in again, with the PIN of that time)"
            )
        else:
            say.append(f"autotrade DB: schema {stored} fits that code, it stays as it is")
    release = find_release(paths, target) if code is not None else None
    if code is not None:
        say.append(f"web: release {release}" if release else f"web: build from {target[:12]}")
    old_app = git(
        paths.root, "diff", "--name-only", target, head, "--", "src", "deploy/dashboard.service"
    )
    say.append(
        "old app: src/ differs, dashboard.service will be restarted"
        if old_app
        else "old app: unchanged, dashboard.service keeps running"
    )
    active = sysctl(["is-active", SERVICE])
    say.append(
        f"autotrade.service: {active}"
        + (", stopped and started again" if active == "active" else "")
    )
    return {
        "result": "ok",
        "head": head,
        "target": target,
        "schema": {"stored": stored, "code": code},
        "restore": None if restore is None else str(restore),
        "release": release,
        "autotrade": code is not None,
        "dashboardChanged": bool(old_app),
        "serviceActive": active == "active",
        "say": say,
    }


def rollback_apply(
    paths: Paths,
    commit: str,
    restore: str | None,
    release: str | None,
    now: datetime,
    sysctl: Systemctl = systemctl,
    jobs_wait_s: float = JOBS_LOCK_WAIT_S,
    ai_wait_s: float = AI_LOCK_WAIT_S,
) -> dict[str, Any]:
    target = commit_of(paths.root, commit)
    if git(paths.root, "status", "--porcelain", "--untracked-files=no"):
        raise ReleaseError("the server's working tree has changes: resolve them by hand first")
    if release is not None and _read_meta(paths, release) is None:
        raise ReleaseError(f"no complete release {release}")
    backup = None if restore is None else Path(restore)
    if backup is not None and not backup.is_file():
        raise ReleaseError(f"no backup {restore}")
    with held(paths.lock("jobs"), jobs_wait_s), held(paths.lock("ai"), ai_wait_s):
        was_active = sysctl(["is-active", SERVICE]) == "active"
        if was_active:
            sysctl(["stop", SERVICE])  # fails before anything changed
        try:
            git(paths.root, "checkout", "-q", "--detach", target)
        except ReleaseError as exc:
            if was_active:
                sysctl(["start", SERVICE])
            raise ReleaseError(f"{exc} (nothing changed; autotrade.service started again)") from exc
        try:
            restored = None if backup is None else restore_db(paths, backup, now)
        except (OSError, sqlite3.Error, ReleaseError) as exc:
            raise ReleaseError(
                f"the code is at {target[:12]} but the database was NOT restored ({exc});"
                " autotrade.service stays stopped: fix it and run the rollback again"
            ) from exc
        try:
            switched = None if release is None else web_switch(paths, release, now)
        except (OSError, ReleaseError) as exc:
            raise ReleaseError(
                f"code and database are rolled back but web/dist was NOT switched ({exc});"
                f" autotrade.service stays stopped: run web-switch {release} and start it"
            ) from exc
    return {
        "result": "ok",
        "commit": target,
        "wasActive": was_active,
        "restored": restored,
        "switched": switched,
    }


def http_status(path: str, method: str = "GET", origin: str | None = None) -> int:
    """The status of one request to the local autotrade (0 when nothing answers)."""
    request = urllib.request.Request(HEALTH_BASE + path, method=method)
    if origin is not None:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except OSError:
        return 0


def health(
    fetch: Fetch = http_status,
    tries: int = 10,
    pause_s: float = 2.0,
    origin_optional: bool = False,
) -> dict[str, Any]:
    """After a restart: /api/healthz and / answer 200 (healthz is 503 unless the schema fits),
    a same-site POST passes and a sibling site's is refused (the origin rule).

    origin_optional (rollbacks): the code rolled back to may predate the origin rule (1587962),
    where both POSTs pass (204, 204); that is reported as originRule 'absent', not a failure.
    Anything else still fails."""

    def code(path: str, method: str = "GET", origin: str | None = None) -> int:
        return fetch(path, method, origin)

    last: dict[str, int] = {}
    for attempt in range(tries):
        last = {"healthz": code("/api/healthz"), "page": code("/")}
        if last == {"healthz": 200, "page": 200}:
            break
        if attempt + 1 < tries:
            time.sleep(pause_s)
    else:
        raise ReleaseError(f"health check failed: {last}")
    last["sameSite"] = code("/api/auth/logout", "POST", HEALTH_BASE)
    last["sibling"] = code("/api/auth/logout", "POST", "https://portfolio.jsyoo.dev")
    pair = (last["sameSite"], last["sibling"])
    if pair == (204, 403):
        return {"result": "ok", **last}
    if origin_optional and pair == (204, 204):
        return {"result": "ok", "originRule": "absent", **last}
    raise ReleaseError(f"the origin rule misbehaves: {last}")


def main(argv: Sequence[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for name in ("code-schema", "web-build", "web-find"):
        sub.add_parser(name).add_argument("commit")
    sub.add_parser("web-switch").add_argument("release")
    sub.add_parser("rollback-plan").add_argument("commit", nargs="?")
    apply = sub.add_parser("rollback-apply")
    apply.add_argument("commit")
    apply.add_argument("--restore")
    apply.add_argument("--release")
    sub.add_parser("record").add_argument("entry", help="a JSON object")
    sub.add_parser("health").add_argument("--origin-optional", action="store_true")
    args = parser.parse_args(argv)
    paths = Paths(root or Path.cwd())
    now = datetime.now(timezone.utc)
    try:
        if args.command == "status":
            out = status(paths)
        elif args.command == "code-schema":
            out = {"result": "ok", "schema": code_schema(paths.root, args.commit)}
        elif args.command == "web-build":
            out = web_build(paths, args.commit, now)
        elif args.command == "web-find":
            sha = commit_of(paths.root, args.commit)
            out = {"result": "ok", "release": find_release(paths, sha)}
        elif args.command == "web-switch":
            out = web_switch(paths, args.release, now)
        elif args.command == "rollback-plan":
            out = rollback_plan(paths, args.commit)
        elif args.command == "rollback-apply":
            out = rollback_apply(paths, args.commit, args.restore, args.release, now)
        elif args.command == "record":
            out = record(paths, dict(json.loads(args.entry)), now)
        else:
            out = health(origin_optional=args.origin_optional)
    except (ReleaseError, OSError, sqlite3.Error, ValueError) as exc:
        sys.stdout.write(json.dumps({"result": "failed", "error": str(exc)}) + "\n")
        return 1
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
