# Removes the scheduled task (the data in db\ is kept).
Stop-ScheduledTask -TaskName "Stock Finder and Analyzer" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Stock Finder and Analyzer" -Confirm:$false
Write-Host "Removed. Stop any running python.exe for the app from Task Manager if the dashboard is still up."
