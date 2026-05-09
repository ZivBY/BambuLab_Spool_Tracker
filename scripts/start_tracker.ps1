$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

Set-Location -LiteralPath $ProjectRoot
& $Python .\app.py --http-host 127.0.0.1 --http-port 8050
