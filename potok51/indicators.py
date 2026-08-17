"""Пятнадцать риск-индикаторов со светофорами.

Индикаторы T1–T6 воспроизводят логику Методических рекомендаций
Банка России 18-МР, но используются здесь как кредитные факторы риска,
а не как основание для отказа в обслуживании счёта.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta

from .config import Config
from .models import (
    ACTIVITY_MARKERS,
    Category,
    Indicator,
    Status,
    Transaction,
)


def _grade(value, amber, red, higher_is_worse: bool) -> Status:
    if value is None:
        return Status.NA
    if higher_is_worse:
        if value > red:
            return Status.RED
        if value > amber:
            return Status.AMBER
        return Status.GREEN
    if value < red:
        return Status.RED
    if value < amber:
        return Status.AMBER
    return Status.GREEN


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}\u00a0%".replace(".", ",")


def _money(value) -> str:
    return "—" if value is None else f"{value:,.0f} ₽".replace(",", "\u00a0")


def _sum(txs: list, *categories, inflow: bool = False) -> tuple:
    cats = set(categories)
    rows = [t for t in txs if t.category in cats]
    total = sum(t.inflow if inflow else t.outflow for t in rows)
    return round(total, 2), [t.row_no for t in rows][:500]


def daily_balances(txs: list) -> dict:
    """Остаток на конец каждого дня периода, протянутый вперёд."""
    by_day: dict = {}
    for tx in sorted(txs, key=lambda t: (t.date, t.row_no)):
        if tx.balance_after is not None:
            by_day[tx.date] = abs(tx.balance_after)
    if not by_day:
        return {}
    start, end = min(by_day), max(by_day)
    series: dict = {}
    last = by_day[start]
    day = start
    while day <= end:
        last = by_day.get(day, last)
        series[day] = last
        day += timedelta(days=1)
    return series


def build_indicators(txs: list, monthly: list, volumes, cfg: Config) -> list:
    th = cfg.thresholds
    out: list = []
    gross_out = volumes.gross_outflow or 1.0
    gross_in = volumes.gross_inflow or 1.0
    revenue = volumes.adjusted_revenue or 1.0
    months = len(monthly) or 1

    # T1 — налоговая нагрузка
    taxes, tax_rows = _sum(txs, Category.OPEX_TAXES, Category.OPEX_PAYROLL_TAX)
    t1 = taxes / gross_out
    out.append(Indicator(
        code="T1", name="Налоговая нагрузка", value=round(t1, 4), display=_pct(t1),
        status=_grade(t1, *th.t1_tax_burden, higher_is_worse=False),
        explanation=f"Налоги и взносы {_money(taxes)} к обороту по списанию {_money(volumes.gross_outflow)}. "
                    f"Ориентир Банка России (18-МР) — не ниже 0,9 %.",
        rows=tax_rows,
    ))

    # T2 — реальность фонда оплаты труда
    payroll_months = {t.month for t in txs if t.category == Category.OPEX_PAYROLL}
    tax_months = {t.month for t in txs if t.category == Category.OPEX_PAYROLL_TAX}
    both = payroll_months & tax_months
    t2 = len(both) / months
    avg_rev = revenue / months
    status = _grade(t2, *th.t2_payroll_months_share, higher_is_worse=False)
    if avg_rev < th.t2_revenue_floor and status == Status.RED:
        status = Status.AMBER  # у микробизнеса без наёмных сотрудников это норма
    out.append(Indicator(
        code="T2", name="Реальность ФОТ", value=round(t2, 4),
        display=f"{len(both)} из {months} мес.", status=status,
        explanation="Месяцы, в которых одновременно есть выплата зарплаты и уплата НДФЛ и взносов. "
                    "Отсутствие ФОТ при значимой выручке — признак нереальности деятельности.",
        rows=[t.row_no for t in txs if t.category in (Category.OPEX_PAYROLL, Category.OPEX_PAYROLL_TAX)][:500],
    ))

    # T3 — транзитность
    transit_rows = [t for t in txs if t.category == Category.TRANSIT_SUSPECT]
    transit_sum = round(sum(t.inflow for t in transit_rows), 2)
    t3 = transit_sum / gross_in
    out.append(Indicator(
        code="T3", name="Транзитность", value=round(t3, 4), display=_pct(t3),
        status=_grade(t3, *th.t3_transit_ratio, higher_is_worse=True),
        explanation=f"{_money(transit_sum)} поступлений ушли со счёта в течение {cfg.transit.window_days} дней "
                    f"тем же объёмом. Сопоставлено пар: {len({t.link_id for t in transit_rows if t.link_id})}.",
        rows=[t.row_no for t in transit_rows][:500],
    ))

    # T4 — обналичивание
    cash, cash_rows = _sum(txs, Category.CASH_WITHDRAWAL, Category.CASH_PROXY)
    t4 = cash / gross_out
    out.append(Indicator(
        code="T4", name="Снятие наличных и подотчёт", value=round(t4, 4), display=_pct(t4),
        status=_grade(t4, *th.t4_cash_ratio, higher_is_worse=True),
        explanation=f"Снятия, касса и перечисления в подотчёт {_money(cash)} к обороту по списанию.",
        rows=cash_rows,
    ))

    # T5 — накопление остатка
    series = daily_balances(txs)
    avg_balance = statistics.fmean(series.values()) if series else None
    # знаменатель — ВАЛОВОЙ приток: логика 18-МР сравнивает остаток именно
    # с общим объёмом движения по счёту, иначе транзитная компания с малой
    # очищенной выручкой выглядит как накапливающая деньги
    avg_month_in = volumes.gross_inflow / months if months else 0
    t5 = (avg_balance / avg_month_in) if (avg_balance is not None and avg_month_in) else None
    out.append(Indicator(
        code="T5", name="Накопление остатка", value=round(t5, 4) if t5 is not None else None,
        display=_pct(t5),
        status=_grade(t5, *th.t5_balance_ratio, higher_is_worse=False),
        explanation=f"Средний дневной остаток {_money(avg_balance)} к среднемесячному валовому "
                    f"притоку {_money(avg_month_in)}. Отсутствие накопления при активном движении "
                    "средств — признак проходного счёта.",
    ))

    # T6 — признаки хозяйственной деятельности
    activity_months = {t.month for t in txs if t.category in ACTIVITY_MARKERS}
    t6 = len(activity_months)
    out.append(Indicator(
        code="T6", name="Признаки хозяйственной деятельности", value=float(t6),
        display=f"{t6} из {months} мес.",
        status=_grade(float(t6), float(th.t6_activity_months[0]), float(th.t6_activity_months[1]),
                      higher_is_worse=False),
        explanation="Месяцы с платежами за аренду, связь или банковское обслуживание. "
                    "Их отсутствие — типовой признак технической компании.",
        rows=[t.row_no for t in txs if t.category in ACTIVITY_MARKERS][:500],
    ))

    # T7 — концентрация покупателей
    # эквайринг исключён намеренно: за расчётами банка-эквайера стоят тысячи
    # розничных покупателей, это противоположность концентрации
    by_cp: dict = defaultdict(float)
    acquiring = round(sum(t.inflow for t in txs if t.category == Category.ACQUIRING_IN), 2)
    for t in txs:
        if t.inflow > 0 and t.excluded_reason is None and t.category == Category.REVENUE_OPERATING:
            by_cp[t.counterparty or "не указан"] += t.inflow
    top1_name, top1_amount = max(by_cp.items(), key=lambda kv: kv[1]) if by_cp else ("—", 0.0)
    total_cp = sum(by_cp.values()) or 1.0
    t7 = top1_amount / total_cp
    hhi = sum((v / total_cp) ** 2 for v in by_cp.values())
    out.append(Indicator(
        code="T7", name="Концентрация покупателей", value=round(t7, 4), display=_pct(t7),
        status=_grade(t7, *th.t7_top1_share, higher_is_worse=True),
        explanation=f"Крупнейший плательщик — {top1_name}, {_money(top1_amount)}. "
                    f"Индекс концентрации HHI {hhi:.3f}, всего плательщиков {len(by_cp)}."
                    + (f" Дополнительно {_money(acquiring)} поступило эквайрингом "
                       "и в расчёт концентрации не включалось." if acquiring else ""),
    ))

    # T8 — волатильность выручки
    values = [m.adjusted_revenue for m in monthly]
    mean = statistics.fmean(values) if values else 0
    cv = (statistics.pstdev(values) / mean) if mean else None
    out.append(Indicator(
        code="T8", name="Волатильность выручки", value=round(cv, 4) if cv is not None else None,
        display="—" if cv is None else f"{cv:.2f}".replace(".", ","),
        status=_grade(cv, *th.t8_revenue_cv, higher_is_worse=True),
        explanation="Коэффициент вариации помесячной очищенной выручки за период.",
    ))

    # T9 — тренд выручки
    trend = None
    if len(values) >= 6:
        last3 = statistics.fmean(values[-3:])
        prev3 = statistics.fmean(values[-6:-3])
        trend = (last3 / prev3 - 1) if prev3 else None
    out.append(Indicator(
        code="T9", name="Тренд выручки", value=round(trend, 4) if trend is not None else None,
        display="—" if trend is None else f"{trend * 100:+.1f}\u00a0%".replace(".", ","),
        status=_grade(trend, *th.t9_revenue_trend, higher_is_worse=False),
        explanation="Последние три месяца к трём предыдущим по очищенной выручке.",
    ))

    # T10 — долговая нагрузка
    debt, debt_rows = _sum(txs, Category.FIN_LOAN_OUT, Category.FIN_INTEREST)
    t10 = debt / revenue
    out.append(Indicator(
        code="T10", name="Текущая долговая нагрузка", value=round(t10, 4), display=_pct(t10),
        status=_grade(t10, *th.t10_debt_burden, higher_is_worse=True),
        explanation=f"Погашение тела и процентов {_money(debt)} к очищенной выручке.",
        rows=debt_rows,
    ))

    # T11 — принудительное взыскание
    enf, enf_rows = _sum(txs, Category.ENFORCEMENT)
    t11 = enf / gross_out
    out.append(Indicator(
        code="T11", name="Принудительное взыскание", value=round(t11, 4), display=_pct(t11),
        status=_grade(t11, *th.t11_enforcement, higher_is_worse=True),
        explanation=f"Списания по исполнительным документам и инкассовым поручениям: {_money(enf)}.",
        rows=enf_rows,
    ))

    # T12 — маржинальность потока
    t12 = volumes.fcf / revenue
    out.append(Indicator(
        code="T12", name="Маржинальность потока", value=round(t12, 4), display=_pct(t12),
        status=_grade(t12, *th.t12_flow_margin, higher_is_worse=False),
        explanation=f"Свободный операционный поток {_money(volumes.fcf)} к очищенной выручке "
                    f"{_money(volumes.adjusted_revenue)}.",
    ))

    # T13 — вывод собственнику
    owner, owner_rows = _sum(txs, Category.OWNER_WITHDRAWAL)
    t13 = owner / revenue
    out.append(Indicator(
        code="T13", name="Вывод собственнику", value=round(t13, 4), display=_pct(t13),
        status=_grade(t13, *th.t13_owner_withdrawal, higher_is_worse=True),
        explanation=f"Дивиденды и переводы собственнику {_money(owner)} к очищенной выручке.",
        rows=owner_rows,
    ))

    # T14 — дни с нулевым остатком
    t14 = None
    if series:
        avg_daily_out = volumes.operating_outflow / max(len(series), 1)
        floor = avg_daily_out
        zero_days = sum(1 for v in series.values() if v < floor)
        t14 = zero_days / len(series)
    out.append(Indicator(
        code="T14", name="Дни без ликвидности", value=round(t14, 4) if t14 is not None else None,
        display=_pct(t14),
        status=_grade(t14, *th.t14_zero_balance_days, higher_is_worse=True),
        explanation="Доля дней, когда остатка не хватало на один средний день операционных платежей.",
    ))

    # T15 — качество данных
    unclassified = round(sum(t.amount for t in txs if t.category == Category.UNCLASSIFIED), 2)
    t15 = unclassified / (volumes.gross_inflow + volumes.gross_outflow or 1.0)
    out.append(Indicator(
        code="T15", name="Качество разметки данных", value=round(t15, 4), display=_pct(t15),
        status=_grade(t15, *th.t15_data_quality, higher_is_worse=True),
        explanation=f"Не классифицировано {_money(unclassified)} оборота. "
                    "Свыше 15 % — кейс уходит на ручной разбор.",
        rows=[t.row_no for t in txs if t.category == Category.UNCLASSIFIED][:500],
    ))

    return out
