"""Типизированные объекты, которыми обмениваются шаги конвейера."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    # приток
    REVENUE_OPERATING = "REVENUE_OPERATING"
    ACQUIRING_IN = "ACQUIRING_IN"
    OTHER_INCOME = "OTHER_INCOME"
    SUPPLIER_REFUND = "SUPPLIER_REFUND"
    FIN_LOAN_IN = "FIN_LOAN_IN"
    OWNER_CONTRIBUTION = "OWNER_CONTRIBUTION"
    DEPOSIT_IN = "DEPOSIT_IN"
    LOAN_REPAY_IN = "LOAN_REPAY_IN"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    # отток
    REVENUE_RETURN = "REVENUE_RETURN"
    OPEX_SUPPLIERS = "OPEX_SUPPLIERS"
    OPEX_PAYROLL = "OPEX_PAYROLL"
    OPEX_PAYROLL_TAX = "OPEX_PAYROLL_TAX"
    OPEX_TAXES = "OPEX_TAXES"
    OPEX_RENT = "OPEX_RENT"
    OPEX_COMMS = "OPEX_COMMS"
    OPEX_BANK_FEES = "OPEX_BANK_FEES"
    INSURANCE = "INSURANCE"
    CUSTOMS = "CUSTOMS"
    LEASING = "LEASING"
    FACTORING = "FACTORING"
    CAPEX = "CAPEX"
    FIN_LOAN_OUT = "FIN_LOAN_OUT"
    FIN_INTEREST = "FIN_INTEREST"
    OWNER_WITHDRAWAL = "OWNER_WITHDRAWAL"
    LOAN_ISSUE_OUT = "LOAN_ISSUE_OUT"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    CASH_PROXY = "CASH_PROXY"
    DEPOSIT_OUT = "DEPOSIT_OUT"
    ACQUIRING_OUT = "ACQUIRING_OUT"
    # обе стороны
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    ENFORCEMENT = "ENFORCEMENT"
    TRANSIT_SUSPECT = "TRANSIT_SUSPECT"
    UNCLASSIFIED = "UNCLASSIFIED"


CATEGORY_RU = {
    "REVENUE_OPERATING": "Выручка от покупателей",
    "ACQUIRING_IN": "Эквайринг, поступление",
    "OTHER_INCOME": "Прочие поступления",
    "SUPPLIER_REFUND": "Возврат от поставщика",
    "FIN_LOAN_IN": "Получение кредитов и займов",
    "OWNER_CONTRIBUTION": "Взнос собственника",
    "DEPOSIT_IN": "Возврат депозита",
    "LOAN_REPAY_IN": "Возврат выданного займа",
    "CASH_DEPOSIT": "Внесение наличных",
    "REVENUE_RETURN": "Возврат покупателю",
    "OPEX_SUPPLIERS": "Поставщики и подрядчики",
    "OPEX_PAYROLL": "Заработная плата",
    "OPEX_PAYROLL_TAX": "Страховые взносы и НДФЛ",
    "OPEX_TAXES": "Налоги",
    "OPEX_RENT": "Аренда и коммунальные",
    "OPEX_COMMS": "Связь и ИТ",
    "OPEX_BANK_FEES": "Комиссии банка",
    "INSURANCE": "Страхование",
    "CUSTOMS": "Таможенные платежи",
    "LEASING": "Лизинг",
    "FACTORING": "Факторинг",
    "CAPEX": "Капитальные вложения",
    "FIN_LOAN_OUT": "Погашение кредитов и займов",
    "FIN_INTEREST": "Проценты по кредитам",
    "OWNER_WITHDRAWAL": "Вывод собственнику",
    "LOAN_ISSUE_OUT": "Выдача займов",
    "CASH_WITHDRAWAL": "Снятие наличных",
    "CASH_PROXY": "Подотчёт и хознужды",
    "DEPOSIT_OUT": "Размещение депозита",
    "ACQUIRING_OUT": "Эквайринг, списание",
    "INTERNAL_TRANSFER": "Перевод между своими счетами",
    "ENFORCEMENT": "Принудительное взыскание",
    "TRANSIT_SUSPECT": "Транзитная операция",
    "UNCLASSIFIED": "Не классифицировано",
}

# Категории, формирующие операционный отток
OPERATING_OUTFLOW = frozenset(
    {
        Category.OPEX_SUPPLIERS,
        Category.OPEX_PAYROLL,
        Category.OPEX_PAYROLL_TAX,
        Category.OPEX_TAXES,
        Category.OPEX_RENT,
        Category.OPEX_COMMS,
        Category.OPEX_BANK_FEES,
        Category.INSURANCE,
        Category.CUSTOMS,
        Category.LEASING,
        Category.FACTORING,
        # снятия и подотчёт — деньги, физически покинувшие бизнес; в свободном
        # потоке их учитывать обязательно, иначе «обнальный» профиль показывает
        # завышенную способность обслуживать долг
        Category.CASH_WITHDRAWAL,
        Category.CASH_PROXY,
    }
)

# Притоки, не являющиеся выручкой: вычитаются из валового притока
NON_REVENUE_INFLOW = frozenset(
    {
        Category.INTERNAL_TRANSFER,
        Category.FIN_LOAN_IN,
        Category.OWNER_CONTRIBUTION,
        Category.DEPOSIT_IN,
        Category.SUPPLIER_REFUND,
        Category.LOAN_REPAY_IN,
        Category.CASH_DEPOSIT,
        Category.TRANSIT_SUSPECT,
    }
)

# Категории, которые не участвуют в поиске транзитных пар:
# это нормальные операционные и обязательные платежи
# ВАЖНО: расчёты с поставщиками (OPEX_SUPPLIERS) намеренно НЕ исключены —
# транзит всегда маскируется именно под оплату поставщикам. Защита от ложных
# срабатываний обеспечивается строгостью самого сопоставления (1:1 либо
# 1:N на одного контрагента), а не отсечением категории.
NON_TRANSIT_OUTFLOW = frozenset(
    {
        Category.OPEX_PAYROLL,
        Category.OPEX_PAYROLL_TAX,
        Category.OPEX_TAXES,
        Category.OPEX_RENT,
        Category.OPEX_COMMS,
        Category.OPEX_BANK_FEES,
        Category.INSURANCE,
        Category.CUSTOMS,
        Category.LEASING,
        Category.FIN_LOAN_OUT,
        Category.FIN_INTEREST,
        Category.ENFORCEMENT,
        Category.INTERNAL_TRANSFER,
        Category.REVENUE_RETURN,
        Category.CAPEX,
    }
)

# Признаки реальной хозяйственной деятельности (индикатор T6)
ACTIVITY_MARKERS = frozenset(
    {Category.OPEX_RENT, Category.OPEX_COMMS, Category.OPEX_BANK_FEES}
)


class Transaction(BaseModel):
    row_no: int
    date: date
    doc_type: str | None = None
    doc_no: str | None = None
    account_no: str | None = None
    bank_name: str | None = None
    corr_account: str | None = None
    counterparty: str | None = None
    contract: str | None = None
    purpose: str | None = None
    inflow: float = 0.0
    outflow: float = 0.0
    balance_after: float | None = None

    category: Category = Category.UNCLASSIFIED
    category_source: str | None = None
    link_id: str | None = None
    excluded_reason: str | None = None

    @property
    def amount(self) -> float:
        return self.inflow if self.inflow else self.outflow

    @property
    def is_inflow(self) -> bool:
        return self.inflow > 0

    @property
    def month(self) -> str:
        return self.date.strftime("%Y-%m")


class CardMeta(BaseModel):
    organization: str | None = None
    inn: str | None = None
    period_from: date | None = None
    period_to: date | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    stated_debit_turnover: float | None = None
    stated_credit_turnover: float | None = None
    accounts: list[str] = Field(default_factory=list)
    banks: list[str] = Field(default_factory=list)
    source_rows: int = 0
    bad_date_rows: int = 0


class Check(BaseModel):
    code: str
    name: str
    passed: bool
    critical: bool
    detail: str = ""


class DataQuality(BaseModel):
    checks: list[Check] = Field(default_factory=list)
    passed: bool = True

    def failed_critical(self) -> list:
        return [c for c in self.checks if c.critical and not c.passed]


class MonthlyPoint(BaseModel):
    month: str
    gross_inflow: float = 0.0
    qualified_inflow: float = 0.0
    adjusted_revenue: float = 0.0
    operating_outflow: float = 0.0
    fcf: float = 0.0


class Exclusion(BaseModel):
    category: str
    label: str
    amount: float
    share: float
    rows: list[int] = Field(default_factory=list)


class Volumes(BaseModel):
    gross_inflow: float = 0.0
    gross_outflow: float = 0.0
    qualified_inflow: float = 0.0
    adjusted_revenue: float = 0.0
    operating_outflow: float = 0.0
    fcf: float = 0.0
    exclusions: list[Exclusion] = Field(default_factory=list)


class Status(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    NA = "NA"


class Indicator(BaseModel):
    code: str
    name: str
    value: float | None = None
    display: str = ""
    status: Status = Status.NA
    explanation: str = ""
    rows: list[int] = Field(default_factory=list)


class LimitResult(BaseModel):
    constraints: dict = Field(default_factory=dict)
    constraint_labels: dict = Field(default_factory=dict)
    constraint_formulas: dict = Field(default_factory=dict)
    binding_constraint: str | None = None
    base: float = 0.0
    multiplier: float = 1.0
    final: float = 0.0
    range_low: float = 0.0
    range_high: float = 0.0


class Decision(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    DECLINE = "DECLINE"


DECISION_RU = {
    "AUTO_APPROVE": "Автоматическое одобрение",
    "MANUAL_REVIEW": "На рассмотрение андеррайтера",
    "DECLINE": "Отказ",
}


class DecisionResult(BaseModel):
    code: Decision
    stop_factors: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class CounterpartyStat(BaseModel):
    name: str
    amount: float
    share: float
    operations: int


class Analysis(BaseModel):
    analysis_id: str
    rules_version: str
    created_at: str
    source_filename: str
    source_sha256: str
    meta: CardMeta
    industry: str
    data_quality: DataQuality
    volumes: Volumes
    monthly: list[MonthlyPoint] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    limit: LimitResult = Field(default_factory=LimitResult)
    decision: DecisionResult = DecisionResult(code=Decision.MANUAL_REVIEW)
    top_inflow: list[CounterpartyStat] = Field(default_factory=list)
    top_outflow: list[CounterpartyStat] = Field(default_factory=list)
    unclassified_top: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    transactions: list[Transaction] = Field(default_factory=list)
