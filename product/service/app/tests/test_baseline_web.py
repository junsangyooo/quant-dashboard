"""P1-01c 화면 · 웹 숫자 기준선 시험(`tests/baseline/web/`의 기록과 셈 함수).

1부: 셈 규칙(`webcounts.py` · `webchecks.py` · `screens.py`)과 화면 대조(`screens.compare` · 가짜 diff)가 문서대로인지 —
브라우저 없이 돌아요.
2부: 저장된 기준선 기록이 자기모순 없이 있는지(화면 목록 · PNG · 화면 글 · 금지어 0 · 바깥 요청 0 · 절대 경로 0 · 기록이
없으면 실패 · 커밋돼 있어야 해요).
3부: 픽셀 차 셈(Node 24 + `PW_CHROMIUM` 브라우저가 있을 때만 · 없으면 건너뜀).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.baseline import screens, webchecks, webcounts

APP = Path(__file__).resolve().parent.parent
WEB_BASE = APP / "tests" / "baseline" / "web"
SCREENS = WEB_BASE / "screens"

# P1-03b 보고(`tests/baseline/reports/P1-03b.md`) 5절 표의 '지운 뒤' 열(웹 숫자 · jscpd · 줄 · 파일 수는 빼고).
# 지운 코드 때문에 기준선 기록(`web/web_counts.json` · 지우기 전 증거 · 그대로 둠)과 등식이 성립할 수 없는 두 시험이
# 이 값과 '줄어들기만(≤)'으로 견줘요(Q-N21 답 (가) · 여유 없음 · 토큰 수와 참/거짓은 같음).
AFTER_P1_03B: dict[str, int | bool] = {
    "boundary_violations": 33,
    "feature_pairs": 5, "feature_to_shell": 15, "shell_to_api": 1, "lib_to_copy": 1, "lib_charts_cycle": True,
    "same_css_groups": 22, "same_css_groups_without_block_editor": 19,
    "raw_token_uses": 447, "raw_token_uses_without_block_editor": 264,
    "px_literals": 9, "px_literals_without_block_editor": 1,
    "custom_vars": 37, "custom_vars_without_block_editor": 21,
    "tokens_export": 223, "tokens_json": 180, "tokens_css": 180, "tokens_unused_export_only": 43,
    "tokens_value_mismatch": 0, "tokens_alias_mismatch": 0,
    "same_text_web": 20, "same_text_dist": 4, "same_text_server_web": 28,
}


def _node24() -> bool:
    try:
        return subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.startswith("v24.")
    except OSError:
        return False


def _browser() -> bool:
    return bool(os.environ.get("PW_CHROMIUM")) or Path("/opt/pw-browsers/chromium").exists()


# ═══ 1부 · 셈 규칙 ══════════════════════════════════════════════════════════


def test_layer_of_maps_current_folders_to_architecture_layers() -> None:
    assert webcounts.layer_of("src/screens/Live/LiveScreens.tsx") == ("features", "Live")
    assert webcounts.layer_of("src/screens/LoadError.tsx") == ("features", "LoadError")
    assert webcounts.layer_of("src/components/Header.tsx") == ("ds", None)
    assert webcounts.layer_of("src/charts/LineChart.tsx") == ("ds", None)
    assert webcounts.layer_of("src/copy.ts") == ("copy", None)
    assert webcounts.layer_of("src/copy/live.ts") == ("copy", None)
    assert webcounts.layer_of("src/routes.tsx") == ("shell", None)
    assert webcounts.layer_of("src/main.tsx") == ("assembly", None)
    assert webcounts.layer_of("src/graph/rules.ts") == ("graph", None)


def test_boundary_violations_match_the_p1_13_line() -> None:
    """P1-13 줄: 기능끼리 5쌍 · 기능 → shell 15곳(지운 LoadError 1은 P1-03b 뒤 빠짐) · shell → api · lib → copy · lib ↔ charts 순환."""
    bd = webcounts.boundary_violations()
    g = bd["groups"]
    assert g["feature_to_feature_pairs"] == ["Live → Setup", "Settings → Auth", "Settings → Setup", "Setup → Auth",
                                            "StrategiesV2 → BlockEditor"]
    kept_to_shell = [e for e in bd["edges"] if e["from_layer"] == "features" and e["to_layer"] == "shell" and e["kept"]]
    # 지운 뒤 값(P1-03b 5절) 이하 · 줄어들기만(Q-N21 답 (가))
    assert len(kept_to_shell) == 15 and g["feature_to_shell_places"] <= AFTER_P1_03B["feature_to_shell"]
    assert g["shell_to_api_places"] == 1
    assert g["lib_to_copy_places"] <= AFTER_P1_03B["lib_to_copy"]  # format.ts(지운 money.ts 몫 1은 P1-03b 뒤 빠짐)
    assert g["lib_charts_cycle"] is True
    assert bd["unresolved"] == []
    assert all("web/" not in e["from"] and not e["from"].startswith("/") for e in bd["edges"])


def test_import_regex_sees_static_export_from_and_dynamic(tmp_path: Path) -> None:
    f = tmp_path / "x.tsx"
    f.write_text("import a from './a';\nimport type { B } from './b';\nexport { c } from './c';\nimport './d.css';\n"
                 "// import z from './z'\nconst e = () => import('./e');\nimport * as f from \"./f\";\n", encoding="utf-8")
    got = [(spec, dyn) for spec, _line, dyn in webcounts.imports_of(f)]
    assert got == [("./a", False), ("./b", False), ("./c", False), ("./d.css", False), ("./e", True), ("./f", False)]


def test_css_rules_parser_splits_media_and_skips_font_face() -> None:
    css = (".a { color: red; gap: 1px; display: flex; }\n@media (min-width: 1px) { .b { display: flex; gap: 1px; color: red; } }\n"
           "@font-face { font-family: x; src: url(x); font-weight: 1 2; }\n.c { color: red; }\n/* .d { a: 1; b: 2; c: 3 } */")
    rules = webcounts.css_rules(css, "f.css")
    assert [r["selector"] for r in rules] == [".a", "@media (min-width: 1px) .b", ".c"]
    assert rules[0]["decls"] == rules[1]["decls"] == ["color:red", "display:flex", "gap:1px"]
    assert rules[0]["line"] == 1 and rules[1]["line"] == 2 and rules[2]["line"] == 4


def test_same_text_rule_is_the_server_rule() -> None:
    """P1-01b `counts.same_text`와 같은 규칙: 길이 8자 이상 + 한글 하나 이상."""
    assert webcounts._eligible("요청 형식이 맞지 않아요")
    assert not webcounts._eligible("맞지 않아요")  # 7자
    assert not webcounts._eligible("no hangul here at all")
    assert webcounts._eligible("DART 응답 1")  # 8자 · 한글 포함
    code = "const a = '조각 하나 둘 셋 넷';\n// '주석은 안 세요 하나 둘'\nconst b = <p>칸 하나 둘 셋 넷 다섯</p>;\nconst u = 'https://x';"
    assert [t for t, _ in webcounts.screen_strings(code)] == ["조각 하나 둘 셋 넷", "https://x", "칸 하나 둘 셋 넷 다섯"]


def test_px_literal_and_raw_token_patterns() -> None:
    assert webcounts.POS_PROPS.match("top") and webcounts.POS_PROPS.match("border-top-left-radius")
    assert webcounts.POS_PROPS.match("inset-inline-start") and not webcounts.POS_PROPS.match("margin-top")
    assert webcounts.PX_LITERAL.search("-7px") and webcounts.PX_LITERAL.search("calc(100% - 8px)")
    assert not webcounts.PX_LITERAL.search("0") and not webcounts.PX_LITERAL.search("var(--space-8)")
    assert webcounts.TSX_POS.search("style={{ left: 152, top: 156 }}")
    assert webcounts.TSX_POS.search("borderRadius: '8px'") and not webcounts.TSX_POS.search("top: 100%")
    assert webcounts.css_var("type/heading-1/line-height") == "--type-heading-1-line-height"


def test_token_crosscheck_export_json_css() -> None:
    """P1-12 줄: Figma 3묶음 223 ↔ tokens.json 180(쓰는 것) ↔ tokens.css 180 · 안 쓰는 43개 · 값 · 별칭 어긋남 0."""
    tk = webcounts.token_crosscheck()
    assert tk["export_count"] == 223 and tk["export_by_layer"] == {"primitive": 70, "semantic": 113, "component": 40}
    assert tk["json_count"] == 180 and tk["json_by_layer"] == {"primitive": 66, "semantic": 78, "component": 36}
    assert tk["css_count"] == 180
    assert tk["used_in_json"] == 180 and tk["unused_export_only"] == 43 and len(tk["unused_export_only_names"]) == 43
    assert tk["json_not_in_export"] == [] and tk["css_not_in_json"] == [] and tk["json_not_in_css"] == []
    assert tk["value_mismatch"] == [] and tk["alias_mismatch"] == [] and tk["layer_mismatch"] == []


def test_figma_value_conversion() -> None:
    assert webcounts._figma_value({"r": 1, "g": 1, "b": 1, "a": 1}, "COLOR") == "#FFFFFF"
    assert webcounts._figma_value({"r": 0.098, "g": 0.1216, "b": 0.1569, "a": 0.5}, "COLOR") == "#191F2880"
    assert webcounts._figma_value({"type": "VARIABLE_ALIAS", "ref": "primitive/color/neutral/1"}, "COLOR") == {"alias": "color/neutral/1"}
    assert webcounts._figma_value("Pretendard Variable", "STRING") == "Pretendard"
    assert webcounts._figma_value(15, "FLOAT") == 15


def test_deleted_web_list_is_p1_01a_8_4() -> None:
    assert len(webcounts.DELETED_WEB) == 32
    assert sum(1 for d in webcounts.DELETED_WEB if d.startswith("src/") and d != "src/api/mvp.ts") == 23
    missing = [d for d in webcounts.DELETED_WEB if not (webcounts.WEB / d).exists()]
    assert missing == list(webcounts.DELETED_WEB)  # 지운 뒤(P1-03b)에는 모두 없어요(P1-01c가 적어 둔 뒤집기)


def test_forbidden_words_rule_matches_words_test_examples() -> None:
    """`web/tests/words.test.ts`의 예시와 같은 판정(같은 JSON 규칙)."""
    from tests.words_rules import hits

    r = webchecks.rules()
    words = lambda t: sorted(h.split(": …")[0] for h in hits(t, r))  # noqa: E731
    assert words("조각 추가 · 블록 · 전략 코드 복사 · 값 넣기") == sorted(["넣기", "블록", "전략 코드", "조각"])
    assert words("빈칸 4개 · 붙여 넣기 · 투자 판단과 손익 · 숫자 칸 · 입력 칸 · 백테스트 · 시험 보내기 · 리포트") == []
    assert words("11/3 16:30 기준") == ["10/29 16:30 기준"]
    assert words("실전 운용이나 모의투자 기록이 있는 전략은 삭제할 수 없어요") == []


def test_png_size_reads_ihdr(tmp_path: Path) -> None:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 3, 2, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")
    p = tmp_path / "a.png"
    p.write_bytes(png)
    assert screens.png_size(p) == (3, 2)
    (tmp_path / "b.png").write_bytes(b"not png")
    with pytest.raises(ValueError):
        screens.png_size(tmp_path / "b.png")


def _tiny_png(w: int = 2, h: int = 2, fill: int = 0) -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes([fill] * 3) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _fake_screens_dir(root: Path, *, text: str = "자산\n운용 중", fill: int = 0, drop: bool = False) -> Path:
    """작은 가짜 화면 폴더: 화면 하나(`s-00__1440`) · PNG 2×2 · 글 JSON."""
    d = root
    d.mkdir(parents=True, exist_ok=True)
    rows = [] if drop else [{"id": "s-00", "width": 1440, "png": "s-00__1440.png"}]
    (d / "screens.json").write_text(json.dumps({"browser": "x", "screens": rows}), encoding="utf-8")
    (d / "screen_texts.json").write_text(json.dumps({"s-00__1440": {"text": text, "aria": "- main"}}), encoding="utf-8")
    if not drop:
        (d / "s-00__1440.png").write_bytes(_tiny_png(fill=fill))
    return d


def test_screens_compare_passes_when_png_and_text_are_the_same(tmp_path: Path) -> None:
    base = _fake_screens_dir(tmp_path / "base")
    new = _fake_screens_dir(tmp_path / "new")
    problems, notes, rows = screens.compare(base, new)  # 같은 바이트 → 브라우저 없이 0%
    assert problems == [] and notes == []
    assert rows == [{"screen": "s-00__1440", "pixel_pct": 0.0, "pixels": 0, "size": "2×2 → 2×2", "text_same": True, "aria_same": True}]


def test_screens_compare_fails_over_the_pixel_threshold_and_notes_under_it(tmp_path: Path) -> None:
    base = _fake_screens_dir(tmp_path / "base", fill=0)
    new = _fake_screens_dir(tmp_path / "new", fill=255)  # 바이트가 달라 diff를 불러요 · 브라우저 대신 가짜 diff
    fake = lambda pairs, pct=[1.25]: {id_: {"percent": pct[0], "a": [2, 2], "b": [2, 2], "changed": 1, "total": 4} for id_, _a, _b in pairs}  # noqa: E731
    problems, notes, rows = screens.compare(base, new, diff=fake)
    assert problems == ["화면 그림 차 1.25% > 0.5%: s-00__1440 (2×2 → 2×2)"] and notes == []
    problems, notes, rows = screens.compare(base, new, diff=lambda pairs: fake(pairs, [0.3]))
    assert problems == [] and notes == ["화면 그림 차 0.3%(1픽셀 · 문턱 안): s-00__1440"] and rows[0]["pixel_pct"] == 0.3
    problems, notes, _rows = screens.compare(base, new, diff=lambda pairs: fake(pairs, [0.0]))  # 몇 픽셀이라 0.000%로 반올림
    assert problems == [] and notes == ["화면 그림 차 0.0%(1픽셀 · 문턱 안): s-00__1440"]


def test_screens_compare_fails_on_text_change_and_missing_screen(tmp_path: Path) -> None:
    base = _fake_screens_dir(tmp_path / "base")
    changed = _fake_screens_dir(tmp_path / "changed", text="자산\n운용 끝")
    problems, _notes, rows = screens.compare(base, changed)
    assert problems == ["화면 글 다름: s-00__1440"] and rows[0]["text_same"] is False and rows[0]["pixel_pct"] == 0.0
    gone = _fake_screens_dir(tmp_path / "gone", drop=True)
    problems, _notes, rows = screens.compare(base, gone)
    assert problems == ["화면이 사라짐: s-00 1440"] and rows == []


def test_pixel_diff_fast_path_without_browser(tmp_path: Path) -> None:
    src = sorted(SCREENS.glob("*__1440.png"))
    assert src, "기준선 화면이 커밋돼 있어야 해요"
    a = tmp_path / "a.png"
    shutil.copy(src[0], a)
    d = screens.pixel_diff([("same", src[0], a)])
    assert d["same"]["percent"] == 0.0 and d["same"]["identical"] is True


# ═══ 2부 · 저장된 기준선 ═════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def index() -> dict:  # type: ignore[type-arg]
    assert (SCREENS / "screens.json").exists(), "기준선 화면 기록이 커밋돼 있어야 해요"
    return json.loads((SCREENS / "screens.json").read_text(encoding="utf-8"))


def test_screen_index_has_every_state_at_both_widths(index: dict) -> None:  # type: ignore[type-arg]
    s = index["summary"]
    assert index["widths"] == [1440, 390] and index["pixel_threshold_pct"] == 0.5
    assert s["states"] == 36 and s["screens"] == 72 and s["captured"] + s["skipped"] == 72
    assert s["frames_missing_file"] == 0 and s["outbound_requests"] == 0
    assert all(r["outbound_requests"] == 0 for r in index["screens"])
    keys = {(r["id"], r["width"]) for r in index["screens"]}
    assert keys == {(st["id"], w) for st in index["states"] for w in (1440, 390)}
    overflow = []
    for r in index["screens"]:
        if r.get("png"):
            # 전체 페이지 그림은 창 폭 × 배율이거나, 가로로 넘치는 화면이면 더 넓어요(지금 동작 · `overflow_x`로 표시)
            assert r["png_width"] >= r["width"] * r["scale"]
            assert r["overflow_x"] == (r["png_width"] > r["width"] * r["scale"])
            if r["overflow_x"]:
                overflow.append(r["id"])
            assert (SCREENS / r["png"]).exists() and screens.sha256(SCREENS / r["png"]) == r["sha256"]
        else:
            assert r["width"] == 390 and r["skipped"]  # 390 편집기 '보기만'의 동작 화면
    assert len(overflow) == s["overflow_x"] == 5 and all("__" not in o for o in overflow)
    assert index["states"][0]["id"] == "editor-00-기본(문제_없음)"
    assert {d["what"] for d in index["deleted_screens"]} >= {"screens/LoadError.tsx"}


def test_screen_texts_cover_captured_screens_without_paths(index: dict) -> None:  # type: ignore[type-arg]
    texts = json.loads((SCREENS / "screen_texts.json").read_text(encoding="utf-8"))
    captured = {f"{r['id']}__{r['width']}" for r in index["screens"] if r.get("png")}
    assert set(texts) == captured
    for key, t in texts.items():
        assert t["text"].strip() and t["aria"].startswith("- "), key
        assert not screens.ABS_PATH.search(t["text"]) and not screens.ABS_PATH.search(t["aria"]), key
    # 고정 시각 · 씨앗이 화면에 닿은 자리
    assert "2PAJ-B9JH-YDYB-A7DH" in texts["settings-01-V2-02_기본__1440"]["text"]
    assert "127.0.0.1:8797" in texts["settings-10-V2-55_앱_정보-기본__1440"]["text"]


def test_forbidden_words_record_is_zero_and_matches_recount() -> None:
    p = WEB_BASE / "forbidden_words.json"
    assert p.exists(), "기준선 금지어 기록이 커밋돼 있어야 해요"
    rec = json.loads(p.read_text(encoding="utf-8"))
    assert rec["dist_count"] == 0 and rec["screen_count"] == 0 and rec["screens"] == 67
    now = webchecks.forbidden_words(SCREENS / "screen_texts.json")
    assert now["screen_hits"] == rec["screen_hits"] == []


def test_web_counts_record_matches_recount_without_jscpd() -> None:
    p = WEB_BASE / "web_counts.json"
    assert p.exists(), "기준선 웹 숫자 기록이 커밋돼 있어야 해요"
    rec = json.loads(p.read_text(encoding="utf-8"))["summary"]
    now = webcounts.run_all(with_jscpd=False)["summary"]
    # P1-03b가 지울 파일을 지운 뒤라 기록(지우기 전 표)과 같을 수 없어요. 기록은 그대로 두고(P1-01c) ARCHITECTURE 6절의
    # '줄어들기만'으로 봐요: 어긋남 수는 지운 뒤 값(`AFTER_P1_03B` · P1-03b 5절) 이하 · 토큰 수는 같음 · 남는/지울 나눔은
    # 모두 남는 쪽(Q-N21 답 (가)). 기록의 항목마다 같은 이름의 지운 뒤 값이 있어요(없으면 KeyError).
    assert now["files_deleted"] == 0 and now["lines_deleted"] == 0
    assert now["files_kept"] == now["files"] and now["lines_kept"] == now["lines"]
    assert now["boundary_violations_kept"] == now["boundary_violations"]
    for k, v in rec.items():
        if k.startswith("jscpd") or k.endswith(("_kept", "_deleted")) or k in ("files", "lines"):
            continue
        after = AFTER_P1_03B[k]
        if isinstance(v, bool) or k in ("tokens_export", "tokens_json", "tokens_css"):
            assert now[k] == after == v, k
        else:
            assert after <= v and now[k] <= after, (k, v, after, now[k])
    assert rec["tokens_unused_export_only"] == 43 and rec["feature_pairs"] == 5


# ═══ 3부 · 브라우저가 있을 때 ═══════════════════════════════════════════════


@pytest.mark.skipif(not (_node24() and _browser()), reason="Node 24 + PW_CHROMIUM 브라우저가 필요해요")
def test_pixel_diff_counts_changed_pixels_with_the_browser() -> None:
    a = SCREENS / "settings-00-V2-01_기본__1440.png"
    b = SCREENS / "settings-02-V2-03_기본__1440.png"
    assert a.exists() and b.exists(), "기준선 화면이 커밋돼 있어야 해요"
    d = screens.pixel_diff([("x", a, b)])["x"]
    assert d["identical"] is False and d["percent"] > 0 and d["bbox"] and d["changed"] <= d["total"]
