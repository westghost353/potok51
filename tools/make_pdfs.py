"""Печать комплекта документов «Поток 51» в PDF."""

from __future__ import annotations

import asyncio
from pathlib import Path

from html2pdf import Chrome, render

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pdf"
BRAND = "Поток 51 · август 2026"

JOBS = [
    {
        "src": "docs/Исследование_потоковое_кредитование_МСБ.html",
        "out": "Поток51_1_Исследование_кредитование_МСБ.pdf",
        "title": "Потоковое кредитование МСБ и оценка риска по карточке счёта 51",
        "footer_left": "Исследование · аналитический материал",
    },
    {
        "src": "docs/ТЗ_Поток51_прототип.html",
        "out": "Поток51_2_Техническое_задание.pdf",
        "title": "Техническое задание · прототип «Поток 51»",
        "footer_left": "Техническое задание · версия 1.0",
    },
    {
        "src": "docs/Спецификация_алгоритмов_Поток51.html",
        "out": "Поток51_3_Спецификация_алгоритмов.pdf",
        "title": "Спецификация алгоритмов и формул · «Поток 51»",
        "footer_left": "Руководство по воспроизведению · версия правил 1.0.0",
    },
    {
        "src": "data/out/01_wholesale_healthy.html",
        "out": "Поток51_4_Отчет_пример_одобрение.pdf",
        "title": "Отчёт кредитного анализа · ООО «Северный Двор»",
        "footer_left": "Пример работы прототипа · данные синтетические",
    },
    {
        "src": "data/out/06_transit_scheme.html",
        "out": "Поток51_5_Отчет_пример_отказ.pdf",
        "title": "Отчёт кредитного анализа · ООО «Вектор Плюс»",
        "footer_left": "Пример работы прототипа · данные синтетические",
    },
]


def main() -> None:
    jobs = [
        {
            "url": (ROOT / job["src"]).as_uri(),
            "out": str(OUT / job["out"]),
            "title": job["title"],
            "subtitle": BRAND,
            "footer_left": job["footer_left"],
        }
        for job in JOBS
    ]
    with Chrome() as chrome:
        asyncio.run(render(chrome.ws_url, jobs))


if __name__ == "__main__":
    main()
