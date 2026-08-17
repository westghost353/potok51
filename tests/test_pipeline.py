"""Интеграционные проверки: восемь профилей проходят конвейер целиком."""

import pytest

from potok51.models import Decision, Status
from potok51.pipeline import analyze_file
from potok51.report.excel import write_excel
from potok51.report.html import render_html
from synth.profiles import PROFILES

KEYS = [p.key for p in PROFILES]


@pytest.fixture(scope="module")
def analyses(cards, profiles) -> dict:
    return {
        key: analyze_file(cards[key], industry=profiles[key].industry)
        for key in KEYS
    }


@pytest.mark.parametrize("key", KEYS)
def test_decision_matches_profile_intent(key, analyses, profiles):
    assert analyses[key].decision.code.value == profiles[key].expected


@pytest.mark.parametrize("key", KEYS)
def test_auto_classification_target(key, analyses):
    """Цель Ц1: не менее 95 % оборота размечено правилами."""
    assert analyses[key].metrics["auto_classified_share"] >= 0.95


@pytest.mark.parametrize("key", KEYS)
def test_analysis_is_fast(key, analyses):
    """Цель Ц2: анализ карточки за 12 месяцев укладывается в 20 секунд."""
    assert analyses[key].metrics["analysis_time_sec"] <= 20


@pytest.mark.parametrize("key", KEYS)
def test_data_quality_passes_on_valid_cards(key, analyses):
    assert analyses[key].data_quality.passed


@pytest.mark.parametrize("key", KEYS)
def test_every_indicator_present(key, analyses):
    codes = [i.code for i in analyses[key].indicators]
    assert codes == [f"T{i}" for i in range(1, 16)]


def test_transit_scheme_is_declined_by_transit(analyses):
    a = analyses["06_transit_scheme"]
    t3 = next(i for i in a.indicators if i.code == "T3")
    assert t3.status == Status.RED
    assert t3.value > 0.6
    assert any(s.startswith("S1") for s in a.decision.stop_factors)
    assert a.limit.final == 0


def test_cash_out_profile_raises_cash_flag(analyses):
    a = analyses["07_cash_out"]
    t4 = next(i for i in a.indicators if i.code == "T4")
    assert t4.status == Status.RED
    assert a.decision.code == Decision.MANUAL_REVIEW


def test_concentration_profile_raises_t7(analyses):
    a = analyses["03_services_concentration"]
    t7 = next(i for i in a.indicators if i.code == "T7")
    assert t7.status == Status.RED
    assert t7.value > 0.6


def test_acquiring_is_not_counted_as_concentration(analyses):
    """Розница с 72 % выручки через эквайринг не должна выглядеть концентрированной."""
    a = analyses["02_retail_acquiring"]
    t7 = next(i for i in a.indicators if i.code == "T7")
    assert t7.status == Status.GREEN


def test_collapse_profile_is_declined(analyses):
    a = analyses["08_revenue_collapse"]
    assert a.decision.code == Decision.DECLINE
    assert any(s.startswith("S7") for s in a.decision.stop_factors)


def test_healthy_profile_is_auto_approved_with_positive_limit(analyses):
    a = analyses["01_wholesale_healthy"]
    assert a.decision.code == Decision.AUTO_APPROVE
    assert a.limit.final > 0
    assert a.limit.range_low <= a.limit.final
    assert not [i for i in a.indicators if i.status == Status.RED]


@pytest.mark.parametrize("key", KEYS)
def test_traceability_every_exclusion_has_rows(key, analyses):
    """Требование сквозной трассируемости: исключение раскрывается до операций."""
    for exclusion in analyses[key].volumes.exclusions:
        assert exclusion.rows, f"{key}: у исключения {exclusion.category} нет строк-источников"


@pytest.mark.parametrize("key", KEYS)
def test_reports_render(key, analyses, tmp_path):
    html = render_html(analyses[key])
    assert "<html" in html and "Поток 51" in html
    assert "http://" not in html and "https://" not in html, "отчёт обязан быть автономным"
    path = write_excel(analyses[key], tmp_path / f"{key}.xlsx")
    assert path.stat().st_size > 10_000


def test_deterministic_result(cards, profiles):
    """Один файл и одна версия правил дают идентичный результат."""
    first = analyze_file(cards["01_wholesale_healthy"], industry="wholesale")
    second = analyze_file(cards["01_wholesale_healthy"], industry="wholesale")
    exclude = {"analysis_id", "created_at", "metrics", "transactions"}
    assert first.model_dump(exclude=exclude) == second.model_dump(exclude=exclude)
