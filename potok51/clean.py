"""Мост от валового оборота к очищенной выручке и свободному потоку."""

from __future__ import annotations

from collections import defaultdict

from .models import (
    CATEGORY_RU,
    NON_REVENUE_INFLOW,
    OPERATING_OUTFLOW,
    Category,
    Exclusion,
    MonthlyPoint,
    Transaction,
    Volumes,
)

EXCLUSION_REASON_RU = {
    "internal_transfer": "Переводы между своими счетами",
    "acquiring_duplicate": "Дубль эквайринга",
    "transit": "Транзитные операции",
}


def _is_excluded_inflow(tx: Transaction) -> bool:
    return tx.inflow > 0 and (
        tx.excluded_reason is not None or tx.category in NON_REVENUE_INFLOW
    )


def compute_volumes(txs: list) -> Volumes:
    gross_in = round(sum(t.inflow for t in txs), 2)
    gross_out = round(sum(t.outflow for t in txs), 2)

    buckets: dict = defaultdict(lambda: {"amount": 0.0, "rows": []})
    for tx in txs:
        if not _is_excluded_inflow(tx):
            continue
        key = tx.excluded_reason or tx.category.value
        buckets[key]["amount"] += tx.inflow
        buckets[key]["rows"].append(tx.row_no)

    exclusions = []
    for key, data in sorted(buckets.items(), key=lambda kv: -kv[1]["amount"]):
        label = EXCLUSION_REASON_RU.get(key) or CATEGORY_RU.get(key, key)
        exclusions.append(
            Exclusion(
                category=key,
                label=label,
                amount=round(data["amount"], 2),
                share=round(data["amount"] / gross_in, 4) if gross_in else 0.0,
                rows=data["rows"][:500],
            )
        )

    excluded_total = sum(e.amount for e in exclusions)
    qualified = round(gross_in - excluded_total, 2)
    returns = round(
        sum(t.outflow for t in txs if t.category == Category.REVENUE_RETURN), 2
    )
    adjusted_revenue = round(qualified - returns, 2)
    operating_outflow = round(
        sum(
            t.outflow
            for t in txs
            if t.category in OPERATING_OUTFLOW and t.excluded_reason is None
        ),
        2,
    )
    return Volumes(
        gross_inflow=gross_in,
        gross_outflow=gross_out,
        qualified_inflow=qualified,
        adjusted_revenue=adjusted_revenue,
        operating_outflow=operating_outflow,
        fcf=round(adjusted_revenue - operating_outflow, 2),
        exclusions=exclusions,
    )


def compute_monthly(txs: list) -> list:
    months: dict = defaultdict(lambda: MonthlyPoint(month=""))
    for tx in txs:
        key = tx.month
        point = months[key]
        point.month = key
        point.gross_inflow += tx.inflow
        if tx.inflow > 0 and not _is_excluded_inflow(tx):
            point.qualified_inflow += tx.inflow
            point.adjusted_revenue += tx.inflow
        if tx.category == Category.REVENUE_RETURN:
            point.adjusted_revenue -= tx.outflow
        if tx.category in OPERATING_OUTFLOW and tx.excluded_reason is None:
            point.operating_outflow += tx.outflow

    result = []
    for key in sorted(months):
        p = months[key]
        p.gross_inflow = round(p.gross_inflow, 2)
        p.qualified_inflow = round(p.qualified_inflow, 2)
        p.adjusted_revenue = round(p.adjusted_revenue, 2)
        p.operating_outflow = round(p.operating_outflow, 2)
        p.fcf = round(p.adjusted_revenue - p.operating_outflow, 2)
        result.append(p)
    return result
