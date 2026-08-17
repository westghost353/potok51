"""Профили синтетических клиентов для проверки конвейера.

Каждый профиль задаёт экономику бизнеса в долях от выручки. Три последних
профиля — «плохие»: они существуют, чтобы проверять срабатывание
стоп-факторов и красных индикаторов, а не чтобы получить лимит.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Profile:
    key: str
    org: str
    inn: str
    industry: str
    title: str
    expected: str                      # ожидаемое решение конвейера
    revenue_base: float                # выручка в первый месяц, руб
    revenue_growth: float = 0.0        # прирост месяц к месяцу
    season: list = field(default_factory=list)   # 12 множителей сезонности
    customers: int = 25
    top1_share: float = 0.15
    acquiring_share: float = 0.0       # доля выручки через эквайринг (счёт 57)
    supplier_share: float = 0.60
    payroll_share: float = 0.12
    tax_share: float = 0.05            # налоги + взносы к выручке
    rent_monthly: float = 0.0
    comms_monthly: float = 0.0
    bank_fee_monthly: float = 3_500.0
    transit_share: float = 0.0         # доля транзита к валовому притоку
    cash_share: float = 0.0            # снятия и подотчёт к выручке
    owner_share: float = 0.12          # вывод собственнику к выручке
    loan_payment: float = 0.0          # ежемесячное погашение тела
    loan_interest: float = 0.0
    has_enforcement: bool = False
    internal_transfers: int = 1        # переводов между своими счетами в месяц
    collapse_factor: float = 1.0       # множитель выручки в последние 3 месяца
    second_account: bool = False
    layout: str = "multirow"           # multirow | inline
    opening_balance: float = 500_000.0


def flat(n: float = 1.0) -> list:
    return [n] * 12


PROFILES: list[Profile] = [
    Profile(
        key="01_wholesale_healthy",
        org='ООО «Северный Двор»',
        inn="7712345678",
        industry="wholesale",
        title="Оптовая торговля стройматериалами, здоровый профиль",
        expected="AUTO_APPROVE",
        revenue_base=18_000_000,
        revenue_growth=0.015,
        season=[0.9, 0.95, 1.0, 1.05, 1.1, 1.05, 0.85, 0.8, 0.9, 1.0, 1.1, 1.15],
        customers=35,
        top1_share=0.14,
        supplier_share=0.62,
        payroll_share=0.10,
        tax_share=0.055,
        rent_monthly=450_000,
        comms_monthly=85_000,
        owner_share=0.085,
        loan_payment=350_000,
        loan_interest=95_000,
        internal_transfers=2,
        second_account=True,
        opening_balance=2_400_000,
    ),
    Profile(
        key="02_retail_acquiring",
        org='ООО «Пять Углов»',
        inn="7801234567",
        industry="retail",
        title="Розничная сеть с эквайрингом, проверка счёта 57",
        expected="AUTO_APPROVE",
        revenue_base=9_500_000,
        revenue_growth=0.008,
        season=[1.0, 1.05, 1.15, 1.2, 1.3, 0.85, 0.8, 0.85, 0.95, 1.0, 1.05, 1.1],
        customers=12,
        top1_share=0.10,
        acquiring_share=0.72,
        supplier_share=0.55,
        payroll_share=0.11,
        tax_share=0.045,
        rent_monthly=780_000,
        comms_monthly=60_000,
        owner_share=0.08,
        opening_balance=1_100_000,
        layout="inline",
    ),
    Profile(
        key="03_services_concentration",
        org='ООО «Тензор Дельта»',
        inn="7727001122",
        industry="services",
        title="ИТ-аутсорс с концентрацией на одном заказчике",
        expected="MANUAL_REVIEW",
        revenue_base=6_200_000,
        revenue_growth=0.01,
        season=flat(),
        customers=5,
        top1_share=0.68,
        supplier_share=0.22,
        payroll_share=0.34,
        tax_share=0.07,
        rent_monthly=310_000,
        comms_monthly=145_000,
        owner_share=0.10,
        opening_balance=1_800_000,
    ),
    Profile(
        key="04_construction_seasonal",
        org='ООО «Стройпоток Регион»',
        inn="6612340099",
        industry="construction",
        title="Строительный подряд, сезонность и кассовые разрывы",
        expected="MANUAL_REVIEW",
        revenue_base=14_000_000,
        revenue_growth=0.0,
        season=[0.25, 0.3, 0.5, 1.4, 1.9, 1.8, 1.6, 1.3, 0.7, 0.35, 0.25, 0.3],
        customers=8,
        top1_share=0.38,
        supplier_share=0.62,
        payroll_share=0.14,
        tax_share=0.04,
        rent_monthly=220_000,
        comms_monthly=40_000,
        owner_share=0.06,
        loan_payment=600_000,
        loan_interest=180_000,
        opening_balance=900_000,
    ),
    Profile(
        key="05_transport_ip",
        org='ИП Ковалёв Артём Сергеевич',
        inn="502712345678",
        industry="transport",
        title="Грузоперевозки, ИП с регулярными переводами себе",
        expected="MANUAL_REVIEW",
        revenue_base=4_100_000,
        revenue_growth=0.005,
        season=[1.0, 1.0, 1.05, 1.1, 1.1, 1.05, 0.9, 0.95, 1.0, 1.05, 1.0, 1.0],
        customers=18,
        top1_share=0.22,
        supplier_share=0.44,
        payroll_share=0.10,
        tax_share=0.035,
        rent_monthly=95_000,
        comms_monthly=25_000,
        cash_share=0.05,
        owner_share=0.45,
        opening_balance=350_000,
    ),
    Profile(
        key="06_transit_scheme",
        org='ООО «Вектор Плюс»',
        inn="7736009911",
        industry="wholesale",
        title="Транзитная схема: приток и списание в 1–2 дня, налогов нет",
        expected="DECLINE",
        revenue_base=8_000_000,
        revenue_growth=0.0,
        season=flat(),
        customers=9,
        top1_share=0.30,
        supplier_share=0.72,
        payroll_share=0.0,
        tax_share=0.004,
        rent_monthly=0,
        comms_monthly=0,
        bank_fee_monthly=12_000,
        cash_share=0.36,
        transit_share=0.82,
        owner_share=0.0,
        opening_balance=40_000,
    ),
    Profile(
        key="07_cash_out",
        org='ООО «Аргус Трейд»',
        inn="7743221100",
        industry="wholesale",
        title="Обналичивание: снятия и подотчёт свыше трети оборота",
        expected="MANUAL_REVIEW",
        revenue_base=12_500_000,
        revenue_growth=0.0,
        season=flat(),
        customers=14,
        top1_share=0.26,
        supplier_share=0.30,
        payroll_share=0.03,
        tax_share=0.011,
        rent_monthly=60_000,
        comms_monthly=15_000,
        cash_share=0.38,
        owner_share=0.14,
        opening_balance=180_000,
    ),
    Profile(
        key="08_revenue_collapse",
        org='ООО «Мебельный Дом Юг»',
        inn="2312009988",
        industry="manufacturing",
        title="Схлопывание оборота в последнем квартале",
        expected="DECLINE",
        revenue_base=11_000_000,
        revenue_growth=0.0,
        season=flat(),
        customers=16,
        top1_share=0.24,
        supplier_share=0.66,
        payroll_share=0.16,
        tax_share=0.045,
        rent_monthly=340_000,
        comms_monthly=45_000,
        owner_share=0.05,
        loan_payment=450_000,
        loan_interest=140_000,
        has_enforcement=True,
        collapse_factor=0.32,
        opening_balance=1_500_000,
    ),
]

BY_KEY = {p.key: p for p in PROFILES}
