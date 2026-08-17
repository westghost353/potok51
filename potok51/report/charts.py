"""Встроенные SVG-графики. Без внешних библиотек: отчёт должен открываться офлайн."""

from __future__ import annotations

PALETTE = {
    "revenue": "#1f6feb",
    "fcf": "#0f8f4f",
    "negative": "#c0392b",
    "grid": "#e3e6ea",
    "axis": "#8b949e",
    "text": "#24292f",
    "GREEN": "#0f8f4f",
    "AMBER": "#c9820a",
    "RED": "#c0392b",
    "NA": "#8b949e",
}


def _fmt_m(value: float) -> str:
    """Денежная подпись на графике: 269,2\u00a0млн вместо 269.2M."""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}".replace(".", ",") + "\u00a0млн"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}\u00a0тыс"
    return f"{value:.0f}"


def monthly_chart(monthly: list, width: int = 900, height: int = 260) -> str:
    """Столбцы очищенной выручки и линия свободного потока."""
    if not monthly:
        return ""
    pad_l, pad_r, pad_t, pad_b = 62, 18, 18, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    values = [m.adjusted_revenue for m in monthly] + [m.fcf for m in monthly]
    vmax = max(values + [1])
    vmin = min(values + [0])
    span = (vmax - vmin) or 1

    def y(v: float) -> float:
        return pad_t + plot_h - (v - vmin) / span * plot_h

    n = len(monthly)
    step = plot_w / n
    bar_w = step * 0.56

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + plot_h * frac
        val = vmax - (vmax - vmin) * frac
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
                     f'stroke="{PALETTE["grid"]}" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="{PALETTE["axis"]}">{_fmt_m(val)}</text>')
    if vmin < 0:
        parts.append(f'<line x1="{pad_l}" y1="{y(0):.1f}" x2="{width - pad_r}" y2="{y(0):.1f}" '
                     f'stroke="{PALETTE["axis"]}" stroke-width="1.2"/>')

    for i, m in enumerate(monthly):
        x = pad_l + step * i + (step - bar_w) / 2
        top = y(max(m.adjusted_revenue, 0))
        bottom = y(0)
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
                     f'height="{max(bottom - top, 1):.1f}" fill="{PALETTE["revenue"]}" opacity="0.85" rx="2">'
                     f'<title>{m.month}: выручка {m.adjusted_revenue:,.0f} ₽</title></rect>'.replace(",", " "))
        label = m.month[5:] + "." + m.month[2:4]
        parts.append(f'<text x="{pad_l + step * i + step / 2:.1f}" y="{height - 12}" '
                     f'text-anchor="middle" font-size="10" fill="{PALETTE["axis"]}">{label}</text>')

    points = " ".join(f"{pad_l + step * i + step / 2:.1f},{y(m.fcf):.1f}" for i, m in enumerate(monthly))
    parts.append(f'<polyline points="{points}" fill="none" stroke="{PALETTE["fcf"]}" stroke-width="2.4"/>')
    for i, m in enumerate(monthly):
        cx = pad_l + step * i + step / 2
        color = PALETTE["fcf"] if m.fcf >= 0 else PALETTE["negative"]
        parts.append(f'<circle cx="{cx:.1f}" cy="{y(m.fcf):.1f}" r="3.4" fill="{color}">'
                     f'<title>{m.month}: свободный поток {m.fcf:,.0f} ₽</title></circle>'.replace(",", " "))
    parts.append("</svg>")
    return "".join(parts)


def waterfall(volumes, width: int = 900, height: int = 240) -> str:
    """Мост от валового притока к очищенной выручке."""
    steps = [("Валовой приток", volumes.gross_inflow, "base")]
    for exc in volumes.exclusions:
        steps.append((exc.label, -exc.amount, "minus"))
    steps.append(("Очищенная выручка", volumes.adjusted_revenue, "result"))

    pad_l, pad_r, pad_t, pad_b = 20, 20, 20, 58
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    vmax = max(volumes.gross_inflow, 1)
    step_w = plot_w / len(steps)
    bar_w = step_w * 0.62

    def h(v: float) -> float:
        return abs(v) / vmax * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    running = 0.0
    for i, (label, value, kind) in enumerate(steps):
        x = pad_l + step_w * i + (step_w - bar_w) / 2
        if kind == "base":
            top = pad_t + plot_h - h(value)
            bar_h = h(value)
            running = value
            color = PALETTE["revenue"]
        elif kind == "minus":
            new_running = running + value
            top = pad_t + plot_h - h(running)
            bar_h = max(h(running) - h(new_running), 1.5)
            running = new_running
            color = PALETTE["negative"]
        else:
            top = pad_t + plot_h - h(value)
            bar_h = h(value)
            color = PALETTE["fcf"]
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                     f'fill="{color}" opacity="0.88" rx="2"><title>{label}: {value:,.0f} ₽</title></rect>'.replace(",", " "))
        cx = pad_l + step_w * i + step_w / 2
        parts.append(f'<text x="{cx:.1f}" y="{top - 6:.1f}" text-anchor="middle" font-size="10.5" '
                     f'fill="{PALETTE["text"]}">{_fmt_m(abs(value))}</text>')
        words = label.split()
        line1 = " ".join(words[:2])
        line2 = " ".join(words[2:])
        parts.append(f'<text x="{cx:.1f}" y="{height - 34}" text-anchor="middle" font-size="10" '
                     f'fill="{PALETTE["axis"]}">{line1}</text>')
        if line2:
            parts.append(f'<text x="{cx:.1f}" y="{height - 22}" text-anchor="middle" font-size="10" '
                         f'fill="{PALETTE["axis"]}">{line2}</text>')
    parts.append("</svg>")
    return "".join(parts)


def constraints_chart(limit, width: int = 900, height: int = 170) -> str:
    """Четыре ограничителя; связывающий выделен."""
    if not limit.constraints:
        return ""
    items = list(limit.constraints.items())
    vmax = max(v for _, v in items) or 1
    pad_l, pad_t = 258, 14
    row_h = (height - pad_t - 10) / len(items)
    bar_max = width - pad_l - 170

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for i, (code, value) in enumerate(items):
        y = pad_t + row_h * i
        w = max(value / vmax * bar_max, 2)
        binding = code == limit.binding_constraint
        color = PALETTE["negative"] if binding else PALETTE["revenue"]
        label = f"{code}. {limit.constraint_labels.get(code, '')}"
        parts.append(f'<text x="{pad_l - 12}" y="{y + row_h / 2 + 4:.1f}" text-anchor="end" '
                     f'font-size="12" fill="{PALETTE["text"]}">{label}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y + row_h * 0.18:.1f}" width="{w:.1f}" '
                     f'height="{row_h * 0.62:.1f}" fill="{color}" opacity="{0.95 if binding else 0.55}" rx="2"/>')
        suffix = "  ← связывающий" if binding else ""
        parts.append(f'<text x="{pad_l + w + 10:.1f}" y="{y + row_h / 2 + 4:.1f}" font-size="11.5" '
                     f'fill="{PALETTE["text"]}">{value:,.0f} ₽{suffix}</text>'.replace(",", "\u00a0"))
    parts.append("</svg>")
    return "".join(parts)
