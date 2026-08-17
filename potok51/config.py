"""Единая точка правды для всех калибруемых параметров модели.

Ни один порог не должен быть зашит в коде вне этого модуля: пороги —
основной объект последующей калибровки на исторических данных.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RULES_VERSION = "1.0.0"


@dataclass(frozen=True)
class TransitConfig:
    window_days: int = 3
    # Полоса допуска подобрана на синтетическом наборе: при 0,90–1,10 ложные
    # срабатывания на здоровой оптовой торговле достигают 11 % притока,
    # при 0,95–1,05 падают до 8 %, при этом транзитная схема детектируется
    # одинаково (81 %). Дальнейшее сужение теряет схемы с комиссией выше 5 %.
    match_lower: float = 0.95
    match_upper: float = 1.05


@dataclass(frozen=True)
class Thresholds:
    """Пороги индикаторов: (жёлтый, красный)."""

    t1_tax_burden: tuple = (0.02, 0.009)           # ниже — хуже
    t2_payroll_months_share: tuple = (0.80, 0.50)  # ниже — хуже
    t2_revenue_floor: float = 5_000_000.0          # порог применимости T2, руб/мес
    t3_transit_ratio: tuple = (0.15, 0.40)         # выше — хуже
    t4_cash_ratio: tuple = (0.10, 0.30)            # выше — хуже
    t5_balance_ratio: tuple = (0.05, 0.02)         # ниже — хуже
    t6_activity_months: tuple = (6, 3)             # ниже — хуже
    t7_top1_share: tuple = (0.40, 0.60)            # выше — хуже
    t8_revenue_cv: tuple = (0.35, 0.60)            # выше — хуже
    t9_revenue_trend: tuple = (-0.15, -0.30)       # ниже — хуже
    t10_debt_burden: tuple = (0.15, 0.25)          # выше — хуже
    t11_enforcement: tuple = (0.0, 0.02)           # выше — хуже
    t12_flow_margin: tuple = (0.05, 0.0)           # ниже — хуже
    t13_owner_withdrawal: tuple = (0.20, 0.40)     # выше — хуже
    t14_zero_balance_days: tuple = (0.10, 0.25)    # выше — хуже
    t15_data_quality: tuple = (0.05, 0.15)         # выше — хуже


@dataclass(frozen=True)
class StopFactors:
    transit_ratio: float = 0.60
    tax_burden: float = 0.003
    tax_burden_turnover_floor: float = 10_000_000.0
    enforcement_share: float = 0.05
    negative_fcf_months: int = 4
    negative_fcf_window: int = 6
    min_revenue_last3: float = 300_000.0
    revenue_collapse: float = -0.50


@dataclass(frozen=True)
class LimitConfig:
    industry_k: dict = field(
        default_factory=lambda: {
            "wholesale": 1.5,
            "retail": 1.0,
            "services": 1.2,
            "manufacturing": 1.5,
            "construction": 0.8,
            "transport": 1.0,
        }
    )
    industry_cycle_days: dict = field(
        default_factory=lambda: {
            "wholesale": 60,
            "retail": 30,
            "services": 45,
            "manufacturing": 75,
            "construction": 90,
            "transport": 45,
        }
    )
    default_industry: str = "services"
    dscr_target: float = 1.4
    annual_rate: float = 0.24
    term_months: int = 24
    product_ceiling: float = 20_000_000.0
    revenue_window_months: int = 6
    multiplier_amber: float = 0.90
    multiplier_red: float = 0.70
    multiplier_floor: float = 0.40
    rounding_step: float = 100_000.0
    range_lower_k: float = 0.80


@dataclass(frozen=True)
class QualityConfig:
    balance_tolerance_rub: float = 1.0
    min_months: int = 6
    max_gap_days: int = 21
    max_bad_date_share: float = 0.01
    max_missing_meta_share: float = 0.05
    max_unclassified_share: float = 0.15


@dataclass(frozen=True)
class Config:
    transit: TransitConfig = field(default_factory=TransitConfig)
    thresholds: Thresholds = field(default_factory=Thresholds)
    stops: StopFactors = field(default_factory=StopFactors)
    limit: LimitConfig = field(default_factory=LimitConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)


INDUSTRY_RU = {
    "wholesale": "Оптовая торговля и дистрибуция",
    "retail": "Розничная торговля",
    "services": "Услуги",
    "manufacturing": "Производство",
    "construction": "Строительство",
    "transport": "Транспорт и логистика",
}

DEFAULT_CONFIG = Config()
