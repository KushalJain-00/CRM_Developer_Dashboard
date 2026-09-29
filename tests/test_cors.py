"""CORS allow-list contract: preflight must return ACAO for allowed origins."""
from starlette.testclient import TestClient


def _preflight(origin):
    from main import app
    with TestClient(app) as c:
        return c.options(
            "/api/eml/process",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )


def test_preflight_allows_new_vercel_domain():
    r = _preflight("https://crmdeveloper.vercel.app")
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://crmdeveloper.vercel.app"


def test_preflight_allows_legacy_vercel_domain():
    r = _preflight("https://crmdevloper.vercel.app")
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://crmdevloper.vercel.app"


def test_preflight_allows_local_dev_origins():
    for origin in ("http://localhost:3000", "http://localhost:5173"):
        r = _preflight(origin)
        assert r.status_code == 200, origin
        assert r.headers.get("access-control-allow-origin") == origin


def test_preflight_rejects_unknown_origin():
    r = _preflight("https://evil.example.com")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
