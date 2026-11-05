"""계정 · 비밀번호 · 복구 코드 · 세션 · 비밀 값 금고.

- 무작위 데이터 키(32바이트) 하나가 비밀 값들을 AES-GCM으로 잠근다.
- 데이터 키는 두 번 감싸 둔다: 비밀번호에서 scrypt로 만든 키로 한 번, 복구 코드에서 만든 키로 한 번.
  비밀번호 확인은 따로 해시를 두지 않고, 감싼 데이터 키가 풀리는지로 한다.
- 풀린 데이터 키는 로그인 세션이 하나라도 살아 있는 동안만 메모리에 있다. 앱을 다시 켜면 화면은 잠긴다.
- 세 번째 감싸기: 컴퓨터 키 파일(T-50 · SPEC 10). 키 파일은 레포와 데이터 폴더 밖 고정 경로에 권한 600으로 두고,
  실행기(자동 확인 · 주문)는 그 키로 데이터 키를 풀어 재부팅 뒤에도 로그인 없이 돈다. 화면 입장은 늘 비밀번호.
- 돈이 움직이는 일(SPEC 7-4 목록)은 비밀번호를 다시 받아 짧은 1회용 토큰을 내준다. 틀린 횟수는 로그인과 같이 센다.
- 비밀 값은 어떤 반환 값 · 예외 글 · 로그에도 넣지 않는다. 바깥에는 끝 4자리만 나간다.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .store.db import DB

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SESSION_S = 12 * 3600
MAX_FAILS = 5
LOCK_S = 5 * 60
MIN_PASSWORD = 8
MAX_PASSWORD = 128
# Crockford base32: 0~9와 I L O U를 뺀 영문. 16자 = 80비트.
RC_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RC_LEN = 16

AAD_PW = b"wrap:password"
AAD_RC = b"wrap:recovery"
AAD_KF = b"wrap:keyfile"

# 컴퓨터 키 파일의 고정 경로(레포 · 데이터 폴더 밖). 시험은 conftest가 시험 임시 폴더로 바꿔요.
DEFAULT_KEYFILE_PATH = Path.home() / ".config" / "quant-service" / "keyfile"
KEYFILE_PATH = DEFAULT_KEYFILE_PATH
CONFIRM_S = 120  # 1회용 토큰이 사는 시간

# SPEC 7-4 '비밀번호를 받는 일' 전부. 값은 확인 창(V2-33) 제목.
MONEY_ACTIONS: dict[str, str] = {
    "live_start": "실전 운용 시작",
    "live_amount": "운용 금액 변경",
    "live_limits": "한도 변경",
    "live_strategy": "전략 변경",
    "live_resume_buys": "새 매수 다시 켜기",
    "live_end": "운용 끝내기",
    "live_sell_all_end": "전부 팔고 끝내기",
    "todo_match_account": "계좌에 맞추기",
    "todo_corp_action": "권리 변동 맞추기",
    "todo_big_order": "큰 주문 보내기",
    "toss_key_view": "토스 키 보기",
    "toss_key_change": "토스 키 변경",
    "toss_key_delete": "토스 키 삭제",
    "dart_key_view": "DART 키 보기",
    "dart_key_change": "DART 키 변경",
    "dart_key_delete": "DART 키 삭제",
    "telegram_key_view": "텔레그램 키 보기",
    "telegram_key_change": "텔레그램 키 변경",
    "telegram_key_delete": "텔레그램 키 삭제",
    "restore": "복원",
    "install_place": "설치 위치 변경",
    "data_delete": "앱 데이터 삭제",
    "unknown_order_record": "결과 모르는 주문 기록",
}


class VaultError(Exception):
    """화면에 그대로 보여도 되는 글만 담는다(비밀 값 없음)."""

    def __init__(self, message: str, status: int = 400, **extra: object) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_key(secret: str, salt: bytes, n: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=SCRYPT_R, p=SCRYPT_P).derive(secret.encode("utf-8"))


def seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def unseal(key: bytes, blob: bytes, aad: bytes) -> bytes:
    """틀린 키나 바뀐 글이면 InvalidTag."""
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def new_recovery_code() -> str:
    return "".join(secrets.choice(RC_ALPHABET) for _ in range(RC_LEN))


def format_recovery_code(code: str) -> str:
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def normalize_recovery_code(text: str) -> str:
    out = []
    for ch in (text or "").upper():
        if ch in " -_\t\n":
            continue
        ch = {"O": "0", "I": "1", "L": "1"}.get(ch, ch)
        out.append(ch)
    return "".join(out)


def normalize_password(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def check_new_password(password: str, password2: str) -> str:
    pw = normalize_password(password)
    if len(pw) < MIN_PASSWORD:
        raise VaultError("비밀번호는 8자 이상이어야 해요")
    if len(pw) > MAX_PASSWORD:
        raise VaultError("비밀번호는 128자까지 돼요")
    if pw != normalize_password(password2):
        raise VaultError("두 비밀번호가 달라요")
    return pw


class Vault:
    def __init__(
        self,
        db: DB,
        *,
        scrypt_n: int = SCRYPT_N,
        clock: Callable[[], float] = time.time,
        keyfile: Path | str | None = None,
        forbidden_dirs: tuple[Path | str, ...] = (),
    ) -> None:
        self.db = db
        self.scrypt_n = scrypt_n
        self.clock = clock
        self._key: bytes | None = None
        self._sessions: dict[str, float] = {}  # sha256(토큰) -> 끝나는 때
        self._lock = threading.RLock()
        # 이 서버 프로세스가 켜진 뒤 한 번이라도 열렸는가(로그인 화면의 '앱을 다시 켰어요' 안내)
        self.opened_since_start = False
        # 데이터 키를 지울 때 함께 부를 것들(토스 연결 객체 버리기 등). 잠그기 · 만료 · 마지막 세션 끝 모두.
        self.on_key_cleared: list[Callable[[], None]] = []
        self.keyfile = Path(keyfile) if keyfile is not None else None
        if self.keyfile is not None:
            for d in forbidden_dirs:
                if self.keyfile.resolve().is_relative_to(Path(d).resolve()):
                    raise ValueError("키 파일은 레포와 데이터 폴더 밖에 있어야 해요")
        self._runner_key: bytes | None = None  # 키 파일로 푼 데이터 키(실행기 몫 · 잠그기로 지워지지 않음)
        self._confirms: dict[str, tuple[str, float]] = {}  # sha256(토큰) -> (일, 끝나는 때)
        self.load_runner()

    # ── 상태 ───────────────────────────────────────────────────────────────

    def is_setup(self) -> bool:
        return self.db.one("SELECT 1 FROM owner WHERE id=1") is not None

    @property
    def unlocked(self) -> bool:
        with self._lock:
            self._purge()
            return self._key is not None

    def _locked_left(self) -> float:
        row = self.db.one("SELECT locked_until FROM owner WHERE id=1")
        if row is None:
            return 0.0
        return max(0.0, float(row["locked_until"]) - self.clock())

    def locked_for(self) -> int:
        """로그인이 잠겨 남은 초(화면에 보일 값): 내림, 5분 0초를 넘지 않는다. 0이면 1초 안에 풀린다."""
        return min(LOCK_S, int(self._locked_left()))

    # ── 처음 열기 ─────────────────────────────────────────────────────────

    def setup(self, password: str, password2: str, *, adult: bool, terms: bool) -> tuple[str, str]:
        """(세션 토큰, 복구 코드). 복구 코드는 이때 한 번만 바깥에 나간다."""
        with self._lock:
            if self.is_setup():
                raise VaultError("이미 계정이 있어요", 409)
            if not adult:
                raise VaultError("만 19세 이상만 쓸 수 있어요")
            if not terms:
                raise VaultError("사용 조건에 동의해야 시작할 수 있어요")
            pw = check_new_password(password, password2)
            data_key = AESGCM.generate_key(bit_length=256)
            code = new_recovery_code()
            pw_salt, rc_salt = os.urandom(16), os.urandom(16)
            pw_wrap = seal(derive_key(pw, pw_salt, self.scrypt_n), data_key, AAD_PW)
            rc_wrap = seal(derive_key(code, rc_salt, self.scrypt_n), data_key, AAD_RC)
            self.db.run(
                "INSERT INTO owner(id,scrypt_n,pw_salt,pw_wrap,rc_salt,rc_wrap,fails,locked_until,"
                "adult,terms_at,created_at) VALUES(1,?,?,?,?,?,0,0,1,?,?)",
                (self.scrypt_n, pw_salt, pw_wrap, rc_salt, rc_wrap, _now_iso(), _now_iso()),
            )
            self._key = data_key
            self._attach_keyfile(data_key)
            return self._new_session(), format_recovery_code(code)

    # ── 입장 ────────────────────────────────────────────────────────────────

    def _owner(self):  # type: ignore[no-untyped-def]
        row = self.db.one("SELECT * FROM owner WHERE id=1")
        if row is None:
            raise VaultError("아직 계정이 없어요 · 비밀번호를 먼저 만들어 주세요", 409)
        return row

    def _check_lock(self) -> None:
        if self._locked_left() > 0:
            left = self.locked_for()
            raise VaultError(
                f"5번 맞지 않아 잠금 · {left // 60}분 {left % 60}초 남음",
                429,
                locked_for=left,
            )

    def _fail(self) -> None:
        row = self._owner()
        fails = int(row["fails"]) + 1
        if fails >= MAX_FAILS:
            self.db.run(
                "UPDATE owner SET fails=0, locked_until=? WHERE id=1", (self.clock() + LOCK_S,)
            )
            raise VaultError("5번 맞지 않아 잠금 · 5분 0초 남음", 429, locked_for=LOCK_S)
        self.db.run("UPDATE owner SET fails=? WHERE id=1", (fails,))
        raise VaultError(
            f"비밀번호가 맞지 않아요 · 남은 횟수 {MAX_FAILS - fails}번",
            401,
            tries_left=MAX_FAILS - fails,
        )

    def login(self, password: str) -> str:
        with self._lock:
            row = self._owner()
            self._check_lock()
            pw = normalize_password(password)
            try:
                key = derive_key(pw, bytes(row["pw_salt"]), int(row["scrypt_n"]))
                data_key = unseal(key, bytes(row["pw_wrap"]), AAD_PW)
            except (InvalidTag, ValueError):
                self._fail()
                raise  # _fail은 늘 예외를 던진다
            self.db.run("UPDATE owner SET fails=0, locked_until=0 WHERE id=1")
            self._key = data_key
            self._attach_keyfile(data_key)
            return self._new_session()

    def recover(self, code: str, password: str, password2: str) -> tuple[str, str]:
        """복구 코드로 새 비밀번호를 만든다. 쓴 복구 코드는 버리고 새 코드를 한 번 보인다."""
        with self._lock:
            row = self._owner()
            self._check_lock()
            pw = check_new_password(password, password2)
            norm = normalize_recovery_code(code)
            try:
                if len(norm) != RC_LEN:
                    raise ValueError("length")
                key = derive_key(norm, bytes(row["rc_salt"]), int(row["scrypt_n"]))
                data_key = unseal(key, bytes(row["rc_wrap"]), AAD_RC)
            except (InvalidTag, ValueError):
                try:
                    self._fail()
                except VaultError as exc:
                    if exc.status == 401:
                        raise VaultError(
                            exc.message.replace("비밀번호가", "복구 코드가"), 401, **exc.extra
                        ) from None
                    raise
                raise
            new_code = new_recovery_code()
            pw_salt, rc_salt = os.urandom(16), os.urandom(16)
            self.db.run(
                "UPDATE owner SET pw_salt=?, pw_wrap=?, rc_salt=?, rc_wrap=?, fails=0, locked_until=0 "
                "WHERE id=1",
                (
                    pw_salt,
                    seal(derive_key(pw, pw_salt, self.scrypt_n), data_key, AAD_PW),
                    rc_salt,
                    seal(derive_key(new_code, rc_salt, self.scrypt_n), data_key, AAD_RC),
                ),
            )
            self._sessions.clear()  # 예전 비밀번호로 연 세션은 모두 닫는다
            self._key = data_key
            self._attach_keyfile(data_key)
            return self._new_session(), format_recovery_code(new_code)

    def change_password(self, current: str, password: str, password2: str) -> None:
        """지금 비밀번호로 데이터 키가 풀리는지 보고, 새 비밀번호로 데이터 키를 다시 감싼다.

        틀린 횟수 · 잠금은 로그인과 같이 센다. 복구 코드 감싸기는 그대로 둔다.
        """
        with self._lock:
            row = self._owner()
            self._check_lock()
            pw_new = check_new_password(password, password2)
            pw = normalize_password(current)
            try:
                key = derive_key(pw, bytes(row["pw_salt"]), int(row["scrypt_n"]))
                data_key = unseal(key, bytes(row["pw_wrap"]), AAD_PW)
            except (InvalidTag, ValueError):
                try:
                    self._fail()
                except VaultError as exc:
                    if exc.status == 401:
                        raise VaultError(
                            exc.message.replace("비밀번호가", "지금 비밀번호가"), 401, **exc.extra
                        ) from None
                    raise
                raise
            pw_salt = os.urandom(16)
            self.db.run(
                "UPDATE owner SET pw_salt=?, pw_wrap=?, fails=0, locked_until=0 WHERE id=1",
                (pw_salt, seal(derive_key(pw_new, pw_salt, self.scrypt_n), data_key, AAD_PW)),
            )
            self._key = data_key
            self._attach_keyfile(data_key)

    # ── 컴퓨터 키 파일 ─────────────────────────────────────────────────────

    def _machine_key(self, create: bool) -> bytes | None:
        """키 파일의 32바이트. 다른 사용자가 읽을 수 있는 권한이면 쓰지 않는다."""
        path = self.keyfile
        if path is None:
            return None
        if not path.exists():
            if not create:
                return None
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, os.urandom(32).hex().encode())
            finally:
                os.close(fd)
        if path.stat().st_mode & 0o077:
            return None
        raw = path.read_text().strip()
        try:
            key = bytes.fromhex(raw)
        except ValueError:
            return None
        return key if len(key) == 32 else None

    def _attach_keyfile(self, data_key: bytes) -> None:
        """비밀번호로 연 김에 키 파일 감싸기를 맞춰 둔다(없거나 키 파일이 바뀌었으면 새로 감싼다)."""
        try:
            mk = self._machine_key(create=True)
        except OSError:
            return
        if mk is None:
            return
        row = self.db.one("SELECT wrap FROM owner_keyfile WHERE id=1")
        if row is not None:
            try:
                if unseal(mk, bytes(row["wrap"]), AAD_KF) == data_key:
                    self._runner_key = data_key
                    return
            except (InvalidTag, ValueError):
                pass
        self.db.run(
            "INSERT INTO owner_keyfile(id,wrap,at) VALUES(1,?,?) "
            "ON CONFLICT(id) DO UPDATE SET wrap=excluded.wrap, at=excluded.at",
            (seal(mk, data_key, AAD_KF), _now_iso()),
        )
        self._runner_key = data_key

    def load_runner(self) -> bool:
        """앱이 켜질 때: 키 파일로 데이터 키를 푼다(로그인 없이). 화면은 여전히 잠겨 있다."""
        with self._lock:
            if not self.is_setup():
                return False
            row = self.db.one("SELECT wrap FROM owner_keyfile WHERE id=1")
            try:
                mk = self._machine_key(create=False)
            except OSError:
                mk = None
            if row is None or mk is None:
                return False
            try:
                self._runner_key = unseal(mk, bytes(row["wrap"]), AAD_KF)
            except (InvalidTag, ValueError):
                self._runner_key = None
            return self._runner_key is not None

    @property
    def runner_ready(self) -> bool:
        return self._runner_key is not None

    @property
    def can_read(self) -> bool:
        """비밀 값을 풀 수 있나(화면 세션 또는 실행기 키 파일)."""
        return self.unlocked or self.runner_ready

    def reload(self) -> None:
        """데이터 파일이 바뀐 뒤(복원 · 삭제): 화면 세션 · 데이터 키를 지우고 실행기 키를 새 파일로 다시 풀어요."""
        with self._lock:
            self._sessions.clear()
            self._confirms.clear()
            self._clear_key()
            self._runner_key = None
            self.load_runner()

    def forget_keyfile(self) -> None:
        """앱 데이터 삭제 때: 감싼 키와 메모리의 실행기 키를 지운다(키 파일은 다른 앱 데이터에 쓰일 수 있어 둔다)."""
        with self._lock:
            self.db.run("DELETE FROM owner_keyfile")
            self._runner_key = None

    # ── 비밀번호 다시 받기(돈이 움직이는 일) ────────────────────────────────

    def confirm(self, password: str, action: str) -> str:
        """비밀번호가 맞으면 그 일 하나에만 쓰는 짧은 1회용 토큰. 틀린 횟수 · 잠금은 로그인과 같이 센다."""
        if action not in MONEY_ACTIONS:
            raise VaultError("없는 일이에요", 400)
        with self._lock:
            row = self._owner()
            self._check_lock()
            try:
                key = derive_key(normalize_password(password), bytes(row["pw_salt"]), int(row["scrypt_n"]))
                unseal(key, bytes(row["pw_wrap"]), AAD_PW)
            except (InvalidTag, ValueError):
                self._fail()
                raise
            self.db.run("UPDATE owner SET fails=0, locked_until=0 WHERE id=1")
            now = self.clock()
            for h, (_, until) in list(self._confirms.items()):
                if until <= now:
                    del self._confirms[h]
            token = secrets.token_urlsafe(24)
            self._confirms[self._hash(token)] = (action, now + CONFIRM_S)
            return token

    def use_confirm(self, token: str | None, action: str) -> None:
        """토큰을 한 번 쓴다. 없거나 다른 일 · 지난 토큰이면 비밀번호 창을 띄우라는 403."""
        with self._lock:
            got = self._confirms.pop(self._hash(token), None) if token else None
            if got is None or got[0] != action or got[1] <= self.clock():
                raise VaultError(
                    "비밀번호를 다시 입력해 주세요", 403, need_confirm=True, action=action,
                    title=MONEY_ACTIONS.get(action, ""),
                )

    # ── 세션 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _new_session(self) -> str:
        self.opened_since_start = True
        token = secrets.token_urlsafe(32)
        self._sessions[self._hash(token)] = self.clock() + SESSION_S
        return token

    def _purge(self) -> None:
        now = self.clock()
        for h, until in list(self._sessions.items()):
            if until <= now:
                del self._sessions[h]
        if not self._sessions:
            self._clear_key()

    def _clear_key(self) -> None:
        had = self._key is not None
        self._key = None
        if had:
            for hook in list(self.on_key_cleared):
                hook()

    def session_ok(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            self._purge()
            return self._hash(token) in self._sessions

    def logout(self, token: str | None) -> None:
        with self._lock:
            if token:
                self._sessions.pop(self._hash(token), None)
            self._purge()

    def lock_now(self) -> None:
        """잠그기: 모든 세션을 끝내고 메모리의 데이터 키를 지운다(설정 › 잠그기 · 시험)."""
        with self._lock:
            self._sessions.clear()
            self._clear_key()

    # ── 비밀 값 ─────────────────────────────────────────────────────────────

    def _need_key(self) -> bytes:
        self._purge()
        key = self._key or self._runner_key
        if key is None:
            raise VaultError("잠금 · 비밀번호를 입력하면 다시 실행돼요", 423)
        return key

    def put_secret(self, name: str, value: str) -> None:
        with self._lock:
            key = self._need_key()
            blob = seal(key, value.encode("utf-8"), b"secret:" + name.encode())
            self.db.run(
                "INSERT INTO secrets(name,blob,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET blob=excluded.blob, updated_at=excluded.updated_at",
                (name, blob, _now_iso()),
            )

    def get_secret(self, name: str) -> str | None:
        with self._lock:
            row = self.db.one("SELECT blob FROM secrets WHERE name=?", (name,))
            if row is None:
                return None
            key = self._need_key()
            try:
                return unseal(key, bytes(row["blob"]), b"secret:" + name.encode()).decode("utf-8")
            except InvalidTag:
                raise VaultError("저장한 API 키를 풀지 못했어요 · 삭제하고 다시 등록해 주세요", 500) from None

    def has_secret(self, name: str) -> bool:
        return self.db.one("SELECT 1 FROM secrets WHERE name=?", (name,)) is not None

    def delete_secret(self, name: str) -> None:
        self.db.run("DELETE FROM secrets WHERE name=?", (name,))

    def tail(self, name: str) -> str | None:
        """끝 4자리만. 잠겨 있으면 None."""
        if not self.has_secret(name) or not self.unlocked:
            return None
        value = self.get_secret(name) or ""
        return value[-4:]
