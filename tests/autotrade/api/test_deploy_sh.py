"""deploy/deploy.sh against a simulated Oracle under pytest's temporary folder: an origin
repository, the laptop's clone (with this checkout's deploy.sh and release.py) and the server's
clone, with fake ssh (runs the command locally with HOME = the fake server's home), sudo,
systemctl, npm and curl on PATH. The engine's commands (`autotrade.jobs migrate --predeploy`,
`backup`) are played by the fake server Python. Nothing leaves the temporary folder."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from autotrade.config import REPO_ROOT

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "LC_ALL": "C",
}

FAKE_SSH = """#!/bin/bash
# ssh HOST COMMAND...: run COMMAND here, as if on the server (HOME = the fake server's home).
shift
cd "$SIM_HOME" && HOME="$SIM_HOME" exec bash -c "$*"
"""
FAKE_SUDO = """#!/bin/bash
[ "$1" = "-n" ] && shift
exec "$@"
"""
FAKE_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$SIM_STATE/calls"
state="$SIM_STATE/unit-${2%.service}"
case "$1" in
  is-active)
    cat "$state" 2>/dev/null || echo inactive
    [ "$(cat "$state" 2>/dev/null)" = active ] ;;
  is-enabled) echo enabled ;;
  cat) [ -e "$SIM_STATE/installed" ] ;;
  restart|start) echo active > "$state" ;;
  stop) echo inactive > "$state" ;;
esac
"""
FAKE_NPM = """#!/bin/bash
echo "npm $*" >> "$SIM_STATE/calls"
[ -e "$SIM_STATE/npm-fails" ] && exit 1
if [ "$1 $2" = "run build" ]; then
  n=$(( $(cat "$SIM_STATE/builds" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$SIM_STATE/builds"
  mkdir -p dist/assets
  echo "<title>build $n</title>" > dist/index.html
  echo "build $n" > "dist/assets/index-$n.js"
fi
"""
FAKE_CURL = """#!/bin/bash
exit 0
"""
# The server's .venv/bin/python: the engine's commands are played here, the rest is real Python.
FAKE_PYTHON = """#!/bin/bash
if [ "$1" = "-m" ]; then
  echo "python $*" >> "$SIM_STATE/calls"
  case "$2 $3" in
    "src.core.backup "*) exit 0 ;;
    "autotrade.jobs backup") exec "$REAL_PYTHON" "$SIM_TOOLS/engine.py" backup ;;
    "autotrade.jobs migrate") exec "$REAL_PYTHON" "$SIM_TOOLS/engine.py" migrate "${@:4}" ;;
  esac
  exit 2
fi
if [ "$1 $2" = "- health" ]; then
  cat > /dev/null
  echo '{"result": "ok", "healthz": 200, "page": 200, "sameSite": 204, "sibling": 403}'
  exit 0
fi
exec "$REAL_PYTHON" "$@"
"""
ENGINE = """import datetime, json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())  # the server's checkout, as `python -m` would have it
from autotrade.db.migrations import MIGRATIONS
db = Path("data/autotrade.db")
def backup():
    if not db.exists():
        print(json.dumps({"job": "backup", "result": "no-database"}))
        return
    folder = Path("data/backup/autotrade")
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S%f")[:15]
    target = folder / f"autotrade-predeploy-{stamp}.db"
    conn = sqlite3.connect(db)
    conn.execute("VACUUM INTO ?", (str(target),))
    conn.close()
    print(json.dumps({"job": "backup", "result": "ok", "path": str(target)}))
if sys.argv[1] == "backup":
    backup()
elif os.path.exists(os.path.join(os.environ["SIM_STATE"], "migrate-busy")):
    print(json.dumps({"job": "migrate", "result": "busy", "lock": "ai", "at": "now"}))
    sys.exit(3)
else:
    if "--predeploy" in sys.argv:  # migrate --predeploy: the copy first, as the real command
        backup()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT, revoked_at TEXT,"
                 " revoked_why TEXT)")
    for version, _, _ in MIGRATIONS:
        conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?)", (version,))
    conn.commit()
    conn.close()
    print(json.dumps({"job": "migrate", "result": "ok", "schema": MIGRATIONS[-1][0]}))
"""


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV}
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def migrations(n: int) -> str:
    rows = "\n".join(f'    ({v}, "m{v}", ""),' for v in range(1, n + 1))
    return f"MIGRATIONS = (\n{rows}\n)\n"


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@dataclass
class Sim:
    laptop: Path
    server: Path
    state: Path
    env: dict[str, str]

    def deploy(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "deploy/deploy.sh", *args],
            cwd=self.laptop,
            env=self.env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def commit(self, files: dict[str, str], message: str) -> str:
        for name, text in files.items():
            (self.laptop / name).parent.mkdir(parents=True, exist_ok=True)
            (self.laptop / name).write_text(text)
        git(self.laptop, "add", "-A")
        git(self.laptop, "commit", "-q", "-m", message)
        return git(self.laptop, "rev-parse", "HEAD")

    def head(self) -> str:
        return git(self.server, "rev-parse", "HEAD")

    def schema(self) -> int:
        conn = sqlite3.connect(self.server / "data" / "autotrade.db")
        try:
            return int(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0])
        finally:
            conn.close()

    def calls(self) -> list[str]:
        path = self.state / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def live(self) -> str:
        return os.readlink(self.server / "web" / "dist")


@pytest.fixture
def sim(tmp_path: Path) -> Sim:
    origin, laptop = tmp_path / "origin.git", tmp_path / "laptop"
    home, state, tools, bin_ = (tmp_path / n for n in ("home", "state", "tools", "bin"))
    for folder in (home, state, tools, bin_):
        folder.mkdir()
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(laptop))
    git(laptop, "remote", "add", "origin", str(origin))
    files = {
        ".gitignore": ".venv/\ndata/\nweb/releases/\nweb/dist\n__pycache__/\n",
        "deploy/deploy.sh": (REPO_ROOT / "deploy" / "deploy.sh").read_text(),
        "autotrade/__init__.py": "",
        "autotrade/api/__init__.py": "",
        "autotrade/api/release.py": (REPO_ROOT / "autotrade" / "api" / "release.py").read_text(),
        "autotrade/db/__init__.py": "",
        "autotrade/db/migrations.py": migrations(2),
        "web/package.json": "{}\n",
        "src/app.py": "print('old app')\n",
    }
    for name, text in files.items():
        (laptop / name).parent.mkdir(parents=True, exist_ok=True)
        (laptop / name).write_text(text)
    git(laptop, "add", "-A")
    git(laptop, "commit", "-q", "-m", "first")
    git(laptop, "push", "-q", "-u", "origin", "main")
    server = home / "portfolio-dashboard"
    git(tmp_path, "clone", "-q", str(origin), str(server))
    dot_origin, dot = tmp_path / "dotclaude.git", home / "dotclaude"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(dot_origin))
    git(tmp_path, "init", "-q", "-b", "main", str(dot))
    git(dot, "remote", "add", "origin", str(dot_origin))
    (dot / "x").write_text("x")
    git(dot, "add", "-A")
    git(dot, "commit", "-q", "-m", "x")
    git(dot, "push", "-q", "-u", "origin", "main")
    (server / ".venv" / "bin").mkdir(parents=True)
    executable(server / ".venv" / "bin" / "python", FAKE_PYTHON)
    for name, text in (
        ("ssh", FAKE_SSH),
        ("sudo", FAKE_SUDO),
        ("systemctl", FAKE_SYSTEMCTL),
        ("npm", FAKE_NPM),
        ("curl", FAKE_CURL),
    ):
        executable(bin_ / name, text)
    (bin_ / "python3").symlink_to(sys.executable)
    (tools / "engine.py").write_text(ENGINE)
    (state / "installed").touch()
    (state / "unit-autotrade").write_text("active\n")
    # The web/dist folder a deploy before releases left behind.
    (server / "web" / "dist" / "assets").mkdir(parents=True)
    (server / "web" / "dist" / "index.html").write_text("<title>old build</title>")
    (server / "web" / "dist" / "assets" / "index-old.js").write_text("old")
    env = {
        **os.environ,
        **GIT_ENV,
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "SIM_HOME": str(home),
        "SIM_STATE": str(state),
        "SIM_TOOLS": str(tools),
        "REAL_PYTHON": sys.executable,
        "PYTHONPATH": "",
    }
    return Sim(laptop, server, state, env)


def test_deploy_then_roll_back_then_deploy_again(sim: Sim) -> None:
    first = git(sim.laptop, "rev-parse", "HEAD")
    done = sim.deploy("autotrade")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sim.head() == first
    assert sim.schema() == 2
    assert sim.live().startswith("releases/")
    assert sim.live().endswith(first[:12])
    legacy = [p.name for p in (sim.server / "web" / "releases").iterdir() if "legacy" in p.name]
    assert legacy  # the old web/dist folder was kept as a release
    assert (sim.server / "web" / "dist" / "assets" / "index-old.js").exists()  # carried
    calls = sim.calls()
    order = [
        c
        for c in calls
        if c.startswith(("npm run build", "python -m autotrade", "systemctl restart"))
    ]
    assert order == [
        "npm run build",
        "python -m autotrade.jobs migrate --predeploy",
        "systemctl restart autotrade.service",
    ]
    assert "npm ci --ignore-scripts --no-audit --no-fund" in calls

    second = sim.commit({"autotrade/db/migrations.py": migrations(3)}, "a migration")
    done = sim.deploy("autotrade")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (sim.head(), sim.schema()) == (second, 3)
    backups = sorted((sim.server / "data" / "backup" / "autotrade").glob("autotrade-predeploy-*"))
    assert len(backups) == 1  # the first deploy had no database yet ('no-database')
    history = (sim.server / "data" / "deploy" / "history.jsonl").read_text().splitlines()
    assert [json.loads(line)["to"] for line in history] == [first, second]

    # Roll back: the database restore needs --yes (or typing 'restore').
    refused = sim.deploy("rollback")
    assert refused.returncode != 0
    assert "rollback cancelled (nothing changed)" in refused.stderr
    assert (sim.head(), sim.schema()) == (second, 3)
    done = sim.deploy("rollback", "--yes")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "[rollback] autotrade DB: schema 3 -> 2: restore" in done.stdout
    assert (sim.head(), sim.schema()) == (first, 2)
    assert git(sim.server, "branch", "--show-current") == ""  # detached
    assert sim.live().endswith(first[:12])
    assert "systemctl start autotrade.service" in sim.calls()
    assert "sessions closed" in done.stdout
    replaced = list((sim.server / "data" / "backup" / "autotrade").glob("autotrade-replaced-*.db"))
    assert len(replaced) == 1  # the live database was moved aside, not deleted
    again = sim.deploy("rollback", "--yes")
    assert again.returncode != 0
    assert "no deploy record ends at the server's HEAD" in again.stderr

    # The next deploy leaves the detached HEAD straight for the new commit.
    third = sim.commit({"autotrade/db/migrations.py": migrations(4)}, "the fix")
    done = sim.deploy("autotrade")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (sim.head(), sim.schema()) == (third, 4)
    assert git(sim.server, "branch", "--show-current") == "main"


def test_a_failed_build_changes_nothing(sim: Sim) -> None:
    assert sim.deploy("autotrade").returncode == 0
    before = (sim.head(), sim.live(), sim.schema())
    sim.commit({"autotrade/db/migrations.py": migrations(3)}, "a migration")
    (sim.state / "npm-fails").touch()
    done = sim.deploy("autotrade")
    assert done.returncode != 0
    assert "web build failed" in done.stderr
    assert "nothing changed on the server" in done.stderr
    assert (sim.head(), sim.live(), sim.schema()) == before


def test_a_busy_migrate_says_to_deploy_again(sim: Sim) -> None:
    """migrate waits for the tick's and the AI runner's locks; when one stays busy nothing is
    copied or migrated, the service is not restarted, and the message says what to do."""
    assert sim.deploy("autotrade").returncode == 0
    sim.commit({"autotrade/db/migrations.py": migrations(3)}, "a migration")
    (sim.state / "migrate-busy").touch()
    restarts = sim.calls().count("systemctl restart autotrade.service")
    done = sim.deploy("autotrade")
    assert done.returncode != 0
    assert "the ai lock stayed busy" in done.stderr
    assert "./deploy/deploy.sh autotrade" in done.stderr
    assert sim.schema() == 2  # nothing migrated
    assert sim.calls().count("systemctl restart autotrade.service") == restarts
    (sim.state / "migrate-busy").unlink()
    again = sim.deploy("autotrade")
    assert again.returncode == 0, again.stdout + again.stderr
    assert sim.schema() == 3


def test_a_pull_only_deploy_warns_about_a_pending_schema(sim: Sim) -> None:
    assert sim.deploy("autotrade").returncode == 0
    sim.commit(
        {"autotrade/db/migrations.py": migrations(3), "src/app.py": "print('changed')\n"}, "both"
    )
    done = sim.deploy()
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        "ticks refuse to run and quant answers 503 until ./deploy/deploy.sh autotrade"
        in done.stdout
    )
    assert "dashboard.service was not restarted" in done.stdout
    assert sim.schema() == 2  # nothing migrated
    assert not any(c.startswith("systemctl restart") for c in sim.calls()[-5:])


def test_an_uninstalled_unit_is_not_restarted(sim: Sim) -> None:
    (sim.state / "installed").unlink()
    done = sim.deploy("autotrade")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "autotrade.service is not installed" in done.stdout
    assert not any(c.startswith("systemctl restart") for c in sim.calls())


def test_unknown_service_names_stop_before_anything(sim: Sim) -> None:
    done = sim.deploy("autotrad")
    assert done.returncode != 0
    assert "unknown service 'autotrad'" in done.stderr
    assert sim.calls() == []


def test_the_old_app_deploys_and_rolls_back_as_before(sim: Sim) -> None:
    """qdd (deploy.sh dashboard): pull, the old app's backup, restart and its health check. A
    rollback restarts it only when its code (src/) differs between the two commits."""
    assert sim.deploy("autotrade").returncode == 0  # autotrade's database exists (schema 2)
    before = sim.head()
    changed = sim.commit({"src/app.py": "print('old app, fixed')\n"}, "old app change")
    done = sim.deploy("dashboard")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sim.head() == changed
    assert "systemctl restart dashboard.service" in sim.calls()
    assert "python -m src.core.backup --only portfolio quant news" in sim.calls()
    assert "health OK (http://127.0.0.1:8888/api/accounts" in done.stdout
    restarts = sim.calls().count("systemctl restart dashboard.service")
    done = sim.deploy("rollback", "--yes")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "old app: src/ differs, dashboard.service will be restarted" in done.stdout
    assert "autotrade DB: schema 2 fits that code, it stays as it is" in done.stdout
    assert sim.head() == before
    assert sim.calls().count("systemctl restart dashboard.service") == restarts + 1
    assert sim.schema() == 2  # nothing restored


def test_a_rollback_keeps_the_live_ledger_unless_told(sim: Sim) -> None:
    """Rolling back past the schema that brought the live ledger restores a copy without it, on
    code with no Toss link: the rollback refuses while the database has it (--yes does not
    cover that), and --drop-live sets it aside with the replaced database and says so."""
    first = git(sim.laptop, "rev-parse", "HEAD")
    assert sim.deploy("autotrade").returncode == 0
    second = sim.commit({"autotrade/db/migrations.py": migrations(3)}, "a migration")
    assert sim.deploy("autotrade").returncode == 0
    db = sim.server / "data" / "autotrade.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE events (ledger_id TEXT, kind TEXT)")
        conn.execute("INSERT INTO events VALUES ('live', 'start')")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO settings VALUES ('mode', 'live')")
        conn.execute("CREATE TABLE broker_orders (state TEXT, cancel_state TEXT)")
        conn.execute("INSERT INTO broker_orders VALUES ('sent', NULL)")
        conn.commit()
    finally:
        conn.close()

    refused = sim.deploy("rollback", "--yes")
    assert refused.returncode != 0
    assert "cannot roll back: the live DB has the live ledger" in refused.stderr
    assert "Turn live off on the mode screen" in refused.stderr
    assert "then roll back with --drop-live" in refused.stderr
    assert "(nothing changed)" in refused.stderr
    assert (sim.head(), sim.schema()) == (second, 3)
    cancelled = sim.deploy("rollback", "--drop-live", stdin="no\n")
    assert cancelled.returncode != 0
    assert "rollback cancelled (nothing changed)" in cancelled.stderr
    assert (sim.head(), sim.schema()) == (second, 3)

    done = sim.deploy("rollback", "--yes", "--drop-live")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        "[rollback] live ledger: live is on (mode 'live'); 1 order(s) open at Toss or waiting for"
        " a cancel; the live ledger has started. --drop-live:" in done.stdout
    )
    assert "[rollback] that code has no Toss link" in done.stdout
    assert "[rollback] the live ledger (실전) left the live DB: it is in" in done.stdout
    assert "orders may still be open at Toss: cancel them in the Toss app" in done.stdout
    assert (sim.head(), sim.schema()) == (first, 2)
    (replaced,) = (sim.server / "data" / "backup" / "autotrade").glob("autotrade-replaced-*.db")
    conn = sqlite3.connect(replaced)
    try:
        assert conn.execute("SELECT value FROM settings WHERE key = 'mode'").fetchone() == ("live",)
    finally:
        conn.close()
