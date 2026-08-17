"""Командный режим — для пакетного прогона и регрессионных проверок."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, INDUSTRY_RU
from .models import DECISION_RU
from .pipeline import analyze_file
from .readers.base import ReadError
from .report.excel import write_excel
from .report.html import write_html


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="potok51",
        description="Расчёт кредитного лимита по карточке счёта 51 из 1С",
    )
    parser.add_argument("card", help="путь к файлу карточки (.xlsx / .xls)")
    parser.add_argument("--industry", default="services", choices=sorted(INDUSTRY_RU),
                        help="отрасль клиента")
    parser.add_argument("--html", help="куда записать HTML-отчёт")
    parser.add_argument("--xlsx", help="куда записать выгрузку Excel")
    parser.add_argument("--json", dest="json_path", help="куда записать JSON-результат")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        analysis = analyze_file(args.card, industry=args.industry, cfg=DEFAULT_CONFIG)
    except ReadError as exc:
        print(f"Ошибка разбора: {exc}", file=sys.stderr)
        return 2

    if args.html:
        write_html(analysis, Path(args.html))
    if args.xlsx:
        write_excel(analysis, Path(args.xlsx))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(analysis.model_dump(mode="json", exclude={"transactions"}),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not args.quiet:
        months = max(len(analysis.monthly), 1)
        binding = analysis.limit.binding_constraint
        print(f"Клиент:            {analysis.meta.organization or '—'} (ИНН {analysis.meta.inn or '—'})")
        print(f"Период:            {analysis.monthly[0].month}—{analysis.monthly[-1].month}, "
              f"операций {int(analysis.metrics['operations'])}")
        print(f"Очищенная выручка: {analysis.volumes.adjusted_revenue / months:,.0f} ₽/мес".replace(",", " "))
        print(f"Свободный поток:   {analysis.volumes.fcf / months:,.0f} ₽/мес".replace(",", " "))
        print(f"Решение:           {DECISION_RU[analysis.decision.code.value]}")
        print(f"Лимит:             {analysis.limit.range_low:,.0f} — {analysis.limit.final:,.0f} ₽"
              .replace(",", " ") + (f" (связывает {binding})" if binding else ""))
        for s in analysis.decision.stop_factors:
            print(f"  СТОП: {s}")
        for i in analysis.indicators:
            if i.status.value in ("RED", "AMBER"):
                print(f"  {i.status.value:5s} {i.code}. {i.name}: {i.display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
