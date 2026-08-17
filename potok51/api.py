"""HTTP-сервис: загрузка карточки, анализ, отчёт, выгрузки."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import DEFAULT_CONFIG, INDUSTRY_RU, RULES_VERSION
from .pipeline import analyze_file
from .readers.base import ReadError
from .report.excel import write_excel
from .report.html import write_html
from .storage import analysis_dir, recent, register, save_json

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".xlsx", ".xls"}

# Префикс, под которым сервис опубликован обратным прокси. Caddy с директивой
# handle_path срезает префикс до приложения, поэтому маршруты остаются
# корневыми, а вот все ссылки и редиректы обязаны префикс возвращать —
# иначе браузер уходит в корень домена.
BASE_PATH = os.environ.get("POTOK51_BASE_PATH", "").rstrip("/")


def url(path: str) -> str:
    return f"{BASE_PATH}{path}"

app = FastAPI(title="Поток 51", version=RULES_VERSION,
              description="Кредитный лимит на пополнение оборотных средств по карточке счёта 51")

security = HTTPBasic(auto_error=False)
logger = logging.getLogger("potok51")


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user = os.environ.get("POTOK51_BASIC_USER")
    password = os.environ.get("POTOK51_BASIC_PASSWORD")
    if not user or not password:
        return
    if (
        credentials is None
        or not secrets.compare_digest(credentials.username, user)
        or not secrets.compare_digest(credentials.password, password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "rules_version": RULES_VERSION}


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(require_auth)) -> str:
    options = "".join(
        f'<option value="{key}">{name}</option>' for key, name in INDUSTRY_RU.items()
    )
    history = "".join(
        f'<tr><td><a href="{url("/analysis/" + r["analysis_id"])}">'
        f'{r["organization"] or r["filename"]}</a></td>'
        f'<td>{r["inn"] or "—"}</td><td>{r["decision"]}</td>'
        f'<td style="text-align:right">{r["limit_final"]:,.0f} ₽</td>'
        f'<td>{r["created_at"]}</td></tr>'.replace(",", " ")
        for r in recent()
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Поток 51</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;background:#fff;color:#24292f;font:15px/1.55 "Helvetica Neue",Helvetica,Arial,"Segoe UI",sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:40px 24px}}
h1{{font-size:26px;margin:0 0 6px}} .sub{{color:#5b6570;font-size:14px}}
form{{border:1px solid #e3e6ea;border-radius:10px;padding:22px;margin:26px 0;background:#f6f8fa}}
label{{display:block;font-size:13px;color:#5b6570;margin:12px 0 4px}}
input,select{{width:100%;padding:9px 11px;border:1px solid #d6dae0;border-radius:7px;background:#fff;font-size:14px}}
button{{margin-top:18px;background:#1f6feb;color:#fff;border:0;border-radius:7px;padding:11px 22px;
font-size:15px;font-weight:600;cursor:pointer}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}
th,td{{border-bottom:1px solid #e3e6ea;padding:7px 9px;text-align:left}}
th{{font-size:12px;text-transform:uppercase;color:#5b6570}}
a{{color:#1f6feb}}
</style></head><body><div class="wrap">
<h1>Поток 51</h1>
<div class="sub">Кредитный лимит на пополнение оборотных средств по карточке счёта 51 из 1С.
Версия правил {RULES_VERSION}.</div>
<form action="{url("/upload")}" method="post" enctype="multipart/form-data">
  <label>Карточка счёта 51 (.xlsx или .xls, до 50 МБ)</label>
  <input type="file" name="file" accept=".xlsx,.xls" required>
  <label>Отрасль</label>
  <select name="industry">{options}</select>
  <label>Запрошенная сумма, ₽ (необязательно)</label>
  <input type="number" name="requested_amount" step="1000" min="0">
  <button type="submit">Рассчитать лимит</button>
</form>
<h2 style="font-size:17px">Последние анализы</h2>
<table><thead><tr><th>Клиент</th><th>ИНН</th><th>Решение</th><th style="text-align:right">Лимит</th>
<th>Дата</th></tr></thead><tbody>{history or '<tr><td colspan="5">пока пусто</td></tr>'}</tbody></table>
</div></body></html>"""


async def _run_analysis(file: UploadFile, industry: str):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Поддерживаются только файлы {sorted(ALLOWED_SUFFIXES)}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        size = 0
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(413, "Файл больше 50 МБ")
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        analysis = analyze_file(tmp_path, industry=industry, cfg=DEFAULT_CONFIG)
    except ReadError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(422, f"Не удалось разобрать карточку: {exc}") from exc
    except Exception as exc:  # битый архив, чужой формат, неожиданная раскладка
        tmp_path.unlink(missing_ok=True)
        logger.exception("Разбор файла %s завершился ошибкой", file.filename)
        raise HTTPException(
            422,
            "Файл не удалось прочитать как карточку счёта 51 из 1С. "
            "Проверьте, что это выгрузка отчёта «Карточка счёта» в формате xlsx или xls.",
        ) from exc

    analysis.source_filename = file.filename or tmp_path.name
    directory = analysis_dir(analysis.analysis_id)
    directory.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_path), directory / f"source{suffix}")
    save_json(analysis)
    write_html(analysis, directory / "report.html")
    write_excel(analysis, directory / "export.xlsx")
    register(analysis)
    return analysis


@app.post("/api/v1/analyze")
async def analyze(
    file: UploadFile = File(...),
    industry: str = Form("services"),
    requested_amount: str = Form(""),
    _: None = Depends(require_auth),
) -> JSONResponse:
    analysis = await _run_analysis(file, industry)
    payload = {
        "analysis_id": analysis.analysis_id,
        "decision": analysis.decision.code.value,
        "limit": analysis.limit.final,
        "limit_range": [analysis.limit.range_low, analysis.limit.range_high],
        "binding_constraint": analysis.limit.binding_constraint,
        "stop_factors": analysis.decision.stop_factors,
        "report_url": url(f"/analysis/{analysis.analysis_id}"),
        "json_url": url(f"/api/v1/analysis/{analysis.analysis_id}"),
    }
    if requested_amount.strip():
        try:
            requested = float(requested_amount)
            payload["requested_amount"] = requested
            payload["covers_request"] = analysis.limit.final >= requested
        except ValueError:
            payload["requested_amount"] = None
    return JSONResponse(payload)


@app.post("/upload")
async def upload_form(
    file: UploadFile = File(...),
    industry: str = Form("services"),
    requested_amount: str = Form(""),
    _: None = Depends(require_auth),
) -> RedirectResponse:
    """Точка для формы в браузере: после расчёта сразу открывается отчёт."""
    analysis = await _run_analysis(file, industry)
    return RedirectResponse(url(f"/analysis/{analysis.analysis_id}"), status_code=303)


def _file_or_404(analysis_id: str, name: str) -> Path:
    path = analysis_dir(analysis_id) / name
    if not path.exists():
        raise HTTPException(404, "Анализ не найден")
    return path


@app.get("/analysis/{analysis_id}", response_class=HTMLResponse)
def report(analysis_id: str, _: None = Depends(require_auth)) -> HTMLResponse:
    return HTMLResponse(_file_or_404(analysis_id, "report.html").read_text(encoding="utf-8"))


@app.get("/api/v1/analysis/{analysis_id}")
def analysis_json(analysis_id: str, _: None = Depends(require_auth)) -> FileResponse:
    return FileResponse(_file_or_404(analysis_id, "analysis.json"), media_type="application/json")


@app.get("/api/v1/analysis/{analysis_id}/export.xlsx")
def analysis_xlsx(analysis_id: str, _: None = Depends(require_auth)) -> FileResponse:
    return FileResponse(
        _file_or_404(analysis_id, "export.xlsx"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"potok51-{analysis_id[:8]}.xlsx",
    )
