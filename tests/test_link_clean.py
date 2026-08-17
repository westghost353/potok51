"""Сопоставление пар и арифметика очистки потока."""

from datetime import date

import pytest

from potok51.classify import classify
from potok51.clean import compute_monthly, compute_volumes
from potok51.config import DEFAULT_CONFIG
from potok51.link import detect_transit, link_all, link_internal_transfers
from potok51.models import Category, Transaction
from potok51.readers.card51_xlsx import read_card


def tx(row, day, corr=None, cp=None, purpose=None, inflow=0.0, outflow=0.0, month=3):
    return Transaction(row_no=row, date=date(2026, month, day), corr_account=corr,
                       counterparty=cp, purpose=purpose, inflow=inflow, outflow=outflow)


def test_transit_pair_is_detected():
    txs = [
        tx(1, 5, "62.01", "ООО «Плательщик»", "Оплата по договору", inflow=5_000_000),
        tx(2, 6, "60.01", "ООО «Получатель»", "Оплата по счету за товар", outflow=4_900_000),
    ]
    classify(txs)
    pairs, volume = detect_transit(txs, DEFAULT_CONFIG)
    assert pairs == 1
    assert volume == pytest.approx(5_000_000)
    assert txs[0].category == Category.TRANSIT_SUSPECT
    assert txs[0].link_id == txs[1].link_id


def test_transit_ignores_obligatory_payments():
    """Зарплата и налоги на следующий день после поступления — не транзит."""
    txs = [
        tx(1, 5, "62.01", "ООО «Покупатель»", "Оплата за товар", inflow=1_000_000),
        tx(2, 6, "70", "Сотрудники", "Заработная плата за 02.2026 по реестру № 3", outflow=980_000),
    ]
    classify(txs)
    pairs, _ = detect_transit(txs, DEFAULT_CONFIG)
    assert pairs == 0


def test_transit_ignores_payment_outside_window():
    txs = [
        tx(1, 5, "62.01", "ООО «Покупатель»", "Оплата за товар", inflow=1_000_000),
        tx(2, 20, "60.01", "ООО «Поставщик»", "Оплата по счету", outflow=1_000_000),
    ]
    classify(txs)
    pairs, _ = detect_transit(txs, DEFAULT_CONFIG)
    assert pairs == 0


def test_transit_ignores_mismatched_amount():
    txs = [
        tx(1, 5, "62.01", "ООО «Покупатель»", "Оплата за товар", inflow=1_000_000),
        tx(2, 6, "60.01", "ООО «Поставщик»", "Оплата по счету", outflow=400_000),
    ]
    classify(txs)
    pairs, _ = detect_transit(txs, DEFAULT_CONFIG)
    assert pairs == 0


def test_transit_one_to_many_same_counterparty():
    txs = [
        tx(1, 5, "62.01", "ООО «Покупатель»", "Оплата за товар", inflow=1_000_000),
        tx(2, 6, "60.01", "ООО «Прокладка»", "Оплата по счету 1", outflow=500_000),
        tx(3, 6, "60.01", "ООО «Прокладка»", "Оплата по счету 2", outflow=490_000),
    ]
    classify(txs)
    pairs, _ = detect_transit(txs, DEFAULT_CONFIG)
    assert pairs == 1


def test_internal_transfer_pairs_are_excluded():
    txs = [
        tx(1, 5, "51", "ООО «Клиент»", "Перевод между счетами организации", outflow=2_000_000),
        tx(2, 5, "51", "ООО «Клиент»", "Пополнение расчетного счета организации", inflow=2_000_000),
    ]
    classify(txs)
    assert link_internal_transfers(txs) == 1
    assert all(t.excluded_reason == "internal_transfer" for t in txs)


def test_cleaning_identity_holds(healthy_card):
    """Валовой приток минус все исключения равен квалифицированному притоку до копейки."""
    txs, meta = read_card(healthy_card)
    classify(txs, meta.inn)
    link_all(txs, DEFAULT_CONFIG)
    v = compute_volumes(txs)
    assert v.gross_inflow - sum(e.amount for e in v.exclusions) == pytest.approx(
        v.qualified_inflow, abs=0.01
    )


def test_loans_and_owner_money_are_not_revenue():
    txs = [
        tx(1, 5, "62.01", "ООО «Покупатель»", "Оплата за товар", inflow=3_000_000),
        tx(2, 6, "66.01", "Банк", "Выдача кредита по кредитному договору", inflow=10_000_000),
        tx(3, 7, "75.01", "Учредитель", "Внесение средств учредителем", inflow=2_000_000),
    ]
    classify(txs)
    v = compute_volumes(txs)
    assert v.gross_inflow == pytest.approx(15_000_000)
    assert v.qualified_inflow == pytest.approx(3_000_000)


def test_monthly_series_covers_every_month(healthy_card):
    txs, meta = read_card(healthy_card)
    classify(txs, meta.inn)
    link_all(txs, DEFAULT_CONFIG)
    monthly = compute_monthly(txs)
    assert len(monthly) == 12
    assert monthly == sorted(monthly, key=lambda m: m.month)
    assert all(m.fcf == pytest.approx(m.adjusted_revenue - m.operating_outflow, abs=0.01)
               for m in monthly)
