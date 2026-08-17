"""Контроль целостности карточки до анализа.

Смысл модуля: не считать лимит по недостоверному файлу. Клиент может
подать карточку за неполный период, с обрезанными строками или из другой
базы — все три случая ловятся арифметикой самого файла.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from .config import Config
from .models import Check, CardMeta, DataQuality, Transaction


def _m(value: float) -> str:
    """Денежный формат по-русски: 269 207 543,12 вместо 269,207,543.12."""
    return f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")


def _p(value: float) -> str:
    return f"{value * 100:.1f}\u00a0%".replace(".", ",")


def _months_between(start, end) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def validate(txs: list, meta: CardMeta, cfg: Config) -> DataQuality:
    q = cfg.quality
    checks: list = []
    total_in = round(sum(t.inflow for t in txs), 2)
    total_out = round(sum(t.outflow for t in txs), 2)

    # V1 — сходимость сальдо
    if meta.opening_balance is not None and meta.closing_balance is not None:
        expected = round(meta.opening_balance + total_in - total_out, 2)
        # знак сальдо в печатной форме не сохраняется, сравниваем по модулю
        delta = min(abs(expected - meta.closing_balance), abs(abs(expected) - abs(meta.closing_balance)))
        checks.append(Check(
            code="V1", name="Сходимость сальдо", critical=True,
            passed=delta <= q.balance_tolerance_rub,
            detail=f"Начальное {_m(meta.opening_balance)} + приход {_m(total_in)} "
                   f"− расход {_m(total_out)} = {_m(expected)} ₽; "
                   f"в файле {_m(meta.closing_balance)} ₽; расхождение {_m(delta)} ₽",
        ))
    else:
        checks.append(Check(
            code="V1", name="Сходимость сальдо", critical=False, passed=True,
            detail="Строки сальдо в файле отсутствуют, проверка пропущена",
        ))

    # V2 — совпадение с заявленными оборотами
    if meta.stated_debit_turnover and meta.stated_credit_turnover:
        d_in = abs(total_in - meta.stated_debit_turnover)
        d_out = abs(total_out - meta.stated_credit_turnover)
        checks.append(Check(
            code="V2", name="Совпадение с итогами файла", critical=True,
            passed=max(d_in, d_out) <= q.balance_tolerance_rub,
            detail=f"Разобрано приход {_m(total_in)} ₽ (в файле {_m(meta.stated_debit_turnover)}), "
                   f"расход {_m(total_out)} ₽ (в файле {_m(meta.stated_credit_turnover)})",
        ))
    else:
        checks.append(Check(
            code="V2", name="Совпадение с итогами файла", critical=False, passed=True,
            detail="Строка оборотов отсутствует, проверка пропущена",
        ))

    # V3 — глубина периода
    months = _months_between(txs[0].date, txs[-1].date) if txs else 0
    checks.append(Check(
        code="V3", name="Глубина периода", critical=True,
        passed=months >= q.min_months,
        detail=f"Период {txs[0].date:%d.%m.%Y}–{txs[-1].date:%d.%m.%Y}, {months} мес. "
               f"(минимум {q.min_months})" if txs else "Операций нет",
    ))

    # V4 — разрывы в данных
    max_gap = timedelta(0)
    gap_at = None
    for prev, nxt in zip(txs, txs[1:]):
        gap = nxt.date - prev.date
        if gap > max_gap:
            max_gap, gap_at = gap, prev.date
    checks.append(Check(
        code="V4", name="Непрерывность операций", critical=False,
        passed=max_gap.days <= q.max_gap_days,
        detail=f"Максимальный разрыв {max_gap.days} дн."
               + (f" после {gap_at:%d.%m.%Y}" if gap_at else ""),
    ))

    # V5 — нераспознанные даты
    bad_share = meta.bad_date_rows / max(len(txs) + meta.bad_date_rows, 1)
    checks.append(Check(
        code="V5", name="Распознавание дат", critical=True,
        passed=bad_share <= q.max_bad_date_share,
        detail=f"Строк с нераспознанной датой: {meta.bad_date_rows} ({_p(bad_share)})",
    ))

    # V6 — полнота реквизитов
    no_meta = [t for t in txs if not t.corr_account and not t.purpose]
    share = sum(t.amount for t in no_meta) / max(total_in + total_out, 1)
    checks.append(Check(
        code="V6", name="Полнота реквизитов", critical=False,
        passed=share <= q.max_missing_meta_share,
        detail=f"Операций без корсчёта и назначения: {len(no_meta)} на {_p(share)} оборота",
    ))

    # V7 — валютные операции
    fx = [t for t in txs if (t.corr_account or "").startswith("52")]
    checks.append(Check(
        code="V7", name="Отсутствие валютных операций", critical=False,
        passed=not fx,
        detail=f"Валютных операций: {len(fx)}" if fx else "Валютных операций нет",
    ))

    # V8 — дубли
    keys = Counter((t.date, t.inflow, t.outflow, t.counterparty, t.purpose) for t in txs)
    dupes = sum(c - 1 for c in keys.values() if c > 1)
    checks.append(Check(
        code="V8", name="Отсутствие дублей", critical=False,
        passed=dupes == 0,
        detail=f"Полных дублей строк: {dupes}",
    ))

    passed = all(c.passed for c in checks if c.critical)
    return DataQuality(checks=checks, passed=passed)
