# Registers a Windows scheduled task that starts the service when you log on and
# restarts it if it stops. Run in PowerShell from this folder:
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1
$ErrorActionPreference = "Stop"
$bat  = Join-Path $PSScriptRoot "start_sfa.bat"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$name = "Stock Finder and Analyzer"
$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
            -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Description "Stock Finder and Analyzer: scheduler + dashboard (http://localhost:8000)" -Force | Out-Null
Start-ScheduledTask -TaskName $name
Write-Host "Installed and started '$name'. Dashboard: http://localhost:8000  Log: $root\logs\sfa.log"
