@echo off
rem Starts the Stock Finder and Analyzer service (scheduler + dashboard on http://localhost:8000).
rem Run by the "Stock Finder and Analyzer" scheduled task at log-on; can also be double-clicked.
cd /d "%~dp0\..\.."
if not exist logs mkdir logs
if exist ".venv\Scripts\python.exe" (set PY=.venv\Scripts\python.exe) else (set PY=python)
"%PY%" -m sfa start >> logs\sfa.log 2>&1
