"""Settings of the web API (paths, the session cookie, lockout limits, KDF cost).

Development mode (AUTOTRADE_DEV=1) counts only for a database outside data/ — a dev-seed world
under build/ or web/build/. Set by mistake on the server (data/autotrade.db) it changes nothing:
the clock keeps running and the cookie stays Secure (CONTRACT.md 세션과 보안).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from autotrade.config import REPO_ROOT, Config

# Production: Secure, Path=/, no Domain, so the browser enforces the __Host- prefix: no other
# *.jsyoo.dev site can set or shadow it (SameSite=Strict counts siblings as the same site).
SECURE_COOKIE_NAME = "__Host-qsess"
# Development over plain http (a __Host- cookie must be Secure): the old name, not Secure.
DEV_COOKIE_NAME = "qsess"


@dataclass(frozen=True)
class ApiSettings:
    secret_path: Path  # data/autotrade.secret (0600): signs cookies, peppers the PIN hash
    dist_dir: Path  # web/dist, the built web app (a symlink to the live release on the server)
    session_ttl: timedelta = timedelta(days=30)
    touch_interval: timedelta = timedelta(minutes=10)  # how often 'last seen' is written
    # PIN lockout (autotrade/api/auth.py explains the numbers). The address is the IPv4 address
    # or the IPv6 /64 the request came from.
    ip_max_failures: int = 5  # consecutive wrong PINs from one address ...
    ip_lock: timedelta = timedelta(minutes=30)  # ... lock that address this long
    ipv6_prefix: int = 64
    global_max_failures: int = 20  # wrong PINs from everywhere within ...
    global_window: timedelta = timedelta(hours=1)  # ... this window lock new logins
    alert_failures: int = 10  # wrong PINs within daily_window raise 'PIN 실패 급증'
    hold_failures: int = 30  # ... and close new logins until `python -m autotrade.jobs unlock`
    daily_window: timedelta = timedelta(hours=24)
    session_max_failures: int = 5  # wrong current PINs on one session close that session
    scrypt_n: int = 2**15  # PIN hash cost (tests lower it)
    cookie_secure: bool = True

    @property
    def cookie_name(self) -> str:
        return SECURE_COOKIE_NAME if self.cookie_secure else DEV_COOKIE_NAME


def dev_database(db_path: Path) -> bool:
    """A database outside data/: the only kind development mode may serve."""
    try:
        db_path.resolve().relative_to((REPO_ROOT / "data").resolve())
    except ValueError:
        return True
    return False


def dev_mode(env: Mapping[str, str], db_path: Path) -> bool:
    return env.get("AUTOTRADE_DEV") == "1" and dev_database(db_path)


def default_settings(cfg: Config, *, dev: bool = False) -> ApiSettings:
    return ApiSettings(
        secret_path=cfg.db_path.parent / "autotrade.secret",
        dist_dir=REPO_ROOT / "web" / "dist",
        cookie_secure=not dev,
    )
