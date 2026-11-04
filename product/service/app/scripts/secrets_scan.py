"""비밀 검사(QUALITY S11 · P1-02 ⑥): `product/` 아래 git이 추적하는 글 파일에서 비밀 꼴 문자열을 찾아요.

    cd product/service/app && .venv/bin/python scripts/secrets_scan.py        # 어느 폴더에서 불러도 같아요

찾는 꼴(거짓 경보가 적게 좁게):
- key: 제공사 키 꼴(`sk-…` · `AKIA…` · GitHub `ghp_…` · `github_pat_…` · Slack `xox?-…` · Google `AIza…`) · PEM 개인 키 머리.
- token: 텔레그램 봇 토큰(`숫자:35자`) · JWT(`eyJ….….…`).
- account: 10 ~ 12자리 숫자 덩어리(계좌번호 꼴 · 앞뒤에 글자 · 점 · 빗금이 붙은 것은 뺌 · 13자리 ms 시각 · 14자리 DART 접수번호는 안 걸려요)
  · 하이픈 꼴(`987-12-345601` · `12345678-01` · 묶음 2 ~ 4개 · 숫자만 세어 10 ~ 14자리 · 날짜 `2026-11-04`(8자리)는 안 걸려요).
- ip: 공인 IPv4(127/8 · 10/8 · 172.16/12 · 192.168/16 · 169.254/16 · 100.64/10 · 0/8 · 224 이상 · 문서용 192.0.2 · 198.51.100 ·
  203.0.113은 뺌).

빼는 파일(까닭): 이진 파일(글꼴 · 그림 · 아이콘) · `vendor/`(바깥 명세 · 견본 그대로) · `package-lock.json` · `requirements*.lock`
(생성 파일 · 해시 문자열) · `tests/fixtures/` · `tests/baseline/frozen/` · `tests/baseline/server/` · `tests/baseline/web/`(얼린 시험
자료 · 기록 · 지어낸 값) · `web/src/styles/pretendard.css`(생성된 글꼴 CSS). 지어낸 시험 값(`12345671234` 등)은
`tests/allow/secrets.txt`에 `경로 종류 값  # 까닭`으로 둬요. 목록의 줄은 실제로 그 값이 있을 때만 유효해요(없어지면 줄을 지워요).
종료 코드: 0 통과 · 1 허용 목록 밖 발견(또는 쓸모없는 허용 줄) · 2 실행 실패.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
REPO = APP.parents[2]
ALLOW = APP / "tests" / "allow" / "secrets.txt"
SCOPE = "product"

BINARY_SUFFIXES = {".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".db"}
# (경로 조각, 까닭)
EXCLUDED_PARTS = [
    ("product/service/vendor/", "바깥 명세 · 견본(토스 OpenAPI · DART)을 그대로 둔 폴더"),
    ("/package-lock.json", "생성 파일(npm) · integrity 해시"),
    ("/requirements.lock", "생성 파일(pip-compile) · sha256 해시"),
    ("/requirements-dev.lock", "생성 파일(pip-compile) · sha256 해시"),
    ("/tests/fixtures/", "시험 자료(지어낸 값)"),
    ("/tests/baseline/frozen/", "얼린 시험 자료(P1-01a · 지어낸 값)"),
    ("/tests/baseline/server/", "기준선 기록(P1-01b · 시험이 보낸 지어낸 값이 섞여 있음)"),
    ("/tests/baseline/web/", "기준선 기록(P1-01c · 화면 글 · PNG sha256)"),
    ("/web/src/styles/pretendard.css", "생성된 글꼴 CSS"),
    ("/tests/allow/secrets.txt", "이 검사의 허용 목록 자체(지어낸 값이 적혀 있음)"),
]

PATTERNS: dict[str, re.Pattern[str]] = {
    "key": re.compile(
        r"(?<![A-Za-z0-9_-])(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[opsur]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}"
        r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})(?![A-Za-z0-9_-])"
        r"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |)PRIVATE KEY(?: BLOCK)?-----"
    ),
    "token": re.compile(
        r"(?<![0-9A-Za-z_-])[0-9]{8,10}:[A-Za-z0-9_-]{35}(?![0-9A-Za-z_-])"
        r"|(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])"
    ),
    "account": re.compile(
        r"(?<![0-9A-Za-z_.\-/])[0-9]{10,12}(?![0-9A-Za-z_.\-/])"
        r"|(?<![0-9A-Za-z_.\-/])[0-9]{2,10}(?:-[0-9]{2,10}){1,3}(?![0-9A-Za-z_.\-/])"  # 하이픈 꼴 · 숫자 수는 아래에서 봐요
    ),
    "ip": re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])"),
}
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def _public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    return not any(ip in n for n in DOC_NETS)


def tracked_files() -> list[Path]:
    p = subprocess.run(["git", "ls-files", "-z", SCOPE], cwd=REPO, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"git ls-files 실패: {p.stderr.strip()}")
    return [REPO / f for f in p.stdout.split("\0") if f]


def excluded(rel: str) -> str | None:
    for part, why in EXCLUDED_PARTS:
        if part in "/" + rel:
            return why
    return None


def scan_text(rel: str, text: str) -> list[tuple[str, int, str, str]]:
    hits = []
    for no, line in enumerate(text.splitlines(), 1):
        for kind, pat in PATTERNS.items():
            for m in pat.finditer(line):
                value = m.group(0)
                if kind == "ip" and not _public_ip(value):
                    continue
                if kind == "account" and "-" in value and not 10 <= sum(c.isdigit() for c in value) <= 14:
                    continue
                hits.append((rel, no, kind, value))
    return hits


def scan(files: list[Path]) -> tuple[list[tuple[str, int, str, str]], int, int]:
    hits: list[tuple[str, int, str, str]] = []
    scanned = skipped = 0
    for f in files:
        rel = f.relative_to(REPO).as_posix()
        if f.suffix.lower() in BINARY_SUFFIXES or excluded(rel) or not f.is_file():
            skipped += 1
            continue
        raw = f.read_bytes()
        if b"\0" in raw[:4096]:
            skipped += 1
            continue
        scanned += 1
        hits += scan_text(rel, raw.decode("utf-8", errors="replace"))
    return hits, scanned, skipped


def load_allow() -> dict[tuple[str, str, str], str]:
    allow: dict[tuple[str, str, str], str] = {}
    if not ALLOW.exists():
        return allow
    for raw in ALLOW.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise SystemExit(f"허용 목록 줄을 읽을 수 없어요: {raw}")
        allow[(parts[0], parts[1], parts[2])] = raw
    return allow


def main() -> int:
    hits, scanned, skipped = scan(tracked_files())
    allow = load_allow()
    found_keys = {(rel, kind, value) for rel, _, kind, value in hits}
    problems = [f"{rel}:{no}: {kind} {value}" for rel, no, kind, value in hits if (rel, kind, value) not in allow]
    stale = [allow[k] for k in sorted(allow) if k not in found_keys]
    print(f"비밀 검사: 파일 {scanned}(뺌 {skipped}) · 발견 {len(hits)} · 허용 목록 {len(allow)}줄 · 허용 밖 {len(problems)} · 쓸모없는 허용 줄 {len(stale)}")
    for line in problems:
        print("  허용 밖:", line)
    for line in stale:
        print("  쓸모없는 허용 줄(값이 없어졌어요 · 줄을 지워요):", line.strip())
    return 1 if problems or stale else 0


if __name__ == "__main__":
    sys.exit(main())
