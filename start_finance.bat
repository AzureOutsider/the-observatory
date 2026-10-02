@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "PYTHON_EXE=python"
if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8000/api/health"
set "FRONTEND_URL=http://127.0.0.1:5173"

title The Observatory Launcher

if /I "%PYTHON_EXE%"=="python" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found in PATH.
        echo Install Python or add it to PATH, then run this file again.
        pause
        exit /b 1
    )
)

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found in PATH.
    echo Install Node.js or add npm to PATH, then run this file again.
    pause
    exit /b 1
)

if not exist "%BACKEND_DIR%\app\main.py" (
    echo Backend entry file was not found: %BACKEND_DIR%\app\main.py
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo Frontend package file was not found: %FRONTEND_DIR%\package.json
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo Backend dependencies are missing.
    echo Run: cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m pip install -e .
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo Frontend dependencies are missing.
    echo Run: cd /d "%FRONTEND_DIR%" ^&^& npm ci
    pause
    exit /b 1
)

echo Starting The Observatory...

powershell -NoProfile -Command "try { $response = Invoke-RestMethod -Uri '%BACKEND_URL%' -TimeoutSec 2; if ($response.status -eq 'ok') { exit 0 } }; exit 1" >nul 2>nul
if errorlevel 1 (
    echo Starting backend on http://127.0.0.1:8000 ...
    start "Observatory Backend" /D "%BACKEND_DIR%" /MIN cmd.exe /k ""%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
) else (
    echo Backend is already running.
)

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -Uri '%FRONTEND_URL%' -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } }; exit 1" >nul 2>nul
if errorlevel 1 (
    echo Starting frontend on http://127.0.0.1:5173 ...
    start "Observatory Frontend" /D "%FRONTEND_DIR%" /MIN cmd.exe /k npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
) else (
    echo Frontend is already running.
)

echo Waiting for the website to become ready...
powershell -NoProfile -Command "$deadline = (Get-Date).AddSeconds(45); while ((Get-Date) -lt $deadline) { $backendReady = $false; $frontendReady = $false; try { $health = Invoke-RestMethod -Uri '%BACKEND_URL%' -TimeoutSec 2; $backendReady = $health.status -eq 'ok' } catch {}; try { $page = Invoke-WebRequest -Uri '%FRONTEND_URL%' -UseBasicParsing -TimeoutSec 2; $frontendReady = $page.StatusCode -eq 200 } catch {}; if ($backendReady -and $frontendReady) { exit 0 }; Start-Sleep -Milliseconds 500 }; exit 1"

if errorlevel 1 (
    echo.
    echo The Observatory did not become ready within 45 seconds.
    echo Open the minimized Backend and Frontend windows to inspect their logs.
    pause
    exit /b 1
)

echo The Observatory is ready. Opening the website...
start "" "%FRONTEND_URL%"

endlocal
exit /b 0
