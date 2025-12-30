# PowerShell script to create Windows Scheduled Task for Tail Betting Monitor
# Run as Administrator

$TaskName = "PolymarketTailMonitor"
$ProjectDir = "C:\Users\amalio\Desktop\PROGRAMACION\01-VS_CODE\32-POLYMARKET-BOT"
$PythonPath = "python"
$ScriptPath = "$ProjectDir\scripts\scheduled_monitor.py"
$LogPath = "$ProjectDir\logs\scheduled_task.log"

# Create logs directory
New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

# Create the scheduled task action
$Action = New-ScheduledTaskAction -Execute $PythonPath `
    -Argument "$ScriptPath" `
    -WorkingDirectory $ProjectDir

# Trigger: Every 30 minutes
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Days 365)

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Register the task
Register-ScheduledTask -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Monitors Polymarket tail bets, checks resolutions, and places new bets"

Write-Host "Scheduled task '$TaskName' created successfully!"
Write-Host ""
Write-Host "To manage:"
Write-Host "  Start:   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Stop:    Stop-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Disable: Disable-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Remove:  Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "View in Task Scheduler: taskschd.msc"
