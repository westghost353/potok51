"""HTTP-контракт сервиса, включая работу за обратным прокси."""

import importlib

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("POTOK51_DATA_DIR", str(tmp_path / "analyses"))
    monkeypatch.delenv("POTOK51_BASE_PATH", raising=False)
    monkeypatch.delenv("POTOK51_BASIC_USER", raising=False)
    monkeypatch.delenv("POTOK51_BASIC_PASSWORD", raising=False)
    import potok51.storage as storage
    import potok51.api as api
    importlib.reload(storage)
    importlib.reload(api)
    return TestClient(api.app)


@pytest.fixture
def prefixed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("POTOK51_DATA_DIR", str(tmp_path / "analyses"))
    monkeypatch.setenv("POTOK51_BASE_PATH", "/potok51")
    import potok51.storage as storage
    import potok51.api as api
    importlib.reload(storage)
    importlib.reload(api)
    return TestClient(api.app)


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok" and body["rules_version"]


def test_index_renders(client):
    assert client.get("/").status_code == 200


def test_full_cycle(client, healthy_card):
    with open(healthy_card, "rb") as fh:
        r = client.post("/api/v1/analyze", files={"file": ("card.xlsx", fh)},
                        data={"industry": "wholesale", "requested_amount": "5000000"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "AUTO_APPROVE"
    assert body["covers_request"] is True
    aid = body["analysis_id"]
    assert client.get(f"/analysis/{aid}").status_code == 200
    assert client.get(f"/api/v1/analysis/{aid}").status_code == 200
    assert client.get(f"/api/v1/analysis/{aid}/export.xlsx").status_code == 200


def test_rejects_wrong_extension(client):
    r = client.post("/api/v1/analyze", files={"file": ("card.pdf", b"%PDF-1.4")})
    assert r.status_code == 400


def test_rejects_unparseable_file(client):
    r = client.post("/api/v1/analyze", files={"file": ("card.xlsx", b"not really xlsx")})
    assert r.status_code in (422, 500)


def test_missing_analysis_is_404(client):
    assert client.get("/analysis/00000000-0000-0000-0000-000000000000").status_code == 404


def test_basic_auth_enforced(tmp_path, monkeypatch, healthy_card):
    monkeypatch.setenv("POTOK51_DATA_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("POTOK51_BASIC_USER", "analyst")
    monkeypatch.setenv("POTOK51_BASIC_PASSWORD", "secret")
    import potok51.storage as storage
    import potok51.api as api
    importlib.reload(storage)
    importlib.reload(api)
    c = TestClient(api.app)
    assert c.get("/").status_code == 401
    assert c.get("/", auth=("analyst", "wrong")).status_code == 401
    assert c.get("/", auth=("analyst", "secret")).status_code == 200
    assert c.get("/healthz").status_code == 200  # проверка живости всегда открыта


def test_links_carry_reverse_proxy_prefix(prefixed_client, healthy_card):
    """За Caddy с handle_path префикс срезается — ссылки обязаны его возвращать."""
    assert 'action="/potok51/upload"' in prefixed_client.get("/").text
    with open(healthy_card, "rb") as fh:
        body = prefixed_client.post("/api/v1/analyze", files={"file": ("card.xlsx", fh)},
                                    data={"industry": "wholesale"}).json()
    assert body["report_url"].startswith("/potok51/analysis/")
    assert body["json_url"].startswith("/potok51/api/v1/analysis/")
    with open(healthy_card, "rb") as fh:
        r = prefixed_client.post("/upload", files={"file": ("card.xlsx", fh)},
                                 data={"industry": "wholesale"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/potok51/analysis/")
