"""Каждое правило справочника проверяется положительным и отрицательным кейсом."""

from datetime import date

import pytest

from potok51.classify import auto_classified_share, classify
from potok51.models import Category, Transaction
from potok51.rules.accounts import account_category
from potok51.rules.patterns import best_pattern, normalize_text
from potok51.readers.card51_xlsx import read_card


def tx(corr=None, purpose=None, counterparty=None, inflow=0.0, outflow=0.0):
    return Transaction(row_no=1, date=date(2026, 3, 5), corr_account=corr,
                       purpose=purpose, counterparty=counterparty,
                       inflow=inflow, outflow=outflow)


@pytest.mark.parametrize("corr,inflow,expected", [
    ("62.01", True, Category.REVENUE_OPERATING),
    ("62.01", False, Category.REVENUE_RETURN),
    ("60.01", False, Category.OPEX_SUPPLIERS),
    ("60.01", True, Category.SUPPLIER_REFUND),
    ("66.01", False, Category.FIN_LOAN_OUT),
    ("70", False, Category.OPEX_PAYROLL),
    ("57.03", True, Category.ACQUIRING_IN),
    ("51", False, Category.INTERNAL_TRANSFER),
    ("76.09", False, None),
])
def test_account_map(corr, inflow, expected):
    assert account_category(corr, inflow) == expected


def test_vat_mention_does_not_make_payment_a_tax():
    """Регрессия: «в т.ч. НДС 20 %» есть почти в каждом коммерческом платеже."""
    t = tx(corr="60.01", counterparty="ООО «Поставщик»",
           purpose="Оплата по счету 145 за товар, в т.ч. НДС 20%", outflow=500_000)
    classify([t])
    assert t.category == Category.OPEX_SUPPLIERS


def test_real_tax_payment_is_recognised():
    t = tx(corr="68.90", counterparty="УФК по г. Москве (Казначейство России)",
           purpose="Единый налоговый платеж (ЕНС)", outflow=300_000)
    classify([t])
    assert t.category == Category.OPEX_TAXES


def test_ndfl_counts_as_payroll_burden():
    t = tx(corr="68.01", counterparty="УФК по г. Москве (ИФНС № 7)",
           purpose="НДФЛ с доходов, источником которых является налоговый агент", outflow=90_000)
    classify([t])
    assert t.category == Category.OPEX_PAYROLL_TAX


def test_social_contributions_not_swallowed_by_treasury_pattern():
    t = tx(corr="69.01", counterparty="УФК по г. Москве (СФР)",
           purpose="Страховые взносы по единому тарифу за отчетный период", outflow=210_000)
    classify([t])
    assert t.category == Category.OPEX_PAYROLL_TAX


def test_rent_overrides_supplier_account():
    """Аренда проводится по 60, но нужна отдельно — это признак реальной деятельности."""
    t = tx(corr="60.01", counterparty="ООО «УК Меркурий»",
           purpose="Арендная плата за 03.2026, в т.ч. НДС 20%", outflow=450_000)
    classify([t])
    assert t.category == Category.OPEX_RENT


def test_enforcement_wins_over_other_settlements():
    t = tx(corr="76.02", counterparty="Межрайонный ОСП (ФССП)",
           purpose="Списание по исполнительному документу № 2-1145/2026", outflow=800_000)
    classify([t])
    assert t.category == Category.ENFORCEMENT


def test_ip_self_transfer_is_owner_withdrawal():
    t = tx(corr="76.09", counterparty="ИП Ковалёв А.С.",
           purpose="Перевод собственных средств предпринимателя на личную карту", outflow=1_000_000)
    classify([t])
    assert t.category == Category.OWNER_WITHDRAWAL


def test_cash_for_household_needs():
    t = tx(corr="71.01", purpose="Перечисление в подотчет на хозяйственные нужды", outflow=200_000)
    classify([t])
    assert t.category in (Category.CASH_WITHDRAWAL, Category.CASH_PROXY)


def test_own_inn_forces_internal_transfer():
    t = tx(corr="62.01", counterparty="ООО «Клиент» ИНН 7712345678",
           purpose="Оплата по счету", inflow=1_000_000)
    classify([t], client_inn="7712345678")
    assert t.category == Category.INTERNAL_TRANSFER


def test_unknown_payment_stays_unclassified():
    t = tx(corr=None, counterparty="Неизвестно", purpose="Перевод", outflow=1_000)
    classify([t])
    assert t.category == Category.UNCLASSIFIED


def test_normalize_text_handles_yo_and_spaces():
    assert normalize_text("Платёж", None, "  ЗА   Аренду ") == "платеж за аренду"


def test_auto_classified_share_on_real_card(healthy_card):
    txs, meta = read_card(healthy_card)
    classify(txs, meta.inn)
    assert auto_classified_share(txs) >= 0.95
