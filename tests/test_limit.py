"""Ограничители лимита и стоп-факторы."""

import pytest

from potok51.config import DEFAULT_CONFIG
from potok51.indicators import build_indicators
from potok51.limit import compute_limit, evaluate_stop_factors, make_decision
from potok51.models import Decision, DataQuality, MonthlyPoint, Status, Volumes


def monthly(revenue: float, opex: float, count: int = 12) -> list:
    return [
        MonthlyPoint(month=f"2026-{i + 1:02d}", gross_inflow=revenue,
                     qualified_inflow=revenue, adjusted_revenue=revenue,
                     operating_outflow=opex, fcf=revenue - opex)
        for i in range(count)
    ]


def volumes(revenue: float, opex: float, months: int = 12) -> Volumes:
    return Volumes(gross_inflow=revenue * months, gross_outflow=opex * months,
                   qualified_inflow=revenue * months, adjusted_revenue=revenue * months,
                   operating_outflow=opex * months, fcf=(revenue - opex) * months)


def test_l1_binds_on_scale_of_revenue():
    """Хорошая маржа не должна давать лимит выше масштаба самой выручки."""
    m = monthly(1_000_000, 850_000)
    limit = compute_limit(volumes(1_000_000, 850_000), m, [], "services", DEFAULT_CONFIG, 365)
    assert limit.binding_constraint == "L1"
    assert limit.constraints["L1"] == pytest.approx(1_200_000)


def test_l3_binds_when_working_capital_need_is_small():
    """Бизнес с крошечными операционными расходами не нуждается в большой оборотке."""
    m = monthly(1_000_000, 100_000)
    limit = compute_limit(volumes(1_000_000, 100_000), m, [], "retail", DEFAULT_CONFIG, 365)
    assert limit.binding_constraint == "L3"
    assert limit.constraints["L3"] < limit.constraints["L1"]


def test_l2_binds_when_margin_is_thin():
    m = monthly(20_000_000, 19_600_000)
    limit = compute_limit(volumes(20_000_000, 19_600_000), m, [], "wholesale", DEFAULT_CONFIG, 365)
    assert limit.binding_constraint == "L2"


def test_l4_caps_large_business():
    m = monthly(60_000_000, 30_000_000)
    limit = compute_limit(volumes(60_000_000, 30_000_000), m, [], "wholesale", DEFAULT_CONFIG, 365)
    assert limit.binding_constraint == "L4"
    assert limit.final <= DEFAULT_CONFIG.limit.product_ceiling


def test_zero_fcf_kills_debt_capacity():
    m = monthly(5_000_000, 5_400_000)
    limit = compute_limit(volumes(5_000_000, 5_400_000), m, [], "services", DEFAULT_CONFIG, 365)
    assert limit.constraints["L2"] == 0
    assert limit.final == 0


def test_flag_multiplier_reduces_limit():
    from potok51.models import Indicator
    m = monthly(10_000_000, 8_000_000)
    v = volumes(10_000_000, 8_000_000)
    clean = compute_limit(v, m, [], "retail", DEFAULT_CONFIG, 365)
    flagged = compute_limit(v, m, [
        Indicator(code="T7", name="x", status=Status.RED),
        Indicator(code="T8", name="y", status=Status.AMBER),
    ], "retail", DEFAULT_CONFIG, 365)
    assert flagged.multiplier == pytest.approx(0.7 * 0.9)
    assert flagged.final < clean.final


def test_multiplier_has_floor():
    from potok51.models import Indicator
    m = monthly(10_000_000, 8_000_000)
    reds = [Indicator(code=f"T{i}", name="x", status=Status.RED) for i in range(8)]
    limit = compute_limit(volumes(10_000_000, 8_000_000), m, reds, "retail", DEFAULT_CONFIG, 365)
    assert limit.multiplier == pytest.approx(DEFAULT_CONFIG.limit.multiplier_floor)


def test_limit_is_rounded_down_to_step():
    m = monthly(1_234_567, 900_000)
    limit = compute_limit(volumes(1_234_567, 900_000), m, [], "retail", DEFAULT_CONFIG, 365)
    assert limit.final % DEFAULT_CONFIG.limit.rounding_step == 0


def _stops(indicators, monthly_points, vol, quality=None):
    return evaluate_stop_factors([], vol, monthly_points, indicators,
                                 DEFAULT_CONFIG, quality or DataQuality(passed=True))


def test_stop_negative_fcf(healthy_card):
    from potok51.models import Indicator
    m = monthly(1_000_000, 1_200_000)
    stops = _stops([Indicator(code="T3", name="x", value=0.0, status=Status.GREEN)],
                   m, volumes(1_000_000, 1_200_000))
    assert any(s.startswith("S4") for s in stops)


def test_stop_transit():
    from potok51.models import Indicator
    m = monthly(5_000_000, 3_000_000)
    stops = _stops([Indicator(code="T3", name="Транзитность", value=0.75, status=Status.RED)],
                   m, volumes(5_000_000, 3_000_000))
    assert any(s.startswith("S1") for s in stops)


def test_stop_failed_data_quality():
    from potok51.models import Check, Indicator
    quality = DataQuality(checks=[Check(code="V1", name="Сальдо", passed=False, critical=True)],
                          passed=False)
    m = monthly(5_000_000, 3_000_000)
    stops = _stops([], m, volumes(5_000_000, 3_000_000), quality)
    assert any(s.startswith("S6") for s in stops)


def test_decision_matrix():
    from potok51.models import Indicator
    v = volumes(5_000_000, 3_000_000)
    assert make_decision([], [], v, DEFAULT_CONFIG).code == Decision.AUTO_APPROVE
    assert make_decision([Indicator(code="T4", name="x", status=Status.RED)], [], v,
                         DEFAULT_CONFIG).code == Decision.MANUAL_REVIEW
    assert make_decision([], ["S1. что-то"], v, DEFAULT_CONFIG).code == Decision.DECLINE
