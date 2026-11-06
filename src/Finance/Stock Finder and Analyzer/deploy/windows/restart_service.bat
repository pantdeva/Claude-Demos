@echo off
rem Restarts the Stock Finder and Analyzer service, e.g. after changing sfa.env or updating the app.
rem Double-click it. Stops the scheduled task and any "python -m sfa start" process, then starts the task again.
set TASK=Stock Finder and Analyzer
echo Stopping "%TASK%" ...
schtasks /End /TN "%TASK%" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*-m sfa start*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 3 >nul
echo Starting "%TASK%" ...
schtasks /Run /TN "%TASK%"
if errorlevel 1 (
  echo The scheduled task was not found: starting the service in this window instead.
  call "%~dp0start_sfa.bat"
)
timeout /t 10
