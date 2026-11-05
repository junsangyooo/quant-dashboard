"""화면 글 한 출처(TASKS P1-11 · ARCHITECTURE 2절 '글' · 3절 '화면 글' · 7절 '같은 글' · '금지어').

- 글 목록 `copy/texts.json`(id → 지금 글 그대로 · 변수는 `{name}` 꼴)에서 `scripts/gen_texts.py`가 서버 쪽 `app/copy/texts.py` ·
  화면 쪽 `web/src/copy/texts.gen.ts`를 만들어요. 다시 만들어 글자 그대로 같아야 해요(최신).
- 목록의 꼴: id 꼴 · 묶음 사이 같은 id 0 · 같은 글 두 번 0 · id는 조건 사전(`app/domain/catalog.py`) 이름과 겹치지 않음 · 금지어 0.
- 글 목록을 가져올 수 있는 층(서버: 조립 · API · 쓰기 일 · 실행 흐름 · 화면: `web/src` 전부)은 목록에 있는 글을 글자로 다시 쓰지
  않아요(목록 밖 같은 글을 세는 장치가 목록 파일을 셈 밖에 두어서 · 그 빈틈을 여기서 막아요). 목록을 가져올 수 없는 층(보안 ·
  바깥 연결 · 입구 · 도메인)과 기준선 시계 자리로 얼린 파일(`app/backtest_v2.py` · Q-N24)은 뺌(보고 `P1-11.md`).
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.copy import texts as T
from app.domain import catalog
from scripts import gen_texts
from tests import words_rules as wr
from tests.baseline import counts, webcounts

# 글 목록을 가져와도 되는 서버 층(ARCHITECTURE 2절 표 · 조립은 아래 층 전부)
COPY_LAYERS = {"assembly", "api", "services", "run"}
# 기준선 시계 자리로 얼린 파일(Q-N24 · 이 일감에서 손대지 않음): 그 파일에 남은 목록 글 id
FROZEN = {"app/backtest_v2.py": {"toss_needed_link"}}


def _plain_texts() -> dict[str, str]:
    """글 → id(변수가 없는 글 · 같은 글 셈 규칙 8자 이상 + 한글 하나 이상)."""
    groups = gen_texts.load()
    return {text: tid for g in groups.values() for tid, text in g.items()
            if not gen_texts.variables(text) and webcounts._eligible(text)}


def test_generated_text_modules_are_up_to_date() -> None:
    for path, text in gen_texts.outputs():
        assert path.read_text(encoding="utf-8") == text, f"scripts/gen_texts.py로 다시 만들어요: {path}"


def test_python_texts_are_the_list() -> None:
    groups = gen_texts.load()
    want = {**groups["both"], **groups["server"]}
    got = {k: v for k, v in vars(T).items() if not k.startswith("_") and isinstance(v, str)}
    assert got == want
    assert not set(groups["web"]) & set(got)


def test_ts_texts_are_the_list() -> None:
    groups = gen_texts.load()
    ts = gen_texts.TS_OUT.read_text(encoding="utf-8")
    ids = re.findall(r"^  ([a-z][a-z0-9_]*): ", ts, re.M)
    assert ids == [*groups["both"], *groups["web"]]
    assert not set(groups["server"]) & set(ids)


def test_list_shape_rules(tmp_path: Path) -> None:
    def bad(data: dict[str, Any]) -> str:
        p = tmp_path / "t.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError) as e:
            gen_texts.load(p)
        return str(e.value)

    assert "같은 글" in bad({"both": {"a": "같은 글 하나 둘"}, "web": {"b": "같은 글 하나 둘"}})
    assert "두 묶음" in bad({"server": {"a": "가나다라마바사"}, "web": {"a": "아자차카타파하"}})
    assert "id는" in bad({"web": {"Bad-Id": "가나다라마바사"}})
    assert "모르는 묶음" in bad({"misc": {}})


def test_ts_render_templates_and_escapes() -> None:
    out = gen_texts.render_ts({"both": {}, "server": {}, "web": {
        "a": "버전 {n} · 바뀐 곳 {n}", "b": "`따옴표` ${ 그대로 } \\ {from} ~ {to}", "c": '그냥 "글"'}})
    assert "  a: (v: { n: number | string }): string => `버전 ${String(v.n)} · 바뀐 곳 ${String(v.n)}`," in out
    assert ("  b: (v: { from: number | string; to: number | string }): string => "
            "`\\`따옴표\\` \\${ 그대로 } \\\\ ${String(v.from)} ~ ${String(v.to)}`,") in out
    assert '  c: "그냥 \\"글\\"",' in out


def _catalog_names(obj: Any, out: set[str]) -> None:
    if isinstance(obj, str):
        if gen_texts.ID.match(obj):
            out.add(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _catalog_names(k, out)
            _catalog_names(v, out)
    elif isinstance(obj, list | tuple | set | frozenset):
        for v in obj:
            _catalog_names(v, out)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            _catalog_names(getattr(obj, f.name), out)


def test_text_ids_do_not_collide_with_catalog_names() -> None:
    names: set[str] = set()
    for k, v in vars(catalog).items():
        if k.isupper():
            _catalog_names(v, names)
    assert {"per", "top_n", "universe", "gte", "intraday", "foreign", "n"} <= names  # 조건 사전 이름을 읽었어요
    ids = {tid for g in gen_texts.load().values() for tid in g}
    assert ids & names == set()


def test_text_list_has_no_forbidden_words() -> None:
    rules = wr.load_rules()
    hits = [f"{tid}: {h}" for g in gen_texts.load().values() for tid, text in g.items() for h in wr.hits(text, rules)]
    assert hits == []


def test_list_texts_are_not_rewritten_on_the_server() -> None:
    plain = _plain_texts()
    found = []
    for p in counts.app_files():
        r = counts.rel(p)
        if r == counts.TEXT_LIST or counts.layer_of(r) not in COPY_LAYERS:
            continue
        for text, line in counts._strings(counts._parse(p)):
            if text in plain and plain[text] not in FROZEN.get(r, set()):
                found.append(f"{r}:{line} {plain[text]}")
    assert found == []


def test_list_texts_are_not_rewritten_on_the_web() -> None:
    plain = _plain_texts()
    found = []
    for p in webcounts.src_files():
        r = webcounts.rel(p)
        if r == webcounts.TEXT_LIST:
            continue
        for text, line in webcounts.screen_strings(p.read_text(encoding="utf-8")):
            if text in plain:
                found.append(f"{r}:{line} {plain[text]}")
    assert found == []


def test_frozen_file_keeps_only_its_listed_text() -> None:
    """얼린 파일의 몫은 지금 남은 것만(줄어들기만 · Q-N24 답 뒤 `app/backtest_v2.py`를 옮길 때 목록 글로)."""
    plain = _plain_texts()
    for r, ids in FROZEN.items():
        left = {plain[t] for t, _ in counts._strings(counts._parse(counts.APP / r)) if t in plain}
        assert left == ids, r


def test_server_texts_read_from_the_list() -> None:
    """서버가 보내는 글은 지금처럼 글로 보내고 출처만 목록(같은 글 · 몇 자리 견본)."""
    from app.run import live, paper
    from app.services import access, connect, data_admin, telegram

    assert live.TODO["huge"] == ("yellow", T.big_order_check) == ("yellow", "큰 주문 확인 · [{name}] [{amount}]")
    assert live.SCOPE["toss_down"] == T.scope_all_orders_and_watch
    assert paper.START_LINE == T.paper_start_line
    assert access.PLACES == {"server": T.place_server, "pc": T.place_pc}
    assert connect.STEP_NAMES["price"] == T.step_price and connect.FAILURES["shape"][2] == T.check_again_later
    assert data_admin.RUNNING_LIVE == T.delete_while_live and data_admin.RESTORE_LINE == T.restore_line
    assert telegram.EVENTS["precheck"]["title"] == "08:30 장 시작 전 점검"
    assert telegram.msg_precheck(True, 3) == "장 시작 전 점검 · 통과 · 08:35 주문 3건"
    assert telegram.msg_precheck(False, 0) == "장 시작 전 점검 · 실패 · 오늘 주문 멈춤 · 앱에서 보기"
    assert telegram.msg_fills(2, live=False) == "모의 · 체결 2건 · 앱에서 보기"
    assert telegram.msg_order_failed(1) == "실전 · 주문 실패 1건 · 앱에서 보기"
    assert telegram.msg_check_done(4) == "확인 끝 · 내일 주문 4건"
