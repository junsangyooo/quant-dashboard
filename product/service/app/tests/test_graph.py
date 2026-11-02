"""그래프 규칙(ENGINE-RULES R-G12) · 검사(문제 목록 · 매매 방식 · 경로) · 새 전략 · 예시 · 버전 API."""

from __future__ import annotations

import copy

import pytest

from app import graph as gr
from app import strategy as st
from tests.conftest import setup_owner


def _g(nodes: list[tuple[str, str]], edges: list[tuple[str, str]], **params: dict) -> dict:  # type: ignore[type-arg]
    return {
        "nodes": [{"id": i, "piece": p, "params": params.get(i, {}), "x": None, "y": None} for i, p in nodes],
        "edges": [{"from": a, "to": b} for a, b in edges],
    }


BASE = [("u", "manual_list"), ("s", "ma_cross_up"), ("f", "min_price"), ("k", "top_n"), ("b", "next_open"),
        ("x", "stop_loss"), ("y", "max_hold"), ("w", "equal"), ("r", "rebalance_every")]


def test_link_rules_follow_the_table() -> None:
    g = _g(BASE, [("u", "s"), ("s", "f"), ("f", "k"), ("k", "b"), ("b", "x"), ("w", "b")])
    ok = [("x", "y"), ("u", "f"), ("u", "k"), ("r", "b"), ("b", "y")]
    for a, b in ok:
        assert gr.edge_reason(g, a, b) is None, (a, b)
    bad = {
        ("s", "x"): gr.R_SELL,
        ("x", "b"): gr.R_SELL,
        ("k", "f"): gr.R_SELECT,
        ("s", "b"): gr.R_SELECT,  # ④가 있으면 ② · ③ → ⑤는 막는다
        ("b", "s"): gr.R_ENTRY,
        ("w", "s"): gr.R_WEIGHT,
        ("s", "w"): gr.R_WEIGHT,
        ("s", "u"): gr.R_UNIVERSE_IN,
        ("u", "s"): gr.R_DUP,
        ("f", "s"): gr.R_CYCLE,  # ② → ③ → ② 순환
        ("s", "s"): gr.R_CYCLE,
    }
    for (a, b), why in bad.items():
        assert gr.edge_reason(g, a, b) == why, (a, b)
    # ④가 없으면 ③ → ⑤ 가능, ③ → ②(이미 지나오지 않은 신호)도 가능
    g2 = _g([n for n in BASE if n[0] != "k"] + [("s2", "rsi_below")], [("u", "f")])
    assert gr.edge_reason(g2, "f", "b") is None
    assert gr.edge_reason(g2, "f", "s2") is None


def test_once_rules() -> None:
    g = _g(BASE, [])
    assert gr.add_reason(g, "manual_list") == "유니버스는 하나만 놓을 수 있어요"
    assert gr.add_reason(g, "next_open") == "매수 조건은 하나만 놓을 수 있어요"
    assert gr.add_reason(g, "top_n") == "종목 선정은 매수 바로 앞에 하나만 놓아요"
    assert gr.add_reason(g, "equal") == "동일 비중은 하나만 놓을 수 있어요"
    assert gr.add_reason(g, "rebalance_every") == "리밸런싱 주기 n거래일은 하나만 놓을 수 있어요"
    assert gr.add_reason(g, "ma_cross_up") is None  # 같은 조건을 여러 번 놓을 수 있다
    assert gr.add_reason(g, "stop_loss") is None
    many = _g([(f"n{i}", "min_price") for i in range(40)], [])
    assert gr.add_reason(many, "min_price") == "조건은 40개까지 놓을 수 있어요"


def test_path_limit_on_link() -> None:
    nodes = [("u", "manual_list"), ("b", "next_open")] + [(f"s{i}", "ma_cross_up") for i in range(5)] + [
        (f"f{i}", "min_price") for i in range(4)]
    edges = [("u", f"s{i}") for i in range(5)] + [(f"s{i}", f"f{j}") for i in range(5) for j in range(4)]
    edges += [(f"f{j}", "b") for j in range(4)]
    g = _g(nodes, edges)
    assert len(gr.entry_paths(g)) == 20
    g["nodes"].append({"id": "f9", "piece": "min_price", "params": {}, "x": None, "y": None})
    g["edges"].append({"from": "f9", "to": "b"})
    assert gr.edge_reason(g, "s0", "f9") == gr.R_MANY


def test_blank_canvas_problems_match_the_design() -> None:
    a = st.analyze(st.blank_body())
    assert a["mode"] == "event"
    assert a["counts"] == {"blank": 2, "required": 2}
    req = [p for p in a["problems"] if p["kind"] == "required"]
    assert [p["slot"] for p in req] == ["signal", "sell"]
    assert req[0]["short"] == "진입 경로 1에 신호가 없어요 · 신호 없이 연결하면 매일 모든 종목이 매수 후보가 돼요"
    assert req[0]["hint"] == "목록에서 신호 조건을 끌어 와 ①과 ④ 사이 선 위에 놓아 주세요"
    assert req[1]["short"] == "조건 충족 시 매매에는 매도 경로가 하나 이상 있어야 해요"
    blanks = [p for p in a["problems"] if p["kind"] == "blank"]
    assert blanks[0]["detail"] == "① 유니버스 · 종목 코드를 입력해 주세요"
    assert blanks[1]["detail"] == "④ 종목 선정 · 종목 수를 입력해 주세요"
    assert [p["nodes"] for p in a["entry"]] == [["u1", "k1", "b1"]] and a["sell"] == []


def test_range_loose_dead_messages() -> None:
    body = st.example_body("either")
    g = body["graph"]
    for n in g["nodes"]:
        if n["id"] == "s1":
            n["params"]["n"] = 300
        if n["id"] == "x2":
            n["params"]["n"] = None
    g["edges"] = [e for e in g["edges"] if e != {"from": "f1", "to": "k1"}]
    g["nodes"].append({"id": "p1", "piece": "min_price", "params": {"n": 5000}, "x": 673, "y": 320})
    a = st.analyze(body)
    assert a["counts"] == {"blank": 1, "range": 1, "loose": 1, "dead": 1}
    by = {p["kind"]: p for p in a["problems"]}
    assert by["range"]["title"] == "범위 밖 · 300일 최고가 돌파"
    assert by["range"]["detail"] == "② 신호 · 기간은 5~250일 사이로 입력해 주세요"
    assert by["blank"]["title"] == "빈칸 · 최대 보유 n거래일"
    assert by["blank"]["detail"] == "⑥ 매도 · 보유 기간을 입력해 주세요"
    assert by["loose"]["title"] == "연결 없음 · 주가 5,000원 이상"
    assert by["loose"]["detail"] == "③ 필터 · 선으로 연결해야 전략에 들어가요"
    assert by["dead"]["detail"] == "진입 경로 2 · ③ 거래대금 100억 원 이상 뒤를 ④ 신호 강도 상위 5종목에 연결해 주세요"
    assert [p["complete"] for p in a["entry"]] == [True, False]


def test_mode_from_rebalance_and_unusable_sell() -> None:
    body = st.example_body("trend")
    reb = next(n for n in body["graph"]["nodes"] if n["piece"] == "rebalance_every")
    assert st.analyze(body)["mode"] == "rank"
    reb["params"]["how"] = None
    a = st.analyze(body)
    assert a["mode"] is None and a["counts"] == {"blank": 1}
    assert a["problems"][0]["short"] == "리밸런싱 방식을 골라 주세요"
    reb["params"]["how"] = "target"
    a = st.analyze(body)
    assert a["mode"] == "target" and a["counts"] == {"unusable": 1}
    assert a["problems"][0]["detail"].startswith("⑥ 매도 · 목표 비중 리밸런싱에서는 ⑥ 매도 조건을 쓸 수 없어요")
    # 리밸런싱 주기를 지우면 조건 충족 시 매매(필요한 조건이 바뀐다)
    body["graph"]["nodes"] = [n for n in body["graph"]["nodes"] if n["piece"] != "rebalance_every"]
    body["graph"]["edges"] = [e for e in body["graph"]["edges"] if e["from"] != "w2"]
    a = st.analyze(body)
    assert a["mode"] == "event" and a["problems"] == []
    # 이어지지 않은 리밸런싱 주기는 방식을 정하지 않는다(연결 없음)
    body["graph"]["nodes"].append({"id": "r9", "piece": "rebalance_every", "params": {"n": 5, "how": "rank"}, "x": 0, "y": 0})
    a = st.analyze(body)
    assert a["mode"] == "event" and a["counts"] == {"loose": 1}


def test_select_added_later_marks_the_old_line() -> None:
    g = _g([("u", "manual_list"), ("s", "ma_cross_up"), ("b", "next_open"), ("x", "stop_loss"), ("w", "equal"),
            ("k", "top_n")], [("u", "s"), ("s", "b"), ("b", "x"), ("w", "b")])
    a = gr.analyze(g)
    rule = [p for p in a["problems"] if p["kind"] == "rule"]
    assert len(rule) == 1 and rule[0]["short"] == gr.R_SELECT


def test_chain_and_branch_paths() -> None:
    body = st.example_body("breakout")
    a = st.analyze(body)
    assert len(a["sell"]) == 3  # ⑤에서 갈래 셋
    g = body["graph"]
    g["edges"] = [e for e in g["edges"] if e["to"] != "x3"] + [{"from": "x1", "to": "x3"}]
    a = st.analyze(body)
    assert [p["nodes"] for p in a["sell"]] == [["b1", "x1", "x3"], ["b1", "x2"]]


def test_legacy_conversion_one_line() -> None:
    from tests.helpers import legacy

    old = legacy("rank", "x")
    g = gr.from_slots(old)
    pieces = [n["piece"] for n in g["nodes"]]
    assert pieces == ["manual_list", "top_n", "next_open", "equal", "rebalance_every"]
    assert g["nodes"][-1]["params"]["how"] == "rank"
    assert st.mode_of({"graph": g}) == "rank"


def test_normalize_cleans_values() -> None:
    body = st.example_body("breakout")
    body["graph"]["nodes"][0]["params"]["symbols"] = "005930.KS, 247540.kq 005930"
    body["graph"]["nodes"][1]["params"]["n"] = "1,000"
    body["graph"]["nodes"][2]["params"]["n"] = "abc"
    out = st.normalize(body)
    assert out["graph"]["nodes"][0]["params"]["symbols"] == ["005930", "247540"]
    assert out["graph"]["nodes"][1]["params"]["n"] == 1000
    assert any(p["short"].startswith("거래대금에 숫자를") for p in st.validate(out))
    with pytest.raises(st.FormatError):
        st.normalize({"graph": {"nodes": [{"id": "a b", "piece": "equal"}], "edges": []}})


# ── API ──────────────────────────────────────────────────────────────────────


def test_new_strategy_has_no_version_until_saved(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    assert app_client.get("/api/strategies").json()["strategies"] == []
    # 저장하지 않은 새 전략의 검사(sid=0)
    r = app_client.post("/api/strategies/0/check", json={"body": st.blank_body()})
    assert r.status_code == 200 and r.json()["analysis"]["counts"] == {"blank": 2, "required": 2}
    assert app_client.get("/api/strategies").json()["strategies"] == []
    # 처음 저장 = 버전 1
    r = app_client.post("/api/strategies", json={"body": st.example_body("breakout") | {"name": "대형주 돌파"}})
    assert r.status_code == 200 and r.json()["no"] == 1 and r.json()["problems"] == []
    sid = r.json()["id"]
    # 이름이 겹치면 ' (2)'
    r2 = app_client.post("/api/strategies", json={"body": st.example_body("breakout")})
    assert r2.json()["name"] == "대형주 돌파 (2)"
    r3 = app_client.post("/api/strategies", json={"body": st.example_body("breakout")})
    assert r3.json()["name"] == "대형주 돌파 (3)"
    got = app_client.get(f"/api/strategies/{sid}").json()
    assert got["mode_name"] == "조건 충족 시 매매" and got["analysis"]["problems"] == []
    assert len(got["analysis"]["sell"]) == 3 and got["summary"]["nodes"] == 9


def test_versions_via_api(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = app_client.post("/api/strategies", json={"body": st.blank_body("내 돌파")}).json()["id"]
    body = st.example_body("either") | {"name": "내 돌파"}
    r = app_client.post(f"/api/strategies/{sid}/versions", json={"body": body})
    assert r.status_code == 200 and r.json()["no"] == 2 and r.json()["problems"] == []
    assert [v["no"] for v in r.json()["versions"]] == [2, 1]
    bad = copy.deepcopy(body)
    bad["graph"]["nodes"][6]["params"]["pct"] = 99
    r = app_client.post(f"/api/strategies/{sid}/versions", json={"body": bad})
    assert r.json()["no"] == 3 and r.json()["problems"][0]["kind"] == "range"
    # 매매 방식이 바뀌어도 같은 전략의 새 버전이다(템플릿이 없다)
    r = app_client.post(f"/api/strategies/{sid}/versions", json={"body": st.example_body("trend") | {"name": "내 돌파"}})
    assert r.status_code == 200 and r.json()["no"] == 4
    lst = app_client.get("/api/strategies").json()
    assert lst["strategies"][0]["latest"]["no"] == 4 and lst["strategies"][0]["mode_name"] == "순위 교체 리밸런싱"
    assert lst["steps"]["strategies"] == 1


def test_examples_read_only_and_backtest_not_saved(app_client, fake_bars) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import make_bars, wave

    for k, sym in enumerate(st.BIG10[2:]):
        fake_bars.data[sym] = make_bars(wave(400, 50000 + 9000 * k, 4000, 25 + 3 * k, 0.0008))
    setup_owner(app_client)
    ex = app_client.get("/api/examples").json()["examples"]
    assert [e["name"] for e in ex] == ["대형주 돌파", "돌파 둘 중 하나", "대형주 동일 비중", "추세 상위 교체"]
    assert [(e["summary"]["nodes"], e["summary"]["entry"], e["summary"]["sell"]) for e in ex] == [
        (9, 1, 3), (9, 2, 2), (4, 1, 0), (7, 1, 1)]
    assert [e["summary"]["mode_name"] for e in ex] == [
        "조건 충족 시 매매", "조건 충족 시 매매", "목표 비중 리밸런싱", "순위 교체 리밸런싱"]
    assert all(e["analysis"]["problems"] == [] for e in ex)
    r = app_client.post("/api/backtest", json={"example": "either", "start": "2024-03-01", "end": "2025-05-30",
                                               "cash": 10_000_000})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["version"] is None and res["example"]["name"] == "돌파 둘 중 하나"
    # 결과는 남지 않는다: 전략도 버전도 생기지 않고, 시작하기 '백테스트' 단계도 그대로
    lst = app_client.get("/api/strategies").json()
    assert lst["strategies"] == [] and lst["steps"]["backtested"] is False
    assert app_client.post("/api/backtest", json={"example": "nope"}).status_code == 404


def test_particle_after_name_tail() -> None:
    from app.pieces import josa

    assert josa("(2)", "을/를") == "(2)를"
    assert josa("(3)", "을/를") == "(3)을"
    assert josa("(10)", "을/를") == "(10)을"
    assert josa("대형주 돌파 (2)", "이/가") == "대형주 돌파 (2)가"
    assert josa("대형주 돌파 (3)", "으로/로") == "대형주 돌파 (3)으로"
    assert josa("대형주 돌파 (7)", "으로/로") == "대형주 돌파 (7)로"
