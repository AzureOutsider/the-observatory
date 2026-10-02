import hmac
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.services.launcher_control import signal_launcher_shutdown

router = APIRouter(tags=["system"])


@router.get("/system/status")
def system_status() -> dict[str, str | bool | None]:
    token = os.getenv("FINANCE_SHUTDOWN_TOKEN")
    event_name = os.getenv("FINANCE_SHUTDOWN_EVENT")
    managed = bool(token and event_name)
    return {
        "managed_by_launcher": managed,
        "shutdown_token": token if managed else None,
        "message": "可从网站安全退出" if managed else "当前不是由 Finance 启动器管理",
    }


@router.post("/system/shutdown", status_code=status.HTTP_202_ACCEPTED)
def shutdown_system(
    background_tasks: BackgroundTasks,
    shutdown_token: str | None = Header(default=None, alias="X-Finance-Shutdown-Token"),
) -> dict[str, str]:
    expected_token = os.getenv("FINANCE_SHUTDOWN_TOKEN")
    event_name = os.getenv("FINANCE_SHUTDOWN_EVENT")
    if not expected_token or not event_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="网站不是由 Finance 启动器启动，无法统一退出",
        )
    if not shutdown_token or not hmac.compare_digest(shutdown_token, expected_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="退出令牌无效")

    background_tasks.add_task(signal_launcher_shutdown, event_name)
    return {"status": "shutting_down", "message": "正在停止观象台"}
