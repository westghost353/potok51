"""Парное сопоставление операций.

Три задачи: снять двойной счёт (внутренние переводы, дубли эквайринга)
и найти транзит. Транзит ищется строго — 1:1 либо 1:N на одного
контрагента, — потому что «схлопывание» произвольных подмножеств платежей
находит совпадение почти всегда и превращает детектор в генератор
ложных срабатываний.
"""

from __future__ import annotations

from datetime import timedelta

from .config import Config
from .models import Category, NON_TRANSIT_OUTFLOW, Transaction


def link_internal_transfers(txs: list) -> int:
    """Пары «списание с одного своего счёта → зачисление на другой»."""
    outs = [t for t in txs if t.category == Category.INTERNAL_TRANSFER and t.outflow > 0]
    ins = [t for t in txs if t.category == Category.INTERNAL_TRANSFER and t.inflow > 0]
    used: set = set()
    pairs = 0
    for o in outs:
        for i in ins:
            if id(i) in used:
                continue
            if abs((i.date - o.date).days) <= 1 and abs(i.inflow - o.outflow) < 0.01:
                link = f"INT-{pairs + 1:04d}"
                o.link_id = i.link_id = link
                o.excluded_reason = i.excluded_reason = "internal_transfer"
                used.add(id(i))
                pairs += 1
                break
    return pairs


def link_acquiring_duplicates(txs: list) -> int:
    """Если одна и та же розничная выручка проведена и через 57, и через 62."""
    acq = [t for t in txs if t.category == Category.ACQUIRING_IN]
    rev = [t for t in txs if t.category == Category.REVENUE_OPERATING and t.inflow > 0]
    used: set = set()
    dupes = 0
    for a in acq:
        for r in rev:
            if id(r) in used:
                continue
            if r.date == a.date and abs(r.inflow - a.inflow) < 0.01:
                r.excluded_reason = "acquiring_duplicate"
                r.link_id = f"ACQ-{dupes + 1:04d}"
                used.add(id(r))
                dupes += 1
                break
    return dupes


def detect_transit(txs: list, cfg: Config) -> tuple:
    """Возвращает (число пар, сумма транзитного притока)."""
    tc = cfg.transit
    window = timedelta(days=tc.window_days)

    inflows = [
        t for t in txs
        if t.inflow > 0
        and t.excluded_reason is None
        and t.category in (Category.REVENUE_OPERATING, Category.OTHER_INCOME, Category.UNCLASSIFIED)
    ]
    outflows = [
        t for t in txs
        if t.outflow > 0
        and t.excluded_reason is None
        and t.category not in NON_TRANSIT_OUTFLOW
    ]
    outflows.sort(key=lambda t: t.date)

    used: set = set()
    pairs = 0
    volume = 0.0

    for inc in sorted(inflows, key=lambda t: t.date):
        candidates = [
            o for o in outflows
            if id(o) not in used and inc.date <= o.date <= inc.date + window
        ]
        if not candidates:
            continue

        best = None
        best_gap = None
        # 1:1
        for o in candidates:
            ratio = o.outflow / inc.inflow
            if tc.match_lower <= ratio <= tc.match_upper:
                gap = abs(ratio - 1.0)
                if best_gap is None or gap < best_gap:
                    best, best_gap = [o], gap
        # 1:N на одного контрагента
        if best is None:
            by_cp: dict = {}
            for o in candidates:
                by_cp.setdefault(o.counterparty or "", []).append(o)
            for group in by_cp.values():
                if len(group) < 2:
                    continue
                total = sum(o.outflow for o in group)
                ratio = total / inc.inflow
                if tc.match_lower <= ratio <= tc.match_upper:
                    gap = abs(ratio - 1.0)
                    if best_gap is None or gap < best_gap:
                        best, best_gap = group, gap

        if best:
            pairs += 1
            link = f"TR-{pairs:04d}"
            inc.category = Category.TRANSIT_SUSPECT
            inc.link_id = link
            inc.excluded_reason = "transit"
            volume += inc.inflow
            for o in best:
                o.link_id = link
                o.excluded_reason = "transit"
                used.add(id(o))

    return pairs, round(volume, 2)


def link_all(txs: list, cfg: Config) -> dict:
    return {
        "internal_pairs": link_internal_transfers(txs),
        "acquiring_duplicates": link_acquiring_duplicates(txs),
        "transit_pairs": (result := detect_transit(txs, cfg))[0],
        "transit_volume": result[1],
    }
