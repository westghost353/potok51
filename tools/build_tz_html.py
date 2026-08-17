"""Сборка HTML-версии ТЗ из Markdown — для экрана и для печати в PDF."""

from __future__ import annotations

import re
from pathlib import Path

import markdown

SRC = Path("docs/ТЗ_Поток51_прототип.md")
DST = Path("docs/ТЗ_Поток51_прототип.html")

SHELL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {subtitle}</title>
<style>
  :root{{--bg:#fff;--ink:#1f2328;--muted:#5b6570;--line:#e3e6ea;--soft:#f6f8fa;
        --blue:#1f6feb;--green:#0f8f4f;--amber:#c9820a;--red:#c0392b;--nav:262px}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.6 "Helvetica Neue",Helvetica,Arial,"Segoe UI",sans-serif;font-variant-ligatures:none}}
  .progress{{position:fixed;top:0;left:0;height:3px;background:var(--blue);width:0;z-index:50}}
  .layout{{display:flex;max-width:1250px;margin:0 auto;gap:34px;padding:0 26px}}
  nav{{width:var(--nav);flex:0 0 var(--nav);position:sticky;top:0;align-self:flex-start;
    max-height:100vh;overflow:auto;padding:34px 0 40px}}
  nav .t{{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
  nav ul{{list-style:none;margin:0;padding:0}} nav ul ul{{display:none}}
  nav a{{display:block;color:var(--muted);text-decoration:none;font-size:12.5px;padding:4px 9px;
    border-left:2px solid transparent;line-height:1.35}}
  nav a:hover{{color:var(--ink)}}
  nav a.on{{color:var(--blue);border-left-color:var(--blue);font-weight:600}}
  main{{flex:1;min-width:0;padding:34px 0 90px}}
  .cover{{border-bottom:2px solid var(--ink);padding-bottom:24px;margin-bottom:8px}}
  .kicker{{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
  .cover h1{{font-size:31px;line-height:1.16;margin:10px 0 12px;font-weight:660;letter-spacing:-.02em}}
  .abstract{{font-size:15.5px;color:var(--muted);max-width:74ch;margin:0 0 4px}}
  .meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-top:18px}}
  .meta>div{{border:1px solid var(--line);border-radius:8px;padding:11px 14px}}
  .meta .k{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  .meta .v{{font-size:14px;font-weight:600;margin-top:2px}}
  main h2{{font-size:21px;margin:42px 0 12px;padding-top:16px;border-top:1px solid var(--line);
    font-weight:640;letter-spacing:-.01em;scroll-margin-top:16px}}
  main h3{{font-size:16px;margin:24px 0 8px;font-weight:620}}
  main h4{{font-size:14px;margin:18px 0 6px;font-weight:620;color:var(--muted)}}
  p,li{{max-width:80ch}}
  table{{border-collapse:collapse;width:100%;font-size:13px;margin:14px 0}}
  th,td{{border-bottom:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}}
  th{{background:var(--soft);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
     color:var(--muted);font-weight:600}}
  code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
    background:var(--soft);padding:1px 5px;border-radius:4px}}
  pre{{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:13px 15px;
    overflow-x:auto;font-size:12px;line-height:1.45}}
  pre code{{background:none;padding:0;font-size:12px}}
  blockquote{{border-left:4px solid var(--blue);background:var(--soft);margin:16px 0;
    padding:10px 16px;border-radius:0 8px 8px 0}}
  hr{{border:0;border-top:1px solid var(--line);margin:34px 0}}
  strong{{font-weight:640}}
  a{{color:var(--blue)}}
  .print-toc{{display:none}}
  @media print{{
    nav,.progress{{display:none}} .layout{{display:block;max-width:none;padding:0}} main{{padding:0}}
    body{{font-size:9.4pt;line-height:1.45}}
    .cover{{page-break-after:always;padding-top:26mm;border-bottom:none}}
    .cover h1{{font-size:23pt;line-height:1.18}} .abstract{{font-size:11pt}}
    .print-toc{{display:block;page-break-after:always}}
    .print-toc h2{{border-top:none;padding-top:0;margin-top:0}}
    .print-toc ul{{list-style:none;padding-left:0;font-size:10pt;line-height:1.9}}
    .print-toc ul ul{{display:none}}
    .print-toc a{{color:var(--ink);text-decoration:none}}
    main h2{{page-break-before:auto;page-break-after:avoid;font-size:14pt;margin-top:20pt}}
    main h3,main h4{{page-break-after:avoid}}
    table,pre,blockquote{{page-break-inside:auto}}
    tr{{page-break-inside:avoid}}
    thead{{display:table-header-group}}
    p,li{{max-width:none;orphans:3;widows:3}}
    pre{{white-space:pre-wrap;word-break:break-word}}
  }}
  @media (max-width:960px){{nav{{display:none}}.layout{{padding:0 18px}}}}
</style></head><body>
<div class="progress" id="pr"></div>
<div class="layout">
<nav><div class="t">Содержание</div>{toc}</nav>
<main>
<div class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{subtitle}</h1>
  <p class="abstract">{abstract}</p>
  <div class="meta">{meta}</div>
</div>
<div class="print-toc"><h2>Содержание</h2>{toc}</div>
{body}
</main></div>
<script>
  const links=[...document.querySelectorAll('nav a')];
  const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  const bar=document.getElementById('pr');
  new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting)
    links.forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+e.target.id));}}),
    {{rootMargin:'-12% 0px -80% 0px'}}).observe && secs.forEach(s=>
      new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting)
        links.forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+e.target.id));}}),
        {{rootMargin:'-12% 0px -80% 0px'}}).observe(s));
  addEventListener('scroll',()=>{{const h=document.documentElement;
    bar.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight)*100)+'%';}},{{passive:true}});
</script>
</body></html>"""


def build() -> Path:
    raw = SRC.read_text(encoding="utf-8")
    head, body_md = raw.split("\n---\n", 1)

    title = re.search(r"^# (.+)$", head, re.M).group(1).strip()
    subtitle = re.search(r"^## (.+)$", head, re.M).group(1).strip()
    meta_pairs = re.findall(r"^\*\*(.+?):\*\*\s*(.+)$", head, re.M)
    meta_html = "".join(
        f'<div><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in meta_pairs
    )

    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
                           extension_configs={"toc": {"toc_depth": "2-2"}})
    body_html = md.convert(body_md)
    # цифра и знак процента не должны разъезжаться по разным строкам
    body_html = re.sub(r"(\d)\s%", "\\1\u00a0%", body_html)

    abstract = (
        "Прототип принимает выгрузку карточки счёта 51 из 1С, разбирает её в структурированный "
        "поток операций, отделяет реальную операционную выручку от транзита, внутригрупповых "
        "переводов, заёмных денег и возвратов, считает пятнадцать риск-индикаторов и выдаёт "
        "кредитному аналитику обоснованный лимит с полной трассируемостью каждой цифры "
        "до конкретных строк исходного файла."
    )
    html = SHELL.format(
        title=title, subtitle=subtitle, kicker=title, abstract=abstract,
        meta=meta_html, toc=md.toc, body=body_html,
    )
    DST.write_text(html, encoding="utf-8")
    return DST


if __name__ == "__main__":
    path = build()
    print(f"{path}  {path.stat().st_size / 1024:.0f} КБ")
