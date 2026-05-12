$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }

Set-Location -LiteralPath $ProjectRoot
& $Python .\app.py --http-host 0.0.0.0 --http-port 8050
