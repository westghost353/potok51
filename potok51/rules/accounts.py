"""Карта корреспондирующих счетов — первичный классификатор.

Ключевое преимущество карточки счёта 51 перед банковской выпиской:
бухгалтер клиента уже проставил корсчёт, то есть выполнил экономическую
квалификацию платежа. Эта карта переводит её в категории модели.

Значение: (категория при поступлении на 51, категория при списании с 51).
None означает, что счёт не даёт однозначной квалификации и решение
передаётся словарю паттернов назначения платежа.
"""

from __future__ import annotations

from ..models import Category as C

ACCOUNT_MAP: dict[str, tuple] = {
    "50": (C.CASH_DEPOSIT, C.CASH_WITHDRAWAL),
    "51": (C.INTERNAL_TRANSFER, C.INTERNAL_TRANSFER),
    "52": (C.INTERNAL_TRANSFER, C.INTERNAL_TRANSFER),
    "55": (C.DEPOSIT_IN, C.DEPOSIT_OUT),
    "57": (C.ACQUIRING_IN, C.ACQUIRING_OUT),
    "58": (C.LOAN_REPAY_IN, C.LOAN_ISSUE_OUT),
    "60": (C.SUPPLIER_REFUND, C.OPEX_SUPPLIERS),
    "62": (C.REVENUE_OPERATING, C.REVENUE_RETURN),
    "66": (C.FIN_LOAN_IN, C.FIN_LOAN_OUT),
    "67": (C.FIN_LOAN_IN, C.FIN_LOAN_OUT),
    "68": (C.OTHER_INCOME, C.OPEX_TAXES),
    "69": (C.OTHER_INCOME, C.OPEX_PAYROLL_TAX),
    "70": (C.OTHER_INCOME, C.OPEX_PAYROLL),
    "71": (C.OTHER_INCOME, C.CASH_PROXY),
    "73": (C.LOAN_REPAY_IN, C.LOAN_ISSUE_OUT),
    "75": (C.OWNER_CONTRIBUTION, C.OWNER_WITHDRAWAL),
    "76": (None, None),          # прочие расчёты — только через паттерны
    "79": (C.INTERNAL_TRANSFER, C.INTERNAL_TRANSFER),
    "80": (C.OWNER_CONTRIBUTION, C.OWNER_WITHDRAWAL),
    "84": (C.OTHER_INCOME, C.OWNER_WITHDRAWAL),
    "90": (C.REVENUE_OPERATING, C.REVENUE_RETURN),
    "91": (C.OTHER_INCOME, C.OPEX_BANK_FEES),
    "08": (C.OTHER_INCOME, C.CAPEX),
    "10": (C.SUPPLIER_REFUND, C.OPEX_SUPPLIERS),
    "41": (C.SUPPLIER_REFUND, C.OPEX_SUPPLIERS),
    "19": (C.OTHER_INCOME, C.OPEX_SUPPLIERS),
}


def account_category(corr_account: str | None, is_inflow: bool):
    """Категория по корсчёту. Возвращает None, если счёт не квалифицирует."""
    if not corr_account:
        return None
    prefix = str(corr_account).strip().split(".")[0].zfill(2)
    pair = ACCOUNT_MAP.get(prefix)
    if not pair:
        return None
    return pair[0] if is_inflow else pair[1]
