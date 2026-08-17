"""Модель лимита: четыре независимых ограничителя, множители флагов, стоп-факторы.

Единой формулы намеренно нет. Одна формула даёт правдоподобное число,
которое нечем защищать: андеррайтер спрашивает не «сколько», а «почему
столько», и ответом должен быть конкретный связывающий ограничитель.
"""

from __future__ import annotations

import statistics

from .config import Config, INDUSTRY_RU
from .models import (
    Category,
    Decision,
    DecisionResult,
    Indicator,
    LimitResult,
    Status,
    Volumes,
)

CONSTRAINT_LABELS = {
    "L1": "Масштаб выручки",
    "L2": "Способность обслуживать долг",
    "L3": "Потребность в оборотном капитале",
    "L4": "Потолок продукта",
}


def _annuity_pv_factor(annual_rate: float, months: int) -> float:
    """Сколько долга обслуживает один рубль ежемесячного платежа."""
    r = annual_rate / 12
    if r <= 0:
        return float(months)
    return (1 - (1 + r) ** -months) / r


def _round_down(value: float, step: float) -> float:
    if value <= 0:
        return 0.0
    return float(int(value / step) * step)


def compute_limit(
    volumes: Volumes,
    monthly: list,
    indicators: list,
    industry: str,
    cfg: Config,
    period_days: int,
) -> LimitResult:
    lc = cfg.limit
    industry = industry if industry in lc.industry_k else lc.default_industry
    window = monthly[-lc.revenue_window_months:] if monthly else []

    arm = statistics.fmean([m.adjusted_revenue for m in window]) if window else 0.0
    k = lc.industry_k[industry]
    l1 = max(k * arm, 0.0)

    fcf_values = [m.fcf for m in monthly] or [0.0]
    fcf_median = statistics.median(fcf_values)
    max_payment = max(fcf_median / lc.dscr_target, 0.0)
    l2 = max_payment * _annuity_pv_factor(lc.annual_rate, lc.term_months)

    cycle_days = lc.industry_cycle_days.get(industry, 45)
    daily_out = volumes.operating_outflow / max(period_days, 1)
    l3 = daily_out * cycle_days

    l4 = lc.product_ceiling

    constraints = {"L1": round(l1, 2), "L2": round(l2, 2), "L3": round(l3, 2), "L4": round(l4, 2)}
    binding = min(constraints, key=constraints.get)
    base = constraints[binding]

    multiplier = 1.0
    for ind in indicators:
        if ind.status == Status.AMBER:
            multiplier *= lc.multiplier_amber
        elif ind.status == Status.RED:
            multiplier *= lc.multiplier_red
    multiplier = max(multiplier, lc.multiplier_floor)

    final = _round_down(base * multiplier, lc.rounding_step)
    low = _round_down(final * lc.range_lower_k, lc.rounding_step)

    def f(value: float) -> str:
        return f"{value:,.0f}".replace(",", "\u00a0")

    pv = _annuity_pv_factor(lc.annual_rate, lc.term_months)
    formulas = {
        "L1": f"{k:.2f} × {f(arm)} ₽ среднемесячной очищенной выручки за последние "
              f"{len(window)} мес ({INDUSTRY_RU.get(industry, industry)}) = {f(l1)} ₽",
        "L2": f"медиана свободного потока {f(fcf_median)} ₽/мес ÷ DSCR {lc.dscr_target} = "
              f"{f(max_payment)} ₽/мес допустимого платежа × коэффициент аннуитета {pv:.2f} "
              f"(ставка {lc.annual_rate * 100:.0f} % годовых, срок {lc.term_months} мес) = {f(l2)} ₽",
        "L3": f"средний дневной операционный отток {f(daily_out)} ₽ × {cycle_days} дн. "
              f"операционного цикла = {f(l3)} ₽",
        "L4": f"потолок беззалогового транша для сегмента = {f(l4)} ₽",
    }

    return LimitResult(
        constraints=constraints,
        constraint_labels=CONSTRAINT_LABELS,
        constraint_formulas=formulas,
        binding_constraint=binding,
        base=round(base, 2),
        multiplier=round(multiplier, 4),
        final=final,
        range_low=low,
        range_high=final,
    )


def evaluate_stop_factors(
    txs: list, volumes: Volumes, monthly: list, indicators: list, cfg: Config, quality
) -> list:
    s = cfg.stops
    stops: list = []
    by_code = {i.code: i for i in indicators}

    t3 = by_code.get("T3")
    if t3 and t3.value is not None and t3.value > s.transit_ratio:
        stops.append(f"S1. Транзитность {t3.value * 100:.0f}\u00a0% превышает предельные "
                     f"{s.transit_ratio * 100:.0f}\u00a0%")

    t1 = by_code.get("T1")
    if (t1 and t1.value is not None and t1.value < s.tax_burden
            and volumes.gross_outflow > s.tax_burden_turnover_floor):
        # десятичная запятая ставится только в числе: замена по всей строке
        # превращала «S2.» в «S2,»
        burden = f"{t1.value * 100:.2f}".replace(".", ",")
        turnover = f"{volumes.gross_outflow:,.0f}".replace(",", "\u00a0")
        stops.append(f"S2. Налоговая нагрузка {burden}\u00a0% "
                     f"при обороте по списанию {turnover} ₽")

    t11 = by_code.get("T11")
    if t11 and t11.value is not None and t11.value > s.enforcement_share:
        share = f"{t11.value * 100:.1f}".replace(".", ",")
        stops.append(f"S3. Взыскания по исполнительным документам {share}\u00a0% оборота")

    window = monthly[-s.negative_fcf_window:]
    negative = sum(1 for m in window if m.fcf < 0)
    if negative >= s.negative_fcf_months:
        stops.append(f"S4. Свободный поток отрицателен в {negative} из последних "
                     f"{len(window)} месяцев")

    if monthly:
        last3 = statistics.fmean([m.adjusted_revenue for m in monthly[-3:]])
        if last3 < s.min_revenue_last3:
            stops.append("S5. Очищенная выручка последних трёх месяцев "
                         + f"{last3:,.0f}".replace(",", "\u00a0")
                         + " ₽/мес ниже минимальной")

    if not quality.passed:
        failed = ", ".join(c.code for c in quality.failed_critical())
        stops.append(f"S6. Не пройдены критические проверки целостности карточки: {failed}")

    t9 = by_code.get("T9")
    if t9 and t9.value is not None and t9.value < s.revenue_collapse:
        stops.append(f"S7. Падение выручки на {abs(t9.value) * 100:.0f}\u00a0% за последний квартал")

    return stops


def make_decision(indicators: list, stops: list, volumes: Volumes, cfg: Config) -> DecisionResult:
    if stops:
        return DecisionResult(code=Decision.DECLINE, stop_factors=stops,
                              reasons=["Сработали стоп-факторы кредитной политики"])

    reds = [i for i in indicators if i.status == Status.RED]
    ambers = [i for i in indicators if i.status == Status.AMBER]
    if reds:
        return DecisionResult(
            code=Decision.MANUAL_REVIEW,
            reasons=[f"Красный индикатор {i.code}. {i.name}: {i.display}" for i in reds],
        )
    reasons = [f"Жёлтый индикатор {i.code}. {i.name}: {i.display}" for i in ambers]
    return DecisionResult(
        code=Decision.AUTO_APPROVE,
        reasons=reasons or ["Все индикаторы в зелёной зоне"],
    )
