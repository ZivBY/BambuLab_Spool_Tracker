$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start_tracker.ps1"
$ShortcutName = "Bambu Spool Tracker.lnk"

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".env"))) {
    throw "Missing .env in $ProjectRoot. Create it before installing the startup task."
}

$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder $ShortcutName
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShell
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Save()

Write-Host "Installed startup shortcut: $ShortcutPath"
Write-Host "Dashboard URL on this PC: http://127.0.0.1:8050/"
Write-Host "Dashboard URL from another device: http://<this-computer-ip>:8050/"
