"""Оркестрация конвейера: файл на входе — обоснованный лимит на выходе."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .classify import auto_classified_share, classify
from .clean import compute_monthly, compute_volumes
from .config import DEFAULT_CONFIG, RULES_VERSION, Config
from .indicators import build_indicators
from .limit import compute_limit, evaluate_stop_factors, make_decision
from .link import link_all
from .models import (
    Analysis,
    Category,
    CounterpartyStat,
    Decision,
    DecisionResult,
    LimitResult,
    Status,
)
from .readers.card51_xlsx import read_card
from .validate import validate


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _top_counterparties(txs: list, inflow: bool, limit: int = 10) -> list:
    agg: dict = defaultdict(lambda: [0.0, 0])
    for t in txs:
        amount = t.inflow if inflow else t.outflow
        if amount <= 0 or t.excluded_reason is not None:
            continue
        entry = agg[t.counterparty or "не указан"]
        entry[0] += amount
        entry[1] += 1
    total = sum(v[0] for v in agg.values()) or 1.0
    rows = sorted(agg.items(), key=lambda kv: -kv[1][0])[:limit]
    return [
        CounterpartyStat(name=name, amount=round(v[0], 2),
                         share=round(v[0] / total, 4), operations=v[1])
        for name, v in rows
    ]


def analyze_file(
    path: str | Path,
    industry: str = "services",
    cfg: Config = DEFAULT_CONFIG,
    keep_transactions: bool = True,
) -> Analysis:
    started = time.perf_counter()
    path = Path(path)

    txs, meta = read_card(path)
    quality = validate(txs, meta, cfg)
    classify(txs, client_inn=meta.inn)
    link_stats = link_all(txs, cfg)
    volumes = compute_volumes(txs)
    monthly = compute_monthly(txs)
    indicators = build_indicators(txs, monthly, volumes, cfg)

    period_days = (txs[-1].date - txs[0].date).days + 1 if txs else 1

    if quality.passed:
        limit = compute_limit(volumes, monthly, indicators, industry, cfg, period_days)
        stops = evaluate_stop_factors(txs, volumes, monthly, indicators, cfg, quality)
        decision = make_decision(indicators, stops, volumes, cfg)
    else:
        limit = LimitResult(
            constraints={}, constraint_labels={}, constraint_formulas={},
            binding_constraint=None, base=0.0, multiplier=0.0,
            final=0.0, range_low=0.0, range_high=0.0,
        )
        stops = evaluate_stop_factors(txs, volumes, monthly, indicators, cfg, quality)
        decision = DecisionResult(
            code=Decision.DECLINE, stop_factors=stops,
            reasons=["Карточка не прошла контроль целостности, расчёт не выполнялся"],
        )

    if decision.code == Decision.DECLINE:
        limit.final = 0.0
        limit.range_low = 0.0
        limit.range_high = 0.0

    unclassified = sorted(
        (t for t in txs if t.category == Category.UNCLASSIFIED),
        key=lambda t: -t.amount,
    )[:20]

    auto_share = auto_classified_share(txs)
    elapsed = round(time.perf_counter() - started, 2)

    return Analysis(
        analysis_id=str(uuid.uuid4()),
        rules_version=RULES_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source_filename=path.name,
        source_sha256=_sha256(path),
        meta=meta,
        industry=industry,
        data_quality=quality,
        volumes=volumes,
        monthly=monthly,
        indicators=indicators,
        limit=limit,
        decision=decision,
        top_inflow=_top_counterparties(txs, inflow=True),
        top_outflow=_top_counterparties(txs, inflow=False),
        unclassified_top=[
            {
                "row_no": t.row_no,
                "date": t.date.isoformat(),
                "counterparty": t.counterparty,
                "purpose": t.purpose,
                "corr_account": t.corr_account,
                "amount": t.amount,
                "direction": "приход" if t.is_inflow else "расход",
            }
            for t in unclassified
        ],
        metrics={
            "auto_classified_share": auto_share,
            "analysis_time_sec": elapsed,
            "operations": float(len(txs)),
            "months": float(len(monthly)),
            **{k: float(v) for k, v in link_stats.items()},
        },
        transactions=txs if keep_transactions else [],
    )
