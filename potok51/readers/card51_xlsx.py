"""Ридер карточки счёта 51 из 1С 8.3 (.xlsx / .xls).

Разбор устроен вокруг того факта, что выгрузка 1С — не таблица данных,
а печатная форма. Отсюда все меры: автопоиск шапки, двухуровневые
заголовки, склейка многострочных операций, отбраковка строк итогов
с сохранением их значений для контроля целостности.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from ..models import CardMeta, Transaction
from .base import ReadError
from .grid import load_grid

DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
)

HEADER_KEYWORDS = ("период", "документ", "дебет", "кредит", "сальдо", "аналитика")

TOTAL_MARKERS = (
    "сальдо на начало",
    "сальдо на конец",
    "обороты за период",
    "итого",
    "оборот за период",
)

ACCOUNT_SECTION_RE = re.compile(
    r"(расчетн\w+ счет|расчётн\w+ счет|счет №|р/с)\s*:?\s*(\d{20})?", re.IGNORECASE
)
ACCOUNT_NO_RE = re.compile(r"\b(\d{20})\b")
INN_RE = re.compile(r"\bИНН[:\s]*(\d{10}|\d{12})\b", re.IGNORECASE)
AMOUNT_CLEAN_RE = re.compile(r"[^\d,.\-]")


def parse_amount(raw: str | None) -> float:
    """Суммы в выгрузках приходят текстом: '1 234 567,89', '1\xa0234,89'."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).replace("\xa0", " ").strip()
    if not text:
        return 0.0
    text = AMOUNT_CLEAN_RE.sub("", text)
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


def parse_date(raw: str | None):
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{2}\.\d{2}\.\d{4})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d.%m.%Y").date()
        except ValueError:
            return None
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("ё", "е")).strip().lower()


def find_header(grid: list[list[str]], scan_rows: int = 40) -> int:
    """Строка заголовка — первая, где встречается 3+ ключевых слова шапки."""
    for idx, row in enumerate(grid[:scan_rows]):
        joined = _norm(" ".join(row))
        hits = sum(1 for kw in HEADER_KEYWORDS if kw in joined)
        if hits >= 3:
            return idx
    raise ReadError(
        "Не найдена строка заголовка карточки счёта. "
        "Ожидались колонки: Период, Документ, Дебет, Кредит, Сальдо."
    )


def build_column_map(grid: list[list[str]], header_row: int) -> dict[str, int]:
    """Заголовок 1С двухуровневый: 'Дебет' сверху, 'Счет'/'Сумма' снизу."""
    width = max(len(grid[header_row]), len(grid[header_row + 1]) if header_row + 1 < len(grid) else 0)
    combined: list[str] = []
    for c in range(width):
        top = grid[header_row][c] if c < len(grid[header_row]) else ""
        sub = ""
        if header_row + 1 < len(grid) and c < len(grid[header_row + 1]):
            sub = grid[header_row + 1][c]
        combined.append(_norm(f"{top} {sub}"))

    cols: dict[str, int] = {}
    for c, text in enumerate(combined):
        if not text:
            continue
        if "период" in text or text in ("дата",):
            cols.setdefault("date", c)
        elif "документ" in text:
            cols.setdefault("doc", c)
        elif "аналитика дт" in text:
            cols.setdefault("analytics_dt", c)
        elif "аналитика кт" in text:
            cols.setdefault("analytics_kt", c)
        elif "дебет" in text and ("счет" in text or "счёт" in text or "кор" in text):
            cols.setdefault("debit_acc", c)
        elif "дебет" in text:
            cols.setdefault("debit_amt", c)
        elif "кредит" in text and ("счет" in text or "счёт" in text or "кор" in text):
            cols.setdefault("credit_acc", c)
        elif "кредит" in text:
            cols.setdefault("credit_amt", c)
        elif "сальдо" in text:
            cols.setdefault("balance", c)
        elif "назначение" in text:
            cols.setdefault("purpose", c)
    missing = {"date", "debit_amt", "credit_amt"} - cols.keys()
    if missing:
        raise ReadError(f"В шапке не найдены обязательные колонки: {sorted(missing)}")
    return cols


def _get(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx] or ""


def _is_total_row(row: list[str]) -> str | None:
    joined = _norm(" ".join(row[:4]))
    for marker in TOTAL_MARKERS:
        if joined.startswith(marker):
            return marker
    return None


def read_card(path: Path) -> tuple[list[Transaction], CardMeta]:
    grid = load_grid(Path(path))
    if not grid:
        raise ReadError("Файл пуст")

    header_row = find_header(grid)
    cols = build_column_map(grid, header_row)
    meta = CardMeta(source_rows=len(grid))

    # --- преамбула: организация, ИНН, период --------------------------------
    preamble = " ".join(" ".join(r) for r in grid[:header_row])
    m = INN_RE.search(preamble)
    if m:
        meta.inn = m.group(1)
    for row in grid[:header_row]:
        text = " ".join(x for x in row if x).strip()
        if not text:
            continue
        if meta.organization is None and not _norm(text).startswith("карточка"):
            meta.organization = text[:200]
        dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
        if len(dates) >= 2 and meta.period_from is None:
            meta.period_from = parse_date(dates[0])
            meta.period_to = parse_date(dates[-1])

    transactions: list[Transaction] = []
    current_account: str | None = None
    current_bank: str | None = None
    block: list[list[str]] = []
    block_row_no = 0
    bad_dates = 0

    def flush() -> None:
        nonlocal block
        if block:
            tx = _build_transaction(block, block_row_no, cols, current_account, current_bank)
            if tx is not None:
                transactions.append(tx)
        block = []

    data_start = header_row + 1
    # если вторая строка шапки — подзаголовки, пропускаем и её
    if data_start < len(grid):
        sub = _norm(" ".join(grid[data_start]))
        if sub and all(w in ("счет", "счёт", "сумма", "", "д", "к") for w in sub.split()):
            data_start += 1

    for idx in range(data_start, len(grid)):
        row = grid[idx]
        if not any(x for x in row):
            continue

        marker = _is_total_row(row)
        if marker:
            flush()
            _absorb_totals(meta, row, cols, marker)
            continue

        first_cells = " ".join(x for x in row[:3] if x)
        acc_match = ACCOUNT_NO_RE.search(first_cells)
        if acc_match and not _get(row, cols.get("debit_amt")) and not _get(row, cols.get("credit_amt")):
            flush()
            current_account = acc_match.group(1)
            if current_account not in meta.accounts:
                meta.accounts.append(current_account)
            bank = re.sub(r".*?\d{20}[,;]?\s*", "", first_cells).strip(" ,;")
            current_bank = bank or None
            if current_bank and current_bank not in meta.banks:
                meta.banks.append(current_bank)
            continue

        raw_date = _get(row, cols["date"])
        if _norm(raw_date) in ("период", "дата"):
            continue  # вторая строка двухуровневой шапки
        parsed = parse_date(raw_date)
        if parsed is not None:
            flush()
            block_row_no = idx + 1
            block = [row]
        elif block:
            block.append(row)
        elif raw_date:
            bad_dates += 1

    flush()
    meta.bad_date_rows = bad_dates
    if not transactions:
        raise ReadError("В файле не найдено ни одной операции по счёту 51")
    transactions.sort(key=lambda t: (t.date, t.row_no))
    if meta.period_from is None:
        meta.period_from = transactions[0].date
    if meta.period_to is None:
        meta.period_to = transactions[-1].date
    return transactions, meta


def _absorb_totals(meta: CardMeta, row: list[str], cols: dict[str, int], marker: str) -> None:
    debit = parse_amount(_get(row, cols.get("debit_amt")))
    credit = parse_amount(_get(row, cols.get("credit_amt")))
    balance = parse_amount(_get(row, cols.get("balance")))
    if marker == "сальдо на начало":
        meta.opening_balance = debit or balance
    elif marker == "сальдо на конец":
        meta.closing_balance = debit or balance
    elif marker in ("обороты за период", "оборот за период", "итого"):
        if debit or credit:
            meta.stated_debit_turnover = debit
            meta.stated_credit_turnover = credit


def _build_transaction(
    block: list[list[str]],
    row_no: int,
    cols: dict[str, int],
    account: str | None,
    bank: str | None,
):
    head = block[0]
    tx_date = parse_date(_get(head, cols["date"]))
    if tx_date is None:
        return None

    def collect(key: str) -> str:
        idx = cols.get(key)
        if idx is None:
            return ""
        parts: list[str] = []
        for row in block:
            value = _get(row, idx)
            if not value:
                continue
            for line in str(value).splitlines():
                line = line.strip()
                if line and line not in parts:
                    parts.append(line)
        return "\n".join(parts)

    inflow = parse_amount(_get(head, cols.get("debit_amt")))
    outflow = parse_amount(_get(head, cols.get("credit_amt")))
    if not inflow and not outflow:
        for row in block[1:]:
            inflow = inflow or parse_amount(_get(row, cols.get("debit_amt")))
            outflow = outflow or parse_amount(_get(row, cols.get("credit_amt")))
    if not inflow and not outflow:
        return None

    debit_acc = collect("debit_acc").split("\n")[0] if cols.get("debit_acc") is not None else ""
    credit_acc = collect("credit_acc").split("\n")[0] if cols.get("credit_acc") is not None else ""
    is_inflow = inflow > 0
    # для счёта 51: поступление — Дт 51 Кт X, списание — Дт X Кт 51
    corr = credit_acc if is_inflow else debit_acc
    if corr.startswith("51"):
        corr = debit_acc if is_inflow else credit_acc

    analytics_own = collect("analytics_dt") if is_inflow else collect("analytics_kt")
    analytics_corr = collect("analytics_kt") if is_inflow else collect("analytics_dt")
    lines = [line for line in analytics_corr.split("\n") if line]
    counterparty = lines[0] if lines else None
    contract = next((line for line in lines[1:] if _norm(line).startswith("договор")), None)
    purpose_parts = [line for line in lines[1:] if line != contract]
    explicit_purpose = collect("purpose")
    if explicit_purpose:
        purpose_parts.append(explicit_purpose)
    doc = collect("doc")
    doc_lines = [line for line in doc.split("\n") if line]
    doc_type = doc_lines[0] if doc_lines else None
    doc_no = None
    if doc_type:
        m = re.search(r"№?\s*([\w-]+)\s+от\s+\d{2}\.\d{2}\.\d{4}", doc_type)
        if m:
            doc_no = m.group(1)
    if len(doc_lines) > 1:
        purpose_parts.extend(doc_lines[1:])

    own_account = account
    if not own_account and analytics_own:
        m = ACCOUNT_NO_RE.search(analytics_own)
        if m:
            own_account = m.group(1)

    return Transaction(
        row_no=row_no,
        date=tx_date,
        doc_type=doc_type,
        doc_no=doc_no,
        account_no=own_account,
        bank_name=bank,
        corr_account=corr or None,
        counterparty=counterparty,
        contract=contract,
        purpose=" ".join(purpose_parts).strip() or None,
        inflow=inflow,
        outflow=outflow,
        balance_after=parse_amount(_get(head, cols.get("balance"))) or None,
    )
