"""Интерфейс ридера. Новый формат входа добавляется реализацией read()."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import CardMeta, Transaction


class Reader(Protocol):
    name: str

    def supports(self, path: Path) -> bool: ...

    def read(self, path: Path) -> tuple[list[Transaction], CardMeta]: ...


class ReadError(Exception):
    """Файл не удалось разобрать как источник операций."""
