"""Cutting a filing's text to what a call needs (the prompt is one command-line argument).

A quarterly report is hundreds of thousands of characters; an earnings press release a few
thousand (T27 read 4,000-29,000). Short texts go whole. A long one keeps its opening (title,
summary table) and the lines around the words of the metrics the call asks for, in document
order, until the limit.
"""

from __future__ import annotations

from collections.abc import Iterable

from autotrade.domain import metrics

TEXT_LIMIT = 24_000  # characters of filing text in one prompt (Korean: ~72 KB in UTF-8)
HEAD = 3_000
CONTEXT_LINES = 2
GAP = "\n…\n"

# Words a filing uses for each metric, Korean and English.
WORDS: dict[str, tuple[str, ...]] = {
    "revenue": ("매출", "수익", "revenue", "net sales", "sales"),
    "operating_income": ("영업이익", "영업손익", "operating income", "operating profit"),
    "net_income": ("순이익", "당기순", "net income", "net earnings"),
    "op_margin": ("영업이익률", "operating margin"),
    "eps": ("주당", "EPS", "per share"),
    "fcf": ("잉여현금", "free cash flow", "FCF"),
    "ebitda_margin": ("EBITDA",),
    "net_debt_to_ebitda": ("순차입", "순부채", "net debt", "leverage"),
    "backlog": ("수주잔고", "수주 잔고", "backlog", "remaining performance obligation"),
    "new_orders": ("수주", "신규 수주", "orders", "bookings", "order intake", "awards"),
    "book_to_bill": ("book-to-bill", "book to bill", "수주"),
    "monthly_revenue_yoy": ("월매출", "monthly revenue", "revenue for"),
    "segment_revenue": ("부문", "segment"),
    "segment_operating_income": ("부문", "segment"),
    "segment_op_margin": ("부문", "segment"),
    "segment_backlog": ("부문", "segment", "backlog", "수주잔고"),
    "guidance": ("전망", "목표", "가이던스", "guidance", "outlook", "expects", "forecast"),
}


def keywords(metric_keys: Iterable[str]) -> list[str]:
    """Words to look for: each metric's words and its parameter (a segment, a guidance item)."""
    out: list[str] = []
    for key in metric_keys:
        d, param = metrics.resolve(key)
        out.extend(WORDS.get(d.key, ()))
        if param:
            out.append(param)
            out.extend(word for word in param.split() if len(word) >= 2)
    unique: dict[str, str] = {}
    for word in out:
        unique.setdefault(word.lower(), word)
    return list(unique.values())


def focus(text: str, words: Iterable[str], limit: int = TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    lowered = [w.lower() for w in words if w]
    lines = text.splitlines()
    keep: set[int] = set()
    head_chars = 0
    for i, line in enumerate(lines):
        if head_chars >= HEAD:
            break
        keep.add(i)
        head_chars += len(line) + 1
    budget = limit - head_chars
    for i, line in enumerate(lines):
        if i in keep or not any(w in line.lower() for w in lowered):
            continue
        window = range(max(0, i - CONTEXT_LINES), min(len(lines), i + CONTEXT_LINES + 1))
        cost = sum(len(lines[j]) + 1 for j in window if j not in keep)
        if cost > budget:
            break
        keep.update(window)
        budget -= cost
    out: list[str] = []
    last = -2
    for i in sorted(keep):
        if out and i != last + 1:
            out.append(GAP.strip("\n"))
        out.append(lines[i])
        last = i
    return "\n".join(out)[:limit]
