$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Logs = Join-Path $ProjectRoot "logs"
$Url = "http://127.0.0.1:8050/"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing project Python environment at $Python. Run setup first."
}

if (-not (Test-Path -LiteralPath $Logs)) {
    New-Item -ItemType Directory -Path $Logs | Out-Null
}

$listener = Get-NetTCPConnection -LocalPort 8050 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $listener) {
    Start-Process `
        -FilePath $Python `
        -ArgumentList @(".\app.py", "--http-host", "0.0.0.0", "--http-port", "8050") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "tracker.out.log") `
        -RedirectStandardError (Join-Path $Logs "tracker.err.log") | Out-Null

    for ($i = 0; $i -lt 20; $i++) {
        try {
            Invoke-WebRequest -UseBasicParsing "$Url`health" -TimeoutSec 2 | Out-Null
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
}

Start-Process $Url
