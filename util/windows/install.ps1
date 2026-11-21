# Installs the Orbweaver keymap editor launcher for the current user:
#   %LOCALAPPDATA%\Programs\Orbweaver Keymap\OrbweaverKeymap.exe (+ .ini, uninstall.ps1)
#   Start Menu > Orbweaver Keymap   (and a desktop shortcut with -Desktop)
# No administrator rights needed. The editor keeps working from this QMK
# repository (it builds the firmware there), so do not move or delete it.
#
#   powershell -ExecutionPolicy Bypass -File util\windows\install.ps1 [-Desktop]

param([switch]$Desktop)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
$exe = Join-Path $here "bin\OrbweaverKeymap.exe"
if (-not (Test-Path $exe)) { & (Join-Path $here "build.ps1") }

$dest = Join-Path $env:LOCALAPPDATA "Programs\Orbweaver Keymap"
New-Item -ItemType Directory -Force $dest | Out-Null
# a running copy holds the .exe open: ask it to stop first
Get-Process OrbweaverKeymap -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $dest "OrbweaverKeymap.exe") } |
    ForEach-Object { throw "Orbweaver Keymap is running; quit it from its tray icon, then install again." }
Copy-Item $exe $dest -Force
Copy-Item (Join-Path $here "uninstall.ps1") $dest -Force

$ini = Join-Path $dest "OrbweaverKeymap.ini"
if (-not (Test-Path $ini)) {
    @(
        "; Orbweaver Keymap settings",
        "; the QMK repository that holds keyboards\razer\orbweaver and util\razer_orbweaver_editor.py",
        "repo=$repo",
        "; keymap folder under keyboards\razer\orbweaver\stock\keymaps",
        "keymap=mine",
        "port=8765",
        "; optional: full path to python.exe (default: the py launcher, then PATH)",
        "python="
    ) | Set-Content -Encoding utf8 $ini
}

$shell = New-Object -ComObject WScript.Shell
function New-Shortcut($path) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = Join-Path $dest "OrbweaverKeymap.exe"
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = (Join-Path $dest "OrbweaverKeymap.exe") + ",0"
    $lnk.Description = "Edit and flash the Razer Orbweaver QMK keymap"
    $lnk.Save()
    Write-Output "shortcut: $path"
}
New-Shortcut (Join-Path ([Environment]::GetFolderPath("Programs")) "Orbweaver Keymap.lnk")
if ($Desktop) { New-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Orbweaver Keymap.lnk") }

Write-Output "installed to $dest (repository: $repo)"
