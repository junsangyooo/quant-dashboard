"""의존성 취약점 검사(QUALITY S7 · P1-02 ⑦): pip-audit(lock 기준) · npm audit을 돌려 허용 목록과 대조해요.

    cd product/service/app && .venv/bin/python scripts/audit_allow.py pip    # requirements.lock · requirements-dev.lock
    cd product/service/app && .venv/bin/python scripts/audit_allow.py npm    # web/package-lock.json(npm audit --json)

- 허용 목록 `tests/allow/audit-pip.txt` · `audit-npm.txt`: 한 줄 = `취약점번호 패키지  # 까닭`(1단계는 판을 올리지 않고 허용 목록과
  OPEN-QUESTIONS로 · 허용 밖 취약점이 있으면 실패 · 목록에 있는데 더 안 나오면 줄을 지우라고 실패).
- 바깥 요청은 취약점 자료(PyPI · OSV · npm 등록소)뿐이에요. 종료 코드: 0 통과 · 1 어긋남 · 2 실행 실패.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ALLOW = APP / "tests" / "allow"
PIP_LOCKS = ["requirements.lock", "requirements-dev.lock"]


def load_allow(name: str) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for raw in (ALLOW / name).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise SystemExit(f"허용 목록 줄을 읽을 수 없어요({name}): {raw}")
        out[(parts[0], parts[1])] = raw.strip()
    return out


def pip_findings() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for lock in PIP_LOCKS:
        cmd = [sys.executable, "-m", "pip_audit", "--require-hashes", "-r", lock, "--format", "json", "--progress-spinner", "off"]
        p = subprocess.run(cmd, cwd=APP, capture_output=True, text=True)
        if p.returncode not in (0, 1) or not p.stdout.strip().startswith("{"):
            raise SystemExit(f"pip-audit 실행 실패({lock} · exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
        for dep in json.loads(p.stdout).get("dependencies", []):
            for v in dep.get("vulns", []):
                found.add((v["id"], f"{dep['name']}=={dep['version']}"))
    return found


def npm_findings() -> set[tuple[str, str]]:
    p = subprocess.run(["npm", "audit", "--json"], cwd=APP / "web", capture_output=True, text=True)
    text = p.stdout.strip()
    if not text.startswith("{"):
        raise SystemExit(f"npm audit 실행 실패(exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
    data = json.loads(text)
    if "error" in data:
        raise SystemExit(f"npm audit 실행 실패: {data['error']}")
    found: set[tuple[str, str]] = set()
    for name, item in data.get("vulnerabilities", {}).items():
        for via in item.get("via", []):
            if isinstance(via, dict):  # 문자열이면 다른 항목을 통해 걸린 것(그 항목에서 셈)
                vid = re.sub(r".*/", "", str(via.get("url") or via.get("source") or ""))
                found.add((vid, str(via.get("name") or name)))
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("pip", "npm"):
        print(__doc__)
        return 2
    tool = argv[0]
    found = pip_findings() if tool == "pip" else npm_findings()
    allow = load_allow(f"audit-{tool}.txt")
    extra = sorted(found - set(allow))
    stale = [allow[k] for k in sorted(set(allow) - found)]
    print(f"{tool} audit: 취약점 {len(found)} · 허용 목록 {len(allow)} · 허용 밖 {len(extra)} · 쓸모없는 허용 줄 {len(stale)}")
    for vid, pkg in extra:
        print(f"  허용 밖: {vid} {pkg}")
    for line in stale:
        print(f"  쓸모없는 허용 줄(더 안 나와요 · 줄을 지워요): {line}")
    return 1 if extra or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
