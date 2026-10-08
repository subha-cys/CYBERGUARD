$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$taskName = 'CYBERGUARD Local Analysis Service'

if (-not (Test-Path $python) -or -not (Test-Path $pythonw)) {
    throw 'Project environment not found. Create .venv and install the project dependencies first.'
}

Push-Location $root
try {
    & $python -c 'from backend.service import analyze_request'
    if ($LASTEXITCODE -ne 0) {
        throw 'The local service dependencies are not ready. Install project dependencies before enabling startup.'
    }
} finally {
    Pop-Location
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '-m backend.web --host 127.0.0.1 --port 8765' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts the loopback-only CYBERGUARD analysis API at sign-in.' -Force | Out-Null
Write-Host "Installed '$taskName'. It starts at your next Windows sign-in."
Write-Host 'To remove it, run .\extension\Uninstall-Startup.ps1.'