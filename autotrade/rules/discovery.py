"""'3년 발굴': the AI rule (Vault 5-설계/파이프라인.md '3년 발굴', PHASE2.md).

AI picks a three-year flow and the companies in it every quarter (Opus), checks them every month
(Sonnet), reads the earnings filings (Haiku); the code checks the sell and buy conditions every
day. Every judgment is scored against the same market's index.

The screen draws the rule from this definition (D34): four lanes ('흐름') of the nine card kinds,
copied from the Figma 탐색 frames (17:5855 매일, 17:7193 실적 공시, 17:7808 매달 1일,
17:6432 분기 발굴; read 2026-10-09 through the figma-bridge plugin, read only). Titles are data
(the cards' names); the API fills each card's '지금' block and colours the edges by what ran.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from autotrade.rules.model import RuleDef

RULE_ID = "discovery_3y"

# Same-market index for scoring (T24 score.py) and the index ETF that holds sold money until the
# next buy ('판 돈은 같은 나라 지수 ETF에 둔다').
SCORE_BENCHMARK = {"KR": "069500.KS", "US": "SPY"}

_EXCEPTION = {"id": "exception", "type": "exception", "title": "다음 확인으로 미룸"}

LANES: list[dict[str, Any]] = [
    {
        "id": "daily",
        "label": {"kind": "daily", "time": "08:30"},
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "col": 0,
                "row": 0,
                "title": "매일 08:30",
                "subtitle": "한국 시간 · 평일",
            },
            {
                "id": "data",
                "type": "data",
                "col": 1,
                "row": 0,
                "title": "시세 · 새 공시 · 지표 표",
                "subtitle": "종가·환율 · DART·EDGAR",
            },
            {
                "id": "condition",
                "type": "condition",
                "col": 2,
                "row": 0,
                "title": "팔·살 조건에 걸렸나요?",
                "subtitle": "팔 조건 · 급락 · 관련 공시 · 살 값",
            },
            {
                "id": "ai",
                "type": "ai",
                "col": 0,
                "row": 1,
                "title": "근거가 깨졌나요?",
                "fields": [
                    {"key": "input", "value": "걸린 종목 자료 · 최근 공시"},
                    {"key": "ai", "value": "Sonnet · 두 번 묻기"},
                    {"key": "output", "value": "유지 · 약화 · 반증"},
                ],
            },
            {
                "id": "confirm",
                "type": "condition",
                "col": 1,
                "row": 1,
                "title": "둘 다 '반증'인가요?",
                "subtitle": "사는 쪽도 둘 다 '근거 있음'이면 삼",
            },
            {
                "id": "result",
                "type": "result",
                "col": 2,
                "row": 1,
                "title": "보유 유지",
                "subtitle": "팔 조건 밖 · 마지막 확인",
            },
            {
                "id": "action",
                "type": "action",
                "col": 1,
                "row": 2,
                "title": "매도 · 판 돈은 지수 ETF로",
            },
            {**_EXCEPTION, "col": 1, "row": 3},
        ],
        "edges": [
            {"from": "start", "to": "data"},
            {"from": "data", "to": "condition"},
            {"from": "condition", "to": "ai", "label": "yes"},
            {"from": "condition", "to": "result", "label": "no-keep"},
            {"from": "ai", "to": "confirm"},
            {"from": "confirm", "to": "result", "label": "no"},
            {"from": "confirm", "to": "action", "label": "yes"},
            {"from": "action", "to": "exception", "exception": True},
        ],
    },
    {
        "id": "earnings",
        "label": {"kind": "earnings"},
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "col": 0,
                "row": 0,
                "title": "실적 공시가 나오면",
                "subtitle": "DART · EDGAR · 매일 확인",
            },
            {
                "id": "ai",
                "type": "ai",
                "col": 1,
                "row": 0,
                "title": "실적 지표 뽑기",
                "fields": [
                    {"key": "input", "value": "공시 원문"},
                    {"key": "ai", "value": "Haiku"},
                    {"key": "output", "value": "지표 · 값 · 근거 문장"},
                ],
            },
            {
                "id": "data",
                "type": "data",
                "col": 2,
                "row": 0,
                "title": "지표 표",
                "subtitle": "종목 · 지표 · 값 · 기간 · 출처",
            },
            {
                "id": "result",
                "type": "result",
                "col": 0,
                "row": 1,
                "title": "매일 확인에서 대조",
                "subtitle": "팔 조건 · 계획 게이지에 반영",
            },
        ],
        "edges": [
            {"from": "start", "to": "ai"},
            {"from": "ai", "to": "data"},
            {"from": "data", "to": "result"},
        ],
    },
    {
        "id": "monthly",
        "label": {"kind": "monthly"},
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "col": 0,
                "row": 0,
                "title": "매달 1일",
                "subtitle": "전날 밤 · 보유 종목 전부",
            },
            {
                "id": "data",
                "type": "data",
                "col": 1,
                "row": 0,
                "title": "자료 꾸러미",
                "subtitle": "가격 · 재무 · 지표 표 · 최근 공시",
            },
            {
                "id": "ai",
                "type": "ai",
                "col": 2,
                "row": 0,
                "title": "유지 · 약화 · 반증",
                "fields": [
                    {"key": "input", "value": "종목마다 자료 꾸러미"},
                    {"key": "ai", "value": "Sonnet · 사고량 낮음"},
                    {"key": "output", "value": "판정 · 팔 조건 고쳐 쓰기"},
                ],
            },
            {
                "id": "result",
                "type": "result",
                "col": 0,
                "row": 1,
                "title": "반증이면 매일 흐름의 두 번 확인으로",
                "subtitle": "약화 두 달 연속도 같은 길",
            },
        ],
        "edges": [
            {"from": "start", "to": "data"},
            {"from": "data", "to": "ai"},
            {"from": "ai", "to": "result"},
        ],
    },
    {
        "id": "quarterly",
        "label": {"kind": "quarterly"},
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "col": 0,
                "row": 0,
                "title": "4·6·9·12월 1일",
                "subtitle": "실적 공시가 다 나온 뒤",
            },
            {
                "id": "data",
                "type": "data",
                "col": 1,
                "row": 0,
                "title": "거시 · 흐름 · 실적 · 값",
                "subtitle": "금리·환율·업종 흐름·후보 재무",
            },
            {
                "id": "ai",
                "type": "ai",
                "col": 2,
                "row": 0,
                "title": "흐름과 기업 고르기",
                "fields": [
                    {"key": "input", "value": "거시 · 흐름 · 후보 실적"},
                    {"key": "ai", "value": "Opus · 웹 검색"},
                    {"key": "output", "value": "종목 · 팔 조건 · 살 조건"},
                ],
            },
            {"id": "stock", "type": "stock", "col": 0, "row": 1, "title": "보유 · 후보"},
            {
                "id": "weight",
                "type": "weight",
                "col": 1,
                "row": 1,
                "title": "같은 금액",
                "subtitle": "확신으로 나누지 않음",
            },
            {
                "id": "condition",
                "type": "condition",
                "col": 2,
                "row": 1,
                "title": "살 값에 왔나요?",
                "subtitle": "후보마다 살 조건 · 매일 확인",
            },
            {
                "id": "action",
                "type": "action",
                "col": 0,
                "row": 2,
                "title": "새 종목 매수",
                "subtitle": "두 번 확인해 둘 다 '근거 있음'이면",
            },
            {
                "id": "result",
                "type": "result",
                "col": 2,
                "row": 2,
                "title": "후보로 대기",
                "subtitle": "살 값이 오면 매일 확인에서 두 번 확인",
            },
            {**_EXCEPTION, "col": 0, "row": 3},
        ],
        "edges": [
            {"from": "start", "to": "data"},
            {"from": "data", "to": "ai"},
            {"from": "ai", "to": "stock"},
            {"from": "stock", "to": "weight"},
            {"from": "weight", "to": "condition"},
            {"from": "condition", "to": "action", "label": "yes"},
            {"from": "condition", "to": "result", "label": "no-wait"},
            {"from": "action", "to": "result"},
            {"from": "action", "to": "exception", "exception": True},
        ],
    },
]


def discovery_3y(share: Decimal = Decimal("0.2")) -> RuleDef:
    return RuleDef(
        rule_id=RULE_ID,
        name="3년 발굴",
        kind="ai",
        asset_share=share,
        targets=(),
        threshold=Decimal(0),
        check_time="08:30",
        display={"kind": "flow", "lanes": LANES},
    )
