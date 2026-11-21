# Removes the Orbweaver Keymap launcher installed by install.ps1 (the .exe, its
# settings and log, and the shortcuts). The QMK repository and your keymaps
# are not touched.
#
#   powershell -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\Orbweaver Keymap\uninstall.ps1"

$ErrorActionPreference = "Stop"
$dest = Join-Path $env:LOCALAPPDATA "Programs\Orbweaver Keymap"
if (Get-Process OrbweaverKeymap -ErrorAction SilentlyContinue) {
    throw "Orbweaver Keymap is running; quit it from its tray icon first."
}
foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath("Programs")) "Orbweaver Keymap.lnk"),
                   (Join-Path ([Environment]::GetFolderPath("Desktop")) "Orbweaver Keymap.lnk"))) {
    if (Test-Path $lnk) { Remove-Item $lnk; Write-Output "removed $lnk" }
}
$logs = Join-Path $env:LOCALAPPDATA "Orbweaver Keymap"
if (Test-Path $logs) { Remove-Item -Recurse $logs; Write-Output "removed $logs" }
if (Test-Path $dest) {
    # this script may be running from $dest; delete the folder after it exits
    Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$dest`""
    Write-Output "removing $dest"
}
