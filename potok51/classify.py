"""Классификатор операций: корсчёт (первичный) + назначение платежа (вторичный)."""

from __future__ import annotations

from .models import Category, Transaction
from .rules.accounts import account_category
from .rules.patterns import OVERRIDE_PRIORITY, best_pattern, normalize_text


def classify(txs: list, client_inn: str | None = None) -> list:
    for tx in txs:
        text = normalize_text(tx.counterparty, tx.contract, tx.purpose, tx.doc_type)
        by_account = account_category(tx.corr_account, tx.is_inflow)
        pattern = best_pattern(text, tx.is_inflow)

        category = None
        source = None

        if pattern and pattern.priority >= OVERRIDE_PRIORITY:
            category, source = pattern.category, f"pattern:{pattern.name}"
        elif by_account is not None:
            category, source = by_account, f"corr_account:{tx.corr_account}"
        elif pattern:
            category, source = pattern.category, f"pattern:{pattern.name}"

        # Перевод между своими счетами: совпадение ИНН контрагента с ИНН клиента
        if client_inn and tx.counterparty and client_inn in (tx.counterparty or ""):
            category, source = Category.INTERNAL_TRANSFER, "own_inn"

        tx.category = category or Category.UNCLASSIFIED
        tx.category_source = source
    return txs


def auto_classified_share(txs: list) -> float:
    total = sum(t.amount for t in txs)
    if total <= 0:
        return 1.0
    known = sum(t.amount for t in txs if t.category != Category.UNCLASSIFIED)
    return round(known / total, 4)
