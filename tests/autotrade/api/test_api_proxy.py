"""Behind nginx: the lockout address is the same whether or not uvicorn rewrites the client.

uvicorn 0.46 turns its proxy-header middleware on by default (--proxy-headers is the default;
--forwarded-allow-ips defaults to 127.0.0.1), so deploy/autotrade.service dropping the flags does
not turn it off. With it on, uvicorn replaces the peer 127.0.0.1 with the rightmost
X-Forwarded-For hop that is not 127.0.0.1; with it off, autotrade/api/deps.client_ip() reads that
same hop itself. Either way the address is the one nginx appended.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autotrade.api.settings import ApiSettings
from autotrade.db import auth_repo

from ..helpers import kst
from .support import PIN, owner_pin

proxy_headers = pytest.importorskip("uvicorn.middleware.proxy_headers")

NGINX = ("127.0.0.1", 40000)


def attempts(client: TestClient, forwarded: str, pin: str = "000000") -> int:
    r = client.post("/api/auth/pin", json={"pin": pin}, headers={"x-forwarded-for": forwarded})
    return int(r.status_code)


@pytest.mark.parametrize("uvicorn_rewrites", [True, False])
def test_the_lockout_address_is_the_hop_nginx_added(
    app: FastAPI,
    db: sqlite3.Connection,
    settings: ApiSettings,
    uvicorn_rewrites: bool,
) -> None:
    owner_pin(db, settings)
    served = (
        proxy_headers.ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
        if uvicorn_rewrites
        else app
    )
    with TestClient(served, base_url="https://testserver", client=NGINX) as c:
        # The client forged a first hop; nginx appended the real address after it.
        for _ in range(5):
            attempts(c, "9.9.9.9, 1.2.3.4")
        locked = c.post("/api/auth/pin", json={"pin": PIN}, headers={"x-forwarded-for": "1.2.3.4"})
        assert locked.json()["error"] == "locked"
        # The forged address was never the key: a real 9.9.9.9 can still log in.
        assert attempts(c, "9.9.9.9", PIN) == 204
        assert attempts(c, "5.6.7.8", PIN) == 204
    ips = {s.ip for s in auth_repo.open_sessions(db, kst("2026-07-01 16:10"))}
    assert ips == {"9.9.9.9", "5.6.7.8"}
