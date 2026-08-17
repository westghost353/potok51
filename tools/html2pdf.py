"""Печать HTML в PDF через headless Chrome по протоколу DevTools.

CLI-флаг --print-to-pdf не умеет колонтитулы, поэтому используется
Page.printToPDF: он принимает шаблоны верхнего и нижнего колонтитула
с номерами страниц.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HEADER = """<div style="font-size:7.5pt;font-family:-apple-system,Helvetica,Arial,sans-serif;
color:#8b949e;width:100%;padding:0 12mm;display:flex;justify-content:space-between;">
<span>{title}</span><span>{subtitle}</span></div>"""

FOOTER = """<div style="font-size:7.5pt;font-family:-apple-system,Helvetica,Arial,sans-serif;
color:#8b949e;width:100%;padding:0 12mm;display:flex;justify-content:space-between;">
<span>{footer_left}</span>
<span>Стр. <span class="pageNumber"></span> из <span class="totalPages"></span></span></div>"""


class Chrome:
    def __init__(self, port: int = 9222) -> None:
        self.port = port
        self.profile = Path(tempfile.mkdtemp(prefix="potok51-chrome-"))
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "Chrome":
        self.proc = subprocess.Popen(
            [
                CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}", "about:blank",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1) as r:
                    self.ws_url = json.load(r)["webSocketDebuggerUrl"]
                    return self
            except Exception:
                time.sleep(0.3)
        raise RuntimeError("Chrome не поднялся на порту отладки")

    def __exit__(self, *exc) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


class Session:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.counter = 0

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None):
        self.counter += 1
        message = {"id": self.counter, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        await self.ws.send(json.dumps(message))
        while True:
            data = json.loads(await self.ws.recv())
            if data.get("id") == self.counter:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    async def wait_event(self, method: str, timeout: float = 45.0):
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            data = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=remaining))
            if data.get("method") == method:
                return data
        raise TimeoutError(method)


async def render(ws_url: str, jobs: list) -> None:
    async with websockets.connect(ws_url, max_size=200 * 1024 * 1024) as ws:
        session = Session(ws)
        for job in jobs:
            target = await session.send("Target.createTarget", {"url": "about:blank"})
            attached = await session.send(
                "Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}
            )
            sid = attached["sessionId"]
            await session.send("Page.enable", {}, sid)
            await session.send("Emulation.setEmulatedMedia", {"media": "print"}, sid)
            await session.send("Page.navigate", {"url": job["url"]}, sid)
            await session.wait_event("Page.loadEventFired")
            await asyncio.sleep(1.2)  # дать отрисоваться шрифтам и SVG

            result = await session.send(
                "Page.printToPDF",
                {
                    "printBackground": True,
                    "paperWidth": 8.27,
                    "paperHeight": 11.69,
                    "marginTop": 0.75,
                    "marginBottom": 0.65,
                    "marginLeft": 0.5,
                    "marginRight": 0.5,
                    "displayHeaderFooter": True,
                    "headerTemplate": HEADER.format(title=job["title"], subtitle=job["subtitle"]),
                    "footerTemplate": FOOTER.format(footer_left=job["footer_left"]),
                    "preferCSSPageSize": False,
                    "scale": job.get("scale", 1.0),
                },
                sid,
            )
            out = Path(job["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(result["data"]))
            print(f"{out}  {out.stat().st_size / 1024:.0f} КБ")
            await session.send("Target.closeTarget", {"targetId": target["targetId"]})


def main() -> None:
    parser = argparse.ArgumentParser(description="HTML → PDF через headless Chrome")
    parser.add_argument("spec", help="JSON-файл с заданиями на печать")
    args = parser.parse_args()
    jobs = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    with Chrome() as chrome:
        asyncio.run(render(chrome.ws_url, jobs))


if __name__ == "__main__":
    main()
