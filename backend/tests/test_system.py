from fastapi.testclient import TestClient

from app.api import system
from app.main import create_app


def test_system_status_is_unmanaged_without_launcher_environment(monkeypatch):
    monkeypatch.delenv("FINANCE_SHUTDOWN_TOKEN", raising=False)
    monkeypatch.delenv("FINANCE_SHUTDOWN_EVENT", raising=False)

    response = TestClient(create_app()).get("/api/system/status")

    assert response.status_code == 200
    assert response.json() == {
        "managed_by_launcher": False,
        "shutdown_token": None,
        "message": "当前不是由 Finance 启动器管理",
    }


def test_shutdown_requires_launcher_environment(monkeypatch):
    monkeypatch.delenv("FINANCE_SHUTDOWN_TOKEN", raising=False)
    monkeypatch.delenv("FINANCE_SHUTDOWN_EVENT", raising=False)

    response = TestClient(create_app()).post("/api/system/shutdown")

    assert response.status_code == 409


def test_shutdown_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("FINANCE_SHUTDOWN_TOKEN", "expected")
    monkeypatch.setenv("FINANCE_SHUTDOWN_EVENT", "Local\\FinanceOS.Test")

    response = TestClient(create_app()).post(
        "/api/system/shutdown",
        headers={"X-Finance-Shutdown-Token": "wrong"},
    )

    assert response.status_code == 403


def test_shutdown_signals_launcher(monkeypatch):
    signaled: list[str] = []
    monkeypatch.setenv("FINANCE_SHUTDOWN_TOKEN", "expected")
    monkeypatch.setenv("FINANCE_SHUTDOWN_EVENT", "Local\\FinanceOS.Test")
    monkeypatch.setattr(system, "signal_launcher_shutdown", signaled.append)

    response = TestClient(create_app()).post(
        "/api/system/shutdown",
        headers={"X-Finance-Shutdown-Token": "expected"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "shutting_down"
    assert signaled == ["Local\\FinanceOS.Test"]
