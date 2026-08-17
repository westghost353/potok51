from pathlib import Path

import pytest

from synth.generate import generate
from synth.profiles import BY_KEY, PROFILES


@pytest.fixture(scope="session")
def cards(tmp_path_factory) -> dict:
    """Синтетические карточки генерируются один раз на сессию."""
    out = tmp_path_factory.mktemp("cards")
    return {p.key: generate(p, out) for p in PROFILES}


@pytest.fixture(scope="session")
def healthy_card(cards) -> Path:
    return cards["01_wholesale_healthy"]


@pytest.fixture(scope="session")
def profiles() -> dict:
    return BY_KEY
