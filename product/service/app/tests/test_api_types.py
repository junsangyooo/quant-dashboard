"""화면 API 타입(ARCHITECTURE 7절 'API 타입' · TASKS P1-09): 생성 타입이 최신 · `web/src/api`에 손으로 쓴 API 타입 0.

- `web/src/api/types.gen.ts`는 앱 객체의 OpenAPI(응답 모델 `app/api/*`)에서 openapi-typescript 7.13.0으로 만들어요
  (`scripts/gen_api_types.py`). 응답 모델을 바꾸고 다시 만들지 않으면 여기서 실패해요.
- `web/src/api/*.ts`(생성 파일 빼고)는 응답 타입을 생성 타입의 이름으로만 가리켜요: 객체 꼴을 손으로 적은 `interface` ·
  `type X = { … }` · 타입 인자 `<{ … }>` · 글자 값 나열(`'a' | 'b'`) 0. API 응답이 아닌 것(아래 `NOT_API`)만 까닭과 함께 뺌.
- `web/src` 전부(화면 · 부품 · 시험 밖 · 생성 파일 빼고): API 부르기의 타입 인자에 객체 꼴을 손으로 적지 않아요(`api.post<{ … }>` ·
  `.get<{ … }>` · `put` · `delete` 0 · P1-09 검토 심각도 1을 P1-11에서 · 화면은 `web/src/api/*.ts`의 생성 타입 별칭을 써요).
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import gen_api_types
from tests import structure_guards

API_DIR = Path(__file__).resolve().parent.parent / "web" / "src" / "api"
GENERATED = API_DIR / "types.gen.ts"
# API 응답 꼴이 아닌 타입(까닭): 요청 보내기 설정(fetch 함수 · 로그인 · 비밀번호 창 콜백)
NOT_API = {"ClientConfig"}

INTERFACE = re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)", re.M)
TYPE_ALIAS = re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*=\s*(.+?);\s*$", re.M | re.S)
OBJECT_LITERAL = re.compile(r"\{\s*(?:readonly\s+)?[A-Za-z_]\w*\??\s*:")  # `{ name: …` · `{ name?: …`(꼴을 손으로 적음)
STRING_UNION = re.compile(r"^\(?\s*'[^']*'\s*\|")  # `'a' | 'b'`(서버 값 나열을 손으로 적음)
TYPE_ARG = re.compile(r"<\s*\{")  # `api.get<{ … }>`
CALL_TYPE_ARG = re.compile(r"\.(?:get|post|put|delete)\s*<\s*\{")  # 화면 파일의 `api.post<{ token: string }>(…)`
WEB_SRC = API_DIR.parent


def hand_written(text: str) -> list[str]:
    """한 파일에서 손으로 쓴 API 타입 자리(이름 · 꼴)."""
    out = [f"interface {n}" for n in INTERFACE.findall(text) if n not in NOT_API]
    for name, rhs in TYPE_ALIAS.findall(text):
        if name in NOT_API:
            continue
        if OBJECT_LITERAL.search(rhs) or STRING_UNION.search(rhs.strip()):
            out.append(f"type {name}")
    out += [f"type argument at line {text[: m.start()].count(chr(10)) + 1}" for m in TYPE_ARG.finditer(text)]
    return out


def test_no_hand_written_api_types_in_web_api() -> None:
    files = sorted(p for p in API_DIR.glob("*.ts") if p != GENERATED)
    assert files and GENERATED.exists()
    problems = {p.name: found for p in files if (found := hand_written(p.read_text(encoding="utf-8")))}
    assert problems == {}


def test_hand_written_check_catches_planted_types() -> None:
    planted = (
        "export interface LiveTodo {\n  id: number;\n}\n"
        "export type Card = { id: number; name?: string };\n"
        "export type Side = 'buy' | 'sell';\n"
        "export const f = () => api.get<{ ok: boolean }>('/api/x');\n"
        "export type Fine = Schemas['LiveTodo'];\n"
        "export type Ask = { [K in 'action' | 'title']: string };\n"
        "interface ClientConfig {\n  fetch: typeof fetch;\n}\n"
    )
    assert hand_written(planted) == ["interface LiveTodo", "type Card", "type Side", "type argument at line 6"]


def call_type_args(text: str) -> list[int]:
    """API 부르기 타입 인자에 손으로 적은 객체 꼴이 있는 줄."""
    return [text[: m.start()].count(chr(10)) + 1 for m in CALL_TYPE_ARG.finditer(text)]


def test_no_hand_written_api_type_args_in_web_src() -> None:
    files = sorted(p for p in WEB_SRC.rglob("*") if p.suffix in (".ts", ".tsx") and p != GENERATED)
    assert len(files) > 50
    problems = {p.relative_to(WEB_SRC).as_posix(): lines for p in files
                if (lines := call_type_args(p.read_text(encoding="utf-8")))}
    assert problems == {}


def test_call_type_arg_check_catches_planted_calls() -> None:
    planted = (
        "const r = await api.post<{ token: string }>('/api/confirm', b);\n"
        "api\n  .get<{\n    ip: string }>('/api/x');\n"
        "const ok = api.post<ConfirmToken>('/api/confirm', b);\n"
        "const m = new Map<{ a: number }, string>();\n"
        "api.put< { a: 1 } >('/x'); api.delete<{ ok: boolean }>('/y');\n"
    )
    assert call_type_args(planted) == [1, 3, 7, 7]


def test_generated_api_types_are_up_to_date() -> None:
    """응답 모델 → OpenAPI → TypeScript를 다시 만들어 지금 파일과 글자 그대로 같아야 해요(npm 캐시 · 바깥 요청 없게)."""
    text = gen_api_types.render(env=structure_guards._npm_env())
    assert GENERATED.read_text(encoding="utf-8") == text, "scripts/gen_api_types.py로 다시 만들어요"
    assert text.startswith(gen_api_types.HEADER) and "export interface components" in text
