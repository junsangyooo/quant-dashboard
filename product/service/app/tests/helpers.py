"""시험 도우미: 옛 일곱 칸 본문(얼린 것)과 그것을 DB에 직접 넣기.

P1-03 전에는 `app.strategy`(지운 MVP 모듈)의 `PIECES`로 본문을 만들고 MVP 라우트 `/api/strategies`로 넣었어요. 지금은
P1-01a가 얼린 `tests/baseline/frozen/v1_fixtures.json`의 `legacy` 행(그때 `legacy(template, name)`이 만든 본문 그대로 ·
`test_v1_legacy_helper_matches_frozen`이 같음을 확인했음)을 돌려주고, 본문은 `versions` 표에 직접 넣어요(읽을 때 v3로 바뀌는
길은 그대로 `copytext.read_body`).
"""

from __future__ import annotations

import json
from typing import Any

from tests.baseline import replay


def legacy(template: str, name: str) -> dict[str, Any]:
    """옛 '템플릿' 빈 본문(일곱 칸 · 얼린 것). 숫자 없는 조건만 미리 놓여 있다 — 지금 앱은 이 모양을 읽을 때 그래프로 바꾼다."""
    for row in replay.load_v1_fixtures()["legacy"]:
        if (row["template"], row["name"]) == (template, name):
            return json.loads(json.dumps(row["body"]))  # 복사본(시험이 고쳐도 얼린 값은 그대로)
    raise KeyError(f"얼린 legacy 본문이 없어요: ({template!r}, {name!r})")


def store_v1_body(db: Any, body: dict[str, Any], *, now: str = "2025-06-02T08:00:00+00:00") -> int:
    """옛 본문을 전략 · 버전 1로 DB에 직접 넣고 전략 id를 돌려줘요(지운 MVP 라우트 `POST /api/strategies` 대신)."""
    text = json.dumps(body, ensure_ascii=False)
    with db.tx():
        sid = int(db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                         (body["name"], body.get("template") or "", None, now)))
        db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
               (sid, 1, text, 0, now, "slots"))
    return sid
