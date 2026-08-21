@echo off
setlocal enabledelayedexpansion
title LLM Gateway - Dev Stack
color 0A

echo ============================================================
echo  LLM Gateway - local dev stack
echo ============================================================
echo.

REM --- locate project root (script's own folder)
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "ADMIN=%ROOT%frontend-admin"

REM --- read .env admin credentials for the banner
set "ADMIN_EMAIL="
set "ADMIN_PASSWORD="
for /f "usebackq tokens=1,* delims==" %%a in ("%BACKEND%\.env") do (
  set "line=%%a"
  if /i "%%a"=="ADMIN_EMAIL" set "ADMIN_EMAIL=%%b"
  if /i "%%a"=="ADMIN_PASSWORD" set "ADMIN_PASSWORD=%%b"
  if /i "%%a"=="ADMIN_NAME" set "ADMIN_NAME=%%b"
)

echo  URLs:
echo    Backend API   : http://localhost:8000  (OpenAI base: http://localhost:8000/v1)
echo    API docs      : http://localhost:8000/docs
echo    User dashboard: http://localhost:3000
echo    Admin console : http://localhost:3001  (frontend-admin)
echo.
echo  Admin login:
if defined ADMIN_EMAIL (
  echo    Email    : %ADMIN_EMAIL%
  if defined ADMIN_PASSWORD (
    echo    Password : %ADMIN_PASSWORD%
  ) else (
    echo    Password : (not set - first registered user becomes admin)
  )
) else (
  echo    No seeded admin in .env - register the FIRST account at
  echo    http://localhost:3001/login  to become admin/owner.
)
echo.
echo  Models: gpt-4o, gpt-4o-mini, gpt-3.5-turbo, notrack-c (via notrack.ai, keyless)
echo.
echo  Starting services in separate windows...
echo  Close this window to leave the services running; press Ctrl+C in each service window to stop it.
echo.

REM --- verify prerequisites
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo [ERROR] Python venv missing at %BACKEND%\.venv
  echo         Run:  cd /d "%BACKEND%"  ^&^&  python -m venv .venv
  pause
  exit /b 1
)
if not exist "%FRONTEND%\node_modules" (
  echo [INFO] Installing frontend dependencies...
  pushd "%FRONTEND%"
  call npm install
  popd
)
if not exist "%ADMIN%\node_modules" (
  echo [INFO] Installing admin dependencies...
  pushd "%ADMIN%"
  call npm install
  popd
)

REM --- start backend
start "LLM Gateway - Backend (8000)" cmd /k "cd /d "%BACKEND%" && ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000"

REM --- start user dashboard (3000)
start "LLM Gateway - User Dashboard (3000)" cmd /k "set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000&& cd /d "%FRONTEND%" && call npm run dev"

REM --- start admin console (3001)
start "LLM Gateway - Admin Console (3001)" cmd /k "set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000&& cd /d "%ADMIN%" && call npm run dev -- -p 3001"

echo All services launched.
echo.
pause