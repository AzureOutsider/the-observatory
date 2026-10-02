from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Response-Time-ms"]) >= 0


def test_health_endpoint_preserves_request_id():
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"X-Request-ID": "test-request-123"})

    assert response.headers["X-Request-ID"] == "test-request-123"
