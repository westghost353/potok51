"""Хранилище результатов: файлы на диске + SQLite-индекс.

Индекс нужен только для списка последних анализов; источником правды
остаются файлы в каталоге анализа, чтобы результат можно было забрать
и переслать без базы.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("POTOK51_DATA_DIR", "data/analyses"))


def analysis_dir(analysis_id: str) -> Path:
    return DATA_DIR / analysis_id


def _db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "index.sqlite3"


def init_db() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS analyses(
                   analysis_id TEXT PRIMARY KEY,
                   created_at  TEXT NOT NULL,
                   organization TEXT,
                   inn TEXT,
                   filename TEXT,
                   industry TEXT,
                   decision TEXT,
                   limit_final REAL,
                   rules_version TEXT
               )"""
        )


def register(analysis) -> None:
    init_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?,?,?,?)",
            (
                analysis.analysis_id,
                analysis.created_at,
                analysis.meta.organization,
                analysis.meta.inn,
                analysis.source_filename,
                analysis.industry,
                analysis.decision.code.value,
                analysis.limit.final,
                analysis.rules_version,
            ),
        )


def recent(limit: int = 25) -> list:
    init_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_json(analysis) -> Path:
    directory = analysis_dir(analysis.analysis_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "analysis.json"
    payload = analysis.model_dump(mode="json", exclude={"transactions"})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
