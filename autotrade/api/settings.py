"""Settings of the web API (paths, session lifetime, lockout limits, KDF cost)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from autotrade.config import REPO_ROOT, Config

COOKIE_NAME = "qsess"


@dataclass(frozen=True)
class ApiSettings:
    secret_path: Path  # data/autotrade.secret (0600): signs cookies, peppers the PIN hash
    dist_dir: Path  # web/dist, the built web app
    session_ttl: timedelta = timedelta(days=30)
    touch_interval: timedelta = timedelta(minutes=10)  # how often 'last seen' is written
    ip_max_failures: int = 5  # consecutive wrong PINs from one address ...
    ip_lock: timedelta = timedelta(minutes=30)  # ... lock that address this long
    global_max_failures: int = 20  # wrong PINs from everywhere within ...
    global_window: timedelta = timedelta(hours=1)  # ... this window lock new logins
    scrypt_n: int = 2**15  # PIN hash cost (tests lower it)
    cookie_secure: bool = True


def default_settings(cfg: Config) -> ApiSettings:
    return ApiSettings(
        secret_path=cfg.db_path.parent / "autotrade.secret",
        dist_dir=REPO_ROOT / "web" / "dist",
    )
