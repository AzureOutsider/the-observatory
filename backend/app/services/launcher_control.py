from __future__ import annotations

import ctypes
import sys
import time


def signal_launcher_shutdown(event_name: str) -> None:
    # Background tasks run after the HTTP response is sent, leaving the UI time
    # to render its stopped state before the launcher terminates both services.
    time.sleep(0.6)
    if sys.platform != "win32":
        return

    event_modify_state = 0x0002
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenEventW(event_modify_state, False, event_name)
    if not handle:
        return
    try:
        kernel32.SetEvent(handle)
    finally:
        kernel32.CloseHandle(handle)
