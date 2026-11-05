"""API 응답 타입 만들기(TASKS P1-09 · ARCHITECTURE 3절 'API 클라이언트' · 4절 '화면 · API 타입 생성' · 7절 'API 타입').

    cd product/service/app && .venv/bin/python scripts/gen_api_types.py          # web/src/api/types.gen.ts를 다시 만들어요
    cd product/service/app && .venv/bin/python scripts/gen_api_types.py --check  # 최신인지만(다르면 종료 1 · pytest가 불러요)

- 원본은 앱 객체의 OpenAPI(`create_app(...).openapi()` · 응답 모델은 `app/api/*`)예요. 실행 중인 앱은 OpenAPI 주소를 열지 않아요
  (`openapi_url=None`) · 여기서 앱을 만들어 바로 읽어요(가짜 전송 · 임시 데이터 폴더 · 키 파일 없음 · 바깥 요청 0).
- 바꾸는 도구는 openapi-typescript 7.13.0(P1-00에서 정확한 판 확인 · `npx`로 고정 판 · `package.json`은 그대로 · jscpd와 같은 꼴)이에요.
  npm 캐시를 먼저 써요(`npm_config_prefer_offline`). 상태에 따라 나오는 키(`opt()` · 기본값 null)는 `--default-non-nullable false`로
  선택 키(`?:`)로 둬요.
- 화면 쪽 타입(`web/src/api/*.ts`)은 이 파일의 `components["schemas"]`를 이름으로 가리켜요(손으로 쓴 API 타입 0 · 시험).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
WEB = APP / "web"
OUT = WEB / "src" / "api" / "types.gen.ts"
TOOL = "openapi-typescript@7.13.0"
HEADER = "// 만든 파일 · 손대지 않아요 · 다시 만들기: product/service/app/scripts/gen_api_types.py (OpenAPI → openapi-typescript 7.13.0)\n"


def openapi_json() -> str:
    """앱 객체의 OpenAPI(JSON 글 · 키 차례 그대로 · 같은 코드면 늘 같은 글)."""
    from app.app import create_app

    with tempfile.TemporaryDirectory(prefix="quant-openapi-") as d:
        app = create_app(Path(d) / "data", scheduler=False, keyfile=False)
        spec = app.openapi()
    # FastAPI가 저절로 적는 422(요청 검사 실패)는 이 앱에서 400 + `ErrorBody`예요(`api/errors.py`) · 지금 모양 그대로 빼요
    for ops in spec.get("paths", {}).values():
        for op in ops.values():
            op.get("responses", {}).pop("422", None)
    for name in ("HTTPValidationError", "ValidationError"):
        spec.get("components", {}).get("schemas", {}).pop(name, None)
    return json.dumps(spec, ensure_ascii=False, indent=1)


def render(env: dict[str, str] | None = None) -> str:
    """OpenAPI → TypeScript 글(머리 한 줄 + openapi-typescript 출력)."""
    with tempfile.TemporaryDirectory(prefix="quant-openapi-ts-") as d:
        src, out = Path(d) / "openapi.json", Path(d) / "types.gen.ts"
        src.write_text(openapi_json(), encoding="utf-8")
        cmd = ["npx", "--yes", TOOL, str(src), "--output", str(out), "--default-non-nullable", "false"]
        p = subprocess.run(cmd, cwd=WEB, capture_output=True, text=True, env=env or npm_env())
        if p.returncode != 0 or not out.exists():
            raise SystemExit(f"openapi-typescript 실패(exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
        return HEADER + out.read_text(encoding="utf-8")


def npm_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("npm_config_prefer_offline", "true")
    return env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_api_types")
    ap.add_argument("--check", action="store_true", help="다시 만든 글이 지금 파일과 같은지만(다르면 종료 1)")
    a = ap.parse_args(argv)
    text = render()
    if a.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("types.gen.ts 최신" if same else "types.gen.ts가 응답 모델과 달라요 · scripts/gen_api_types.py로 다시 만들어요")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"썼어요: {OUT.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
