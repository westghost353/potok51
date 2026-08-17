"""HTML-отчёт кредитного аналитика: один самодостаточный файл без внешних зависимостей."""

from __future__ import annotations

import html as html_escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import INDUSTRY_RU
from ..models import CATEGORY_RU, DECISION_RU, Analysis
from .charts import constraints_chart, monthly_chart, waterfall

TEMPLATES = Path(__file__).parent / "templates"


def _money(value) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ")


MONTHS_RU = ("янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек")


def _month_ru(value: str) -> str:
    try:
        year, month = value.split("-")
        return f"{MONTHS_RU[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return value


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}\u00a0%".replace(".", ",")


def _rows_table_factory(analysis: Analysis):
    by_row = {t.row_no: t for t in analysis.transactions}

    def rows_table(row_nos: list, limit: int = 120) -> str:
        txs = [by_row[r] for r in row_nos if r in by_row]
        txs.sort(key=lambda t: -t.amount)
        shown = txs[:limit]
        head = (
            "<table><thead><tr><th>Строка</th><th>Дата</th><th>Контрагент</th>"
            "<th>Назначение</th><th>Корсчёт</th><th>Категория</th>"
            "<th class='num'>Сумма, ₽</th></tr></thead><tbody>"
        )
        body = []
        for t in shown:
            body.append(
                "<tr><td>{row}</td><td>{date}</td><td>{cp}</td><td>{purpose}</td>"
                "<td>{acc}</td><td>{cat}</td><td class='num'>{amount}</td></tr>".format(
                    row=t.row_no,
                    date=t.date.strftime("%d.%m.%Y"),
                    cp=html_escape.escape(t.counterparty or "—"),
                    purpose=html_escape.escape((t.purpose or "—")[:100]),
                    acc=html_escape.escape(t.corr_account or "—"),
                    cat=CATEGORY_RU.get(t.category.value, t.category.value),
                    amount=_money(t.amount),
                )
            )
        tail = "</tbody></table>"
        if len(txs) > limit:
            tail += (
                f"<p class='sub'>Показаны {limit} крупнейших из {len(txs)} операций. "
                "Полный перечень — в выгрузке Excel.</p>"
            )
        return head + "".join(body) + tail

    return rows_table


def render_html(analysis: Analysis) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["money"] = _money
    env.filters["pct"] = _pct
    env.filters["month_ru"] = _month_ru
    template = env.get_template("report.html.j2")

    months = max(len(analysis.monthly), 1)
    return template.render(
        a=analysis,
        months=months,
        ind={i.code: i for i in analysis.indicators},
        industry_ru=INDUSTRY_RU.get(analysis.industry, analysis.industry),
        decision_ru=DECISION_RU[analysis.decision.code.value],
        chart_monthly=monthly_chart(analysis.monthly),
        chart_waterfall=waterfall(analysis.volumes),
        chart_constraints=constraints_chart(analysis.limit),
        rows_table=_rows_table_factory(analysis),
    )


def write_html(analysis: Analysis, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(analysis), encoding="utf-8")
    return path
