@echo off
rem One-click set-up of Stock Finder and Analyzer on Windows.
rem Double-click this file (or run it from Command Prompt). It is safe to run again.
rem   1. finds Python 3.10+ (installs Python 3.12 with winget if there is none)
rem   2. creates the .venv virtual environment and installs the packages
rem   3. creates sfa.env from the example and opens it in Notepad for your keys
rem   4. runs the readiness check (python -m sfa doctor)
rem   5. registers the start-at-log-on service and starts it (dashboard: http://localhost:8000)
setlocal
cd /d "%~dp0\..\.."
echo.
echo === Stock Finder and Analyzer - Windows set-up ===
echo Folder: %CD%
echo.

rem ---- 1. Python ---------------------------------------------------------------
set PY=
where py >nul 2>&1 && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set PY=py -3)
if not defined PY (
  where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set PY=python)
)
if not defined PY (
  echo Python 3.10 or newer was not found. Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo.
    echo Could not install Python automatically. Install it from https://www.python.org/downloads/windows/
    echo ^(tick "Add python.exe to PATH"^), then run this file again.
    pause
    exit /b 1
  )
  set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
echo [1/5] Python:
%PY% --version
if errorlevel 1 (
  echo Python was installed but this window cannot see it yet. Close this window and run the file again.
  pause
  exit /b 1
)

rem ---- 2. Virtual environment and packages -------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [2/5] Creating the virtual environment .venv ...
  %PY% -m venv .venv || (echo Could not create .venv & pause & exit /b 1)
) else (
  echo [2/5] Virtual environment .venv already exists.
)
".venv\Scripts\python.exe" -m pip install -q -U pip
echo       Installing packages ^(a few minutes the first time^)...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo Package install failed: see the messages above & pause & exit /b 1)

rem ---- 3. Settings -------------------------------------------------------------
if not exist sfa.env (
  copy /y sfa.env.example sfa.env >nul
  echo [3/5] Created sfa.env. Notepad opens now: fill in NEWSAPI_KEY and SFA_SEC_USER_AGENT,
  echo       save, close Notepad, and the set-up continues.
  notepad sfa.env
) else (
  echo [3/5] sfa.env already exists ^(edit it any time with: notepad sfa.env^).
)

rem ---- 4. Readiness check ------------------------------------------------------
echo [4/5] Readiness check:
".venv\Scripts\python.exe" -m sfa doctor

rem ---- 5. Service --------------------------------------------------------------
echo.
choice /c YN /m "[5/5] Start the service now and every time you log on"
if errorlevel 2 (
  echo Skipped. Start it later with: deploy\windows\start_sfa.bat ^(or install_task.ps1 for log-on start^)
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_task.ps1"
  timeout /t 8 >nul
  start "" http://localhost:8000
)
echo.
echo Done. Dashboard: http://localhost:8000   Log: %CD%\logs\sfa.log
pause
