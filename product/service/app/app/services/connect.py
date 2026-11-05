"""설정 › 연결(쓰기 일 · ARCHITECTURE 2-1 `services/connect.py`): 토스 API 키 저장과 연결 확인(조회만), DART 키 저장.

연결 확인은 액세스 토큰 받기 → 계좌 → 삼성전자 현재가 순서로 GET만 한다.
결과에는 계좌 끝 4자리와 현재가만 담고, 키 · 토큰은 담지 않는다.

- 증권사는 `Broker` 포트로 받아요: 토스 클라이언트를 만드는 함수(`client_for`) · 토스 오류를 연결 상태 종류로 바꾸는
  함수(`link_state`) · 기록 시각(`now`)은 조립(`app.py`)이 넣어 줘요(쓰기 일은 어댑터를 몰라요 · 기본은 가짜 전송).
- 기록 시각은 기준선 시계 고정 자리(`app/connect.py` `_now` · Q-N24)라 조립이 그 함수를 넘겨요.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from typing import Any

from ..copy import texts as T
from ..ports import Broker, BrokerError, BrokerRejected
from ..security.vault import Vault, VaultError
from ..store.db import DB

TOSS_ID = "toss.client_id"
TOSS_SECRET = "toss.client_secret"
TOSS_ACCOUNT = "toss.account_no"
DART_KEY = "dart.api_key"
CHECK_META = "toss.last_check"
PROBE_SYMBOL = "005930"
PROBE_NAME = "삼성전자"

STEP_NAMES = {"token": T.step_token, "account": "계좌 찾기", "price": T.step_price}
STEP_ORDER = ["token", "account", "price"]

# kind -> (제목, 원인, 다음)
FAILURES: dict[str, tuple[str, str, str]] = {
    "auth": (
        "API 키가 맞지 않아요",
        "Client ID나 Client Secret이 토스에 등록된 값과 달라요",
        "토스증권 PC(WTS) › Open API에서 키를 다시 복사해 API 키 변경으로 입력해요",
    ),
    "ip": (
        "허용 IP에 이 컴퓨터가 없어요",
        "토스 허용 IP 목록에 이 컴퓨터의 공인 IP가 없어요 · 와이파이가 바뀌면 공인 IP도 바뀌어요",
        "WTS › Open API › 허용 IP에 이 컴퓨터의 공인 IP를 등록하고 다시 확인해요",
    ),
    "unreachable": (
        "토스가 응답하지 않아요",
        "토스가 정해진 시간 안에 답하지 않았어요 · 인터넷 연결이나 토스 쪽 문제예요",
        "인터넷 연결을 확인하고 잠시 뒤 다시 확인해요",
    ),
    "account": (
        "맞는 계좌를 찾지 못했어요",
        "입력한 계좌번호와 같은 계좌가 토스에 없거나, 계좌가 여러 개예요",
        "계좌번호 숫자가 맞는지 보고, 계좌가 여러 개면 계좌번호를 입력해요",
    ),
    "maintenance": (
        "토스가 점검 중이에요",
        "토스증권 Open API가 점검 중이에요",
        "점검이 끝난 뒤 다시 확인해요",
    ),
    "shape": (
        "토스 응답 이상이에요",
        "토스가 보낸 응답의 형식이 맞지 않아요",
        T.check_again_later,
    ),
    "error": (
        "연결을 확인하지 못했어요",
        "토스가 알 수 없는 답을 보냈어요",
        T.check_again_later,
    ),
}


def _step_state(key: str, failed: str) -> str:
    i, f = STEP_ORDER.index(key), STEP_ORDER.index(failed)
    return "done" if i < f else ("failed" if i == f else "waiting")


def won(value: float | int) -> str:
    return f"{round(value):,}원"


# 증권사 클라이언트 만들기: (Client ID, Client Secret, 계좌번호, 전송) → Broker(조립이 토스 어댑터로 넣어 줘요)
ClientFor = Callable[[str, str, "str | None", Any], Broker]


class Connections:
    def __init__(self, db: DB, vault: Vault, transport_factory: Callable[[], Any], *, client_for: ClientFor,
                 link_state: Callable[[BaseException], str], now: Callable[[], str]) -> None:
        self.db = db
        self.vault = vault
        vault.on_key_cleared.append(self.drop)  # 데이터 키가 사라지면 연결 객체 · 토큰도 버린다
        self.transport_factory = transport_factory
        self.client_for = client_for
        self.link_state = link_state  # 증권사 오류 → auth · ip · unreachable · account · maintenance · shape · error
        self.now = now
        self._client: Broker | None = None
        self._client_for: str | None = None
        self._lock = threading.Lock()

    # ── 저장 · 지우기 ──────────────────────────────────────────────────────

    def save_toss(self, client_id: str, client_secret: str, account_no: str | None) -> None:
        cid, sec = (client_id or "").strip(), (client_secret or "").strip()
        acc = "".join(ch for ch in (account_no or "") if ch.isdigit())
        if not cid:
            raise VaultError("Client ID를 입력해 주세요")
        if not sec:
            raise VaultError("Client Secret을 입력해 주세요")
        if len(cid) > 512 or len(sec) > 512:
            raise VaultError("API 키가 너무 길어요 · 복사한 글을 다시 확인해 주세요")
        if account_no and (len(acc) < 8 or len(acc) > 20):
            raise VaultError("계좌번호는 숫자 8~20자리로 입력해 주세요")
        self.vault.put_secret(TOSS_ID, cid)
        self.vault.put_secret(TOSS_SECRET, sec)
        if acc:
            self.vault.put_secret(TOSS_ACCOUNT, acc)
        else:
            self.vault.delete_secret(TOSS_ACCOUNT)
        self.db.set_meta(CHECK_META, None)
        self._drop_client()

    def delete_toss(self) -> None:
        for name in (TOSS_ID, TOSS_SECRET, TOSS_ACCOUNT):
            self.vault.delete_secret(name)
        self.db.set_meta(CHECK_META, None)
        self._drop_client()

    def save_dart(self, key: str) -> None:
        k = (key or "").strip()
        if not k:
            raise VaultError("DART API 키를 입력해 주세요")
        if len(k) > 256:
            raise VaultError("API 키가 너무 길어요")
        self.vault.put_secret(DART_KEY, k)

    def delete_dart(self) -> None:
        self.vault.delete_secret(DART_KEY)

    # ── 보기 ────────────────────────────────────────────────────────────────

    def last_check(self) -> dict[str, Any] | None:
        raw = self.db.get_meta(CHECK_META)
        return None if raw is None else json.loads(raw)

    def view(self) -> dict[str, Any]:
        saved = self.vault.has_secret(TOSS_ID) and self.vault.has_secret(TOSS_SECRET)
        unlocked = self.vault.unlocked
        return {
            "unlocked": unlocked,
            "toss": {
                "saved": saved,
                "client_id_tail": self.vault.tail(TOSS_ID) if saved else None,
                "secret_tail": self.vault.tail(TOSS_SECRET) if saved else None,
                "account_tail": self.vault.tail(TOSS_ACCOUNT),
                "last_check": self.last_check() if saved else None,
            },
            "dart": {"saved": self.vault.has_secret(DART_KEY), "tail": self.vault.tail(DART_KEY)},
        }

    # ── 연결 확인 ───────────────────────────────────────────────────────────

    def drop(self) -> None:
        """연결 객체를 버리고 그 안의 액세스 토큰 · 계좌를 지운다(잠그기 · 키 삭제 · 키 변경)."""
        with self._lock:
            c: Any = self._client  # 토스 클라이언트 안의 토큰 · 계좌(어댑터 속성)를 지워요
            if c is not None:
                c._token = None
                c._expires = 0.0
                c._account = None
            self._client = None
            self._client_for = None

    _drop_client = drop

    def client(self) -> Broker | None:
        """저장된 키로 만든 클라이언트(키가 같으면 다시 쓴다: 토큰을 덜 받는다)."""
        if not self.vault.can_read:
            self.drop()  # 잠긴 뒤에는 토큰도 남기지 않는다(키 파일이 있으면 실행기는 계속 열 수 있어요)
            return None
        cid = self.vault.get_secret(TOSS_ID)
        sec = self.vault.get_secret(TOSS_SECRET)
        if not cid or not sec:
            return None
        acc = self.vault.get_secret(TOSS_ACCOUNT)
        fp = hashlib.sha256(f"{cid}\0{sec}\0{acc or ''}".encode()).hexdigest()
        with self._lock:
            if self._client is None or self._client_for != fp:
                self._client = self.client_for(cid, sec, acc, self.transport_factory())
                self._client_for = fp
            return self._client

    def check(self) -> dict[str, Any]:
        client = self.client()
        if client is None:
            if not self.vault.can_read:
                raise VaultError(T.locked_retry, 423)
            raise VaultError("API 키를 먼저 저장해 주세요")
        step = "token"
        kind = code = ""
        try:
            client.token(force=True)
            step = "account"
            _, tail = client.account(force=True)
            step = "price"
            quotes = client.prices([PROBE_SYMBOL])
            if PROBE_SYMBOL not in quotes:
                # 옮기기 전에는 토스 오류(HTTP 200 · 'no-price')를 던져 `link_state`가 'error'로 바꿨어요(같은 결과)
                kind, code = "error", "no-price"
            else:
                price = float(quotes[PROBE_SYMBOL].price)
        except BrokerError as exc:
            kind = self.link_state(exc)
            code = exc.code if isinstance(exc, BrokerRejected) else "no-answer"
        if kind:
            title, cause, next_step = FAILURES[kind]
            result: dict[str, Any] = {
                "ok": False,
                "kind": kind,
                "step": STEP_NAMES[step],
                "step_key": step,
                "steps": [
                    {"key": k, "name": STEP_NAMES[k], "state": _step_state(k, step)} for k in STEP_ORDER
                ],
                "title": title,
                "cause": cause,
                "next": next_step,
                "code": code,
                "line": f"{title} · {STEP_NAMES[step]}에서 중단",
                "at": self.now(),
            }
            self.db.set_meta(CHECK_META, json.dumps(result, ensure_ascii=False))
            return result
        result = {
            "ok": True,
            "steps": [{"key": k, "name": STEP_NAMES[k], "state": "done"} for k in STEP_ORDER],
            "account_tail": tail,
            "price": price,
            "line": f"연결됐어요 · 계좌 끝 {tail} · {PROBE_NAME} {won(price)}",
            "at": self.now(),
        }
        self.db.set_meta(CHECK_META, json.dumps(result, ensure_ascii=False))
        return result

    def live_prices(self, symbols: list[str]) -> dict[str, float] | None:
        """모의투자 평가용 토스 현재가. 마지막 연결 확인이 성공했고 풀려 있을 때만 부른다."""
        last = self.last_check()
        if not symbols or not last or not last.get("ok"):
            return None
        client = self.client()
        if client is None:
            return None
        try:
            quotes = client.prices(symbols)
        except BrokerError:
            return None
        return {s: float(q.price) for s, q in quotes.items()}
