from pathlib import Path

from fastapi.testclient import TestClient

from asteroid_belt.server.app import build_app


def test_health_ok(tmp_path: Path) -> None:
    app = build_app(data_dir=tmp_path)
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_schema_versioned(tmp_path: Path) -> None:
    app = build_app(data_dir=tmp_path)
    client = TestClient(app)
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "/api/v1/health" in schema["paths"]
