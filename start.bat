@echo off
setlocal
cd /d "%~dp0"

title FireFlink 4.0 League Tracker
echo.
echo  FireFlink 4.0 League Tracker
echo  http://127.0.0.1:8000
echo.

REM --- Python venv (one-time if missing; does NOT create/reset admin) ---
if not exist "backend\.venv\Scripts\uvicorn.exe" (
  echo Setting up Python environment...
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python is not on PATH. Install Python 3.12+ and try again.
    pause
    exit /b 1
  )
  pushd backend
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: could not create .venv
    popd
    pause
    exit /b 1
  )
  .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 (
    echo ERROR: pip install failed
    popd
    pause
    exit /b 1
  )
  popd
  echo.
  echo NOTE: If this is a brand-new install with no database yet, create an admin once:
  echo   cd backend
  echo   .venv\Scripts\python manage.py create-admin admin
  echo.
)

REM --- Frontend build (one-time if missing) ---
if not exist "frontend\dist\index.html" (
  echo Building frontend...
  where npm >nul 2>&1
  if errorlevel 1 (
    echo ERROR: npm is not on PATH. Install Node.js and try again.
    pause
    exit /b 1
  )
  pushd frontend
  call npm install
  if errorlevel 1 (
    echo ERROR: npm install failed
    popd
    pause
    exit /b 1
  )
  call npm run build
  if errorlevel 1 (
    echo ERROR: npm run build failed
    popd
    pause
    exit /b 1
  )
  popd
)

REM Open the browser shortly after the server starts
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000/"

echo Starting server... close this window to stop the app.
echo.
cd backend
".venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo Server stopped with an error.
  pause
)
endlocal
