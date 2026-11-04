"""화면 기준선(P1-01c): `screens.mjs`(Node 24 + Playwright + `PW_CHROMIUM`)를 불러 PNG · 화면 글을 만들고 기록 꼴로 정리해요.

`tests/baseline/web/screens/` 아래에 남기는 것(본체 · 두 번 같아야 함):
- `<id>__<폭>.png`: 상태 × 폭(1440 · 390)의 화면 그림(무손실 PNG · 1440 편집기만 창 크기 · 나머지는 전체 페이지).
- `screens.json`: 화면 목록(상태 id · 묶음 · 이름 · 폭 · 파일 · PNG 크기 · 그림 짝 `frame`(`design/frames/`의 파일 이름 ·
  있는지) · 빠진 화면의 까닭) · 지울 화면 목록(P1-01a 8-4 · 찍히지 않는 것) · 브라우저 판.
- `screen_texts.json`: 화면마다 보이는 글 전부(`document.body.innerText` · DOM 순서)와 역할 트리(aria snapshot).
- 대조(`compare.py`): PNG는 sha256이 같으면 0% · 다르면 `screens.mjs diff`(브라우저 canvas · 같은 자리 RGBA가 다른 픽셀 /
  큰 쪽 면적 · 크기가 다르면 빈 자리는 다른 픽셀)로 픽셀 차 %를 재고 **0.5%를 넘으면 실패**. 화면 글은 같아야 해요.
- 바깥 요청: 찍을 때 서버 밖 요청은 모두 막고 세요(`screens.json`의 `outbound_requests` · 0이어야 · 1건이라도 있으면 찍기 실패).
- node는 새 프로세스 묶음으로 돌리고(20분 timeout) 끝낼 때 묶음 전체를 끝내요(서버 · 브라우저 고아 0).

기록에는 절대 경로 · 시각이 들어가지 않아요(화면 글에 `/home/` · `/tmp/` 같은 경로가 섞이면 실패해요).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2]
SERVICE = APP.parent
FRAMES = SERVICE / "design" / "frames"
MJS = Path(__file__).resolve().parent / "screens.mjs"
PIXEL_THRESHOLD_PCT = 0.5
ABS_PATH = re.compile(r"(?:/home/|/tmp/|/private/|/Users/|[A-Z]:\\)")

# P1-01a 8-4 · P1-03의 웹 지울 목록 가운데 '화면'(라우트 · 부품)으로 닿을 수 있었던 것 → 찍히지 않으니 표시만
DELETED_SCREENS = [
    {"what": "screens/LoadError.tsx", "why": "화면에서 닿지 않는 부품(라우트 없음) · P1-03에서 지움"},
    {"what": "components/graph/GraphView.tsx · PathsPanel.tsx", "why": "옛 그래프 편집기 부품 · 화면에서 닿지 않음 · P1-03에서 지움"},
    {"what": "components/Badges · Chips · Dots · StageIcon · Text · Toast", "why": "화면에서 닿지 않는 부품 · P1-03에서 지움"},
]


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"PNG가 아니에요: {path.name}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


NODE_TIMEOUT_S = 20 * 60


def _node(args: list[str], *, cwd: Path = APP, timeout: float = NODE_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    """node를 새 세션(프로세스 묶음)으로 돌려요. 시간이 넘거나 우리가 죽으면 묶음 전체(node · 서버 · 브라우저)를
    SIGTERM → SIGKILL로 끝내 고아가 남지 않게 해요(P1-02 `check.sh`가 쓰는 길)."""
    proc = subprocess.Popen(["node", str(MJS), *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = proc.communicate()
        raise SystemExit(f"screens.mjs가 {timeout:.0f}초 안에 끝나지 않아 묶음을 끝냈어요:\n{err[-2000:]}")
    finally:
        if proc.poll() is None:
            _kill_group(proc)


def _kill_group(proc: subprocess.Popen[str]) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def list_states() -> list[dict[str, Any]]:
    p = _node(["list"])
    if p.returncode != 0:
        raise SystemExit(f"screens.mjs list 실패:\n{p.stderr[-2000:]}")
    return json.loads(p.stdout)


def capture(out: Path, *, only: str | None = None, quiet: bool = True) -> dict[str, Any]:
    """PNG · 화면 글을 `out/screens/`에 만들고 `screens.json` · `screen_texts.json`을 적어요. 두 번 같아요."""
    from tests.baseline.clock import FIXED_NOW_EPOCH_MS

    if not os.environ.get("PW_CHROMIUM") and not Path("/opt/pw-browsers/chromium").exists():
        raise SystemExit("화면 찍기 브라우저가 없어요: 환경 변수 PW_CHROMIUM이 비어 있고 /opt/pw-browsers/chromium도 없어요"
                         "(브라우저는 내려받지 않아요 · DEVELOPING 4절)")
    shots = out / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="quant-baseline-shots-") as d:
        args = ["capture", "--out", d, "--python", sys.executable, "--now-ms", str(FIXED_NOW_EPOCH_MS)]
        if only:
            args += ["--only", only]
        if quiet:
            args.append("--quiet")
        p = _node(args)
        if p.returncode != 0:
            raise SystemExit(f"screens.mjs capture 실패(exit {p.returncode}):\n{p.stderr[-3000:]}")
        raw = json.loads((Path(d) / "screens_raw.json").read_text(encoding="utf-8"))
        for rec in raw["records"]:
            if rec.get("png"):
                (shots / rec["png"]).write_bytes((Path(d) / rec["png"]).read_bytes())
    return write_records(shots, raw)


def write_records(shots: Path, raw: dict[str, Any]) -> dict[str, Any]:
    states = list_states()
    by_id = {s["id"]: s for s in states}
    screens: list[dict[str, Any]] = []
    texts: dict[str, Any] = {}
    leaks = []
    for rec in raw["records"]:
        meta = by_id[rec["id"]]
        frame = rec.get("frame")
        row: dict[str, Any] = {
            "id": rec["id"], "group": rec["group"], "name": rec["name"], "width": rec["width"],
            "path": meta["path"], "frame": frame, "frame_exists": bool(frame) and (FRAMES / frame).exists(),
        }
        row["outbound_requests"] = len(rec.get("outbound") or [])
        if rec.get("skipped"):
            row["skipped"] = rec["skipped"]
            row["png"] = None
        else:
            png = shots / rec["png"]
            w, h = png_size(png)
            # 전체 페이지 그림이 창(폭 × 배율)보다 넓으면 그 화면은 가로로 넘쳐요(지금 동작 · 기록만 · 390의 표 · 편집기 보기)
            row.update({"png": rec["png"], "png_width": w, "png_height": h, "scale": rec["scale"],
                        "bytes": png.stat().st_size, "sha256": sha256(png),
                        "overflow_x": w > rec["width"] * rec["scale"]})
            texts[rec["id"] + "__" + str(rec["width"])] = {"text": rec["text"], "aria": rec["aria"]}
            for kind in ("text", "aria"):
                if ABS_PATH.search(rec[kind]):
                    leaks.append(f"{rec['id']} {rec['width']} {kind}")
        screens.append(row)
    if leaks:
        raise SystemExit("화면 글에 절대 경로가 섞였어요(두 번 같음이 깨져요): " + ", ".join(leaks))
    screens.sort(key=lambda r: (r["id"], r["width"]))
    index = {
        "browser": raw["browser"],
        "widths": [1440, 390],
        "pixel_threshold_pct": PIXEL_THRESHOLD_PCT,
        "summary": {
            "states": len(states), "screens": len(screens), "captured": sum(1 for r in screens if r.get("png")),
            "skipped": sum(1 for r in screens if not r.get("png")),
            "with_frame": sum(1 for r in screens if r["frame"]),
            "frames_missing_file": sum(1 for r in screens if r["frame"] and not r["frame_exists"]),
            "overflow_x": sum(1 for r in screens if r.get("overflow_x")),
            "outbound_requests": sum(r["outbound_requests"] for r in screens),  # 0이어야(막힌 요청도 세요)
            "bytes": sum(r.get("bytes", 0) for r in screens),
        },
        "states": [{k: s[k] for k in ("id", "group", "index", "name", "frames", "path", "only1440")} for s in states],
        "screens": screens,
        "deleted_screens": DELETED_SCREENS,
    }
    (shots / "screens.json").write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                        encoding="utf-8")
    (shots / "screen_texts.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                             encoding="utf-8")
    return index


def pixel_diff(pairs: list[tuple[str, Path, Path]]) -> dict[str, dict[str, Any]]:
    """[(id, a.png, b.png)] → {id: {percent, a: [w, h], b: [w, h], changed, total}}. sha256이 같으면 브라우저 없이 0%."""
    out: dict[str, dict[str, Any]] = {}
    todo = []
    for id_, a, b in pairs:
        if a.exists() and b.exists() and sha256(a) == sha256(b):
            w, h = png_size(a)
            out[id_] = {"percent": 0.0, "a": [w, h], "b": [w, h], "changed": 0, "total": w * h, "identical": True}
        else:
            todo.append({"id": id_, "a": str(a), "b": str(b)})
    if todo:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(todo, f)
            name = f.name
        try:
            p = _node(["diff", name])
        finally:
            os.unlink(name)
        if p.returncode != 0:
            raise SystemExit(f"screens.mjs diff 실패(브라우저가 필요해요):\n{p.stderr[-2000:]}")
        for r in json.loads(p.stdout):
            out[r.pop("id")] = {**r, "identical": False}
    return out


def compare(base: Path, new: Path, diff: Callable[..., dict[str, dict[str, Any]]] = pixel_diff,
            ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """기준선 화면 폴더 ↔ 새로 찍은 폴더 → (차이 목록, 알림 목록, 화면별 표). `diff`는 시험에서 바꿔 끼울 수 있어요."""
    b = json.loads((base / "screens.json").read_text(encoding="utf-8"))
    n = json.loads((new / "screens.json").read_text(encoding="utf-8"))
    bt = json.loads((base / "screen_texts.json").read_text(encoding="utf-8"))
    nt = json.loads((new / "screen_texts.json").read_text(encoding="utf-8"))
    problems, notes, rows = [], [], []
    if b["browser"] != n["browser"]:
        notes.append(f"브라우저 판이 다름(QUALITY T8 · 이 비교는 실패로 치지 않음): {b['browser']} → {n['browser']}")
    n_screens = {(r["id"], r["width"]): r for r in n["screens"]}
    pairs = []
    for r in b["screens"]:
        key = (r["id"], r["width"])
        got = n_screens.get(key)
        if got is None:
            problems.append(f"화면이 사라짐: {r['id']} {r['width']}")
            continue
        if not r.get("png"):
            if got.get("png"):
                notes.append(f"기준선에서 건너뛴 화면이 새로 찍힘: {r['id']} {r['width']}")
            continue
        if not got.get("png"):
            problems.append(f"화면을 찍지 못함: {r['id']} {r['width']} · {got.get('skipped')}")
            continue
        pairs.append((f"{r['id']}__{r['width']}", base / r["png"], new / got["png"]))
    diffs = diff(pairs) if pairs else {}
    for id_, a, _b in pairs:
        d = diffs[id_]
        same_text = bt[id_]["text"] == nt.get(id_, {}).get("text")
        same_aria = bt[id_]["aria"] == nt.get(id_, {}).get("aria")
        rows.append({"screen": id_, "pixel_pct": d["percent"], "pixels": d.get("changed", 0),
                     "size": f"{d['a'][0]}×{d['a'][1]} → {d['b'][0]}×{d['b'][1]}", "text_same": same_text, "aria_same": same_aria})
        if d["percent"] > PIXEL_THRESHOLD_PCT:
            problems.append(f"화면 그림 차 {d['percent']}% > {PIXEL_THRESHOLD_PCT}%: {id_} ({rows[-1]['size']})")
        elif d.get("changed", 0) > 0:  # %가 0.000으로 반올림되는 몇 픽셀 차도 알림으로 남겨요(editor-05의 5픽셀 흔들림 같은 것)
            notes.append(f"화면 그림 차 {d['percent']}%({d['changed']}픽셀 · 문턱 안): {id_}")
        if not same_text:
            problems.append(f"화면 글 다름: {id_}")
        if not same_aria:
            problems.append(f"역할 트리 다름: {id_}")
    return problems, notes, rows


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "web"))
    ap.add_argument("--only", default=None, help="묶음[:번호] (예: settings:0)")
    a = ap.parse_args()
    idx = capture(Path(a.out), only=a.only, quiet=False)
    print(json.dumps(idx["summary"], ensure_ascii=False))
