"""Ридер обязан переживать свойства печатной формы 1С, а не идеальной таблицы."""

import pytest

from potok51.readers.base import ReadError
from potok51.readers.card51_xlsx import find_header, parse_amount, parse_date, read_card
from potok51.readers.grid import load_grid


@pytest.mark.parametrize("raw,expected", [
    ("1 234 567,89", 1234567.89),
    ("1 234 567,89", 1234567.89),
    ("3 500,00", 3500.0),
    ("1.234.567,89", 1234567.89),
    (12345.67, 12345.67),
    ("", 0.0),
    (None, 0.0),
    ("не число", 0.0),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["05.03.2026", "05.03.2026 12:04:07", "2026-03-05"])
def test_parse_date_formats(raw):
    d = parse_date(raw)
    assert (d.day, d.month, d.year) == (5, 3, 2026)


def test_parse_date_rejects_garbage():
    assert parse_date("Сальдо на начало") is None


def test_header_found_below_preamble(healthy_card):
    """P1: шапка не в первой строке — над ней организация, ИНН и название отчёта."""
    grid = load_grid(healthy_card)
    header = find_header(grid)
    assert header > 0
    assert "Период" in grid[header]
    assert "Дебет" in grid[header]


def test_reader_extracts_meta(healthy_card):
    txs, meta = read_card(healthy_card)
    assert meta.inn == "7712345678"
    assert meta.organization.startswith("ООО")
    assert len(meta.accounts) == 2          # P7: два расчётных счёта в одной карточке
    assert meta.opening_balance is not None
    assert meta.stated_debit_turnover is not None


def test_turnovers_match_file_totals(healthy_card):
    """P6: строки итогов не должны попасть в операции и обязаны сойтись с суммой строк."""
    txs, meta = read_card(healthy_card)
    assert sum(t.inflow for t in txs) == pytest.approx(meta.stated_debit_turnover, abs=1.0)
    assert sum(t.outflow for t in txs) == pytest.approx(meta.stated_credit_turnover, abs=1.0)


def test_multirow_operation_is_glued(healthy_card):
    """P2: договор и назначение лежат в отдельных строках блока операции."""
    txs, _ = read_card(healthy_card)
    with_contract = [t for t in txs if t.contract]
    assert with_contract, "ни у одной операции не разобран договор"
    sample = with_contract[0]
    assert sample.purpose and "Оплата" in sample.purpose
    assert sample.corr_account and not sample.corr_account.startswith("51")


def test_inline_layout_is_supported(cards):
    """Вариант выгрузки, где вся аналитика — одна ячейка с переносами строк."""
    txs, meta = read_card(cards["02_retail_acquiring"])
    assert len(txs) > 100
    # аналитика склеена из одной ячейки: контрагент и назначение разделились верно
    acq = [t for t in txs if t.counterparty and "эквайринг" in t.counterparty.lower()]
    assert acq, "поступления эквайринга не разобраны"
    assert all("возмещение по операциям" in (t.purpose or "").lower() for t in acq)


def test_every_operation_has_one_direction(healthy_card):
    txs, _ = read_card(healthy_card)
    assert all((t.inflow > 0) != (t.outflow > 0) for t in txs)


def test_unsupported_extension(tmp_path):
    bad = tmp_path / "card.csv"
    bad.write_text("a;b;c")
    with pytest.raises(ReadError):
        read_card(bad)


def test_file_without_header(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["просто", "какой-то", "файл"])
    path = tmp_path / "junk.xlsx"
    wb.save(path)
    with pytest.raises(ReadError):
        read_card(path)
