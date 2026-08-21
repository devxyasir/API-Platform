@echo off
setlocal enabledelayedexpansion
title LLM Gateway - Dev Stack
color 0A

rem ============================================================
rem  LLM Gateway - local dev stack launcher
rem  Starts: backend API (8000), user dashboard (3000), admin console (3001)
rem ============================================================
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "ADMIN=%ROOT%frontend-admin"

rem --- read admin credentials from backend/.env for the banner ---
set "ADMIN_EMAIL="
set "ADMIN_PASSWORD="
set "ADMIN_NAME=Administrator"
for /f "usebackq tokens=1,* delims==" %%a in ("%BACKEND%\.env") do (
    if /i "%%a"=="ADMIN_EMAIL" set "ADMIN_EMAIL=%%b"
    if /i "%%a"=="ADMIN_PASSWORD" set "ADMIN_PASSWORD=%%b"
    if /i "%%a"=="ADMIN_NAME" set "ADMIN_NAME=%%b"
)

echo.
echo  ============================================================
echo   LLM GATEWAY - DEV STACK
echo  ============================================================
echo.
echo   URLs
echo     Backend API    : http://localhost:8000
echo     OpenAI base URL: http://localhost:8000/v1
echo     API docs       : http://localhost:8000/docs
echo     User dashboard : http://localhost:3000
echo     Admin console  : http://localhost:3001
echo.
echo   Admin login
if defined ADMIN_EMAIL (
    echo     Email    : %ADMIN_EMAIL%
    if defined ADMIN_PASSWORD (
        echo     Password : %ADMIN_PASSWORD%
    ) else (
        echo     Password : not set in .env - first registered user becomes admin/owner
    )
) else (
    echo     No seeded admin in .env - register the FIRST account at
    echo     http://localhost:3001/login  to become admin/owner.
)
echo.
echo   Models
echo     gpt-4o, gpt-4o-mini, gpt-3.5-turbo   (OpenAI upstream)
echo     notrack-c / notrack                   (notrack.ai, keyless)
echo.
echo   API keys: create them in the User dashboard (API Keys page) - use those
echo   sk_... keys as Bearer tokens against http://localhost:8000/v1.
echo   CORS origins allowed: http://localhost:3000, http://localhost:3001
echo.
echo  ============================================================
echo   Starting services in separate windows...
echo   Close THIS window anytime to stop the launcher (services keep running).
echo   Press Ctrl+C inside a service window to stop that service.
echo  ============================================================
echo.

rem --- prerequisites ---
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo [ERROR] Python venv missing: %BACKEND%\.venv
    echo         Create it with:  cd /d "%BACKEND%"  ^&^&  python -m venv .venv
    echo         Then:            "%BACKEND%\.venv\Scripts\pip" install -r "%BACKEND%\requirements.txt"
    pause
    exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
    echo [INFO] Installing user dashboard dependencies...
    pushd "%FRONTEND%"
    call npm install
    popd
)
if not exist "%ADMIN%\node_modules" (
    echo [INFO] Installing admin console dependencies...
    pushd "%ADMIN%"
    call npm install
    popd
)

rem --- warn if a target port is already in use ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo [WARN] Port 8000 appears to be in use ^(PID %%p^) - backend may fail to start.
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo [WARN] Port 3000 appears to be in use ^(PID %%p^) - user dashboard may fail to start.
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :3001 ^| findstr LISTENING') do (
    echo [WARN] Port 3001 appears to be in use ^(PID %%p^) - admin console may fail to start.
)
echo.

rem --- start backend (port 8000) ---
start "LLM Gateway - Backend (8000)" cmd /k "set "CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"&& cd /d "%BACKEND%" && ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000"

rem --- start user dashboard (port 3000) ---
start "LLM Gateway - User Dashboard (3000)" cmd /k "set "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000"&& set "PORT=3000"&& cd /d "%FRONTEND%" && call npm run dev"

rem --- start admin console (port 3001) ---
start "LLM Gateway - Admin Console (3001)" cmd /k "set "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000"&& set "PORT=3001"&& cd /d "%ADMIN%" && call npm run dev"

echo  All services launched. Waiting a moment for the backend to boot...
timeout /t 5 /nobreak >nul

rem --- confirm backend is up ---
set "READY="
for /l %%i in (1,1,10) do (
    ping -n 1 127.0.0.1 >nul
    if not defined READY (
        powershell -NoProfile -Command "try { $r=Invoke-WebRequest -Uri 'http://localhost:8000/health/live' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 set "READY=1"
    )
)
if defined READY (
    echo  Backend is UP at http://localhost:8000/health/live
) else (
    echo  Backend did not respond yet - check its window for errors.
)
echo.
echo  Open the admin console: http://localhost:3001
echo  Open the user dashboard: http://localhost:3000
echo.
pause