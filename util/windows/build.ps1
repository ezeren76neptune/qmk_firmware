# Builds util\windows\bin\OrbweaverKeymap.exe (tray launcher for the Orbweaver
# keymap editor) with the C# compiler that comes with the .NET Framework 4.x,
# which every Windows 10/11 has. Nothing is downloaded.
#
#   powershell -ExecutionPolicy Bypass -File util\windows\build.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "No .NET Framework 4 C# compiler (csc.exe) found under $env:WINDIR\Microsoft.NET" }

$src = Join-Path $here "OrbweaverKeymap.cs"
$ico = Join-Path $here "orbweaver_keymap.ico"
$out = Join-Path $here "bin\OrbweaverKeymap.exe"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null

& $csc /nologo /target:winexe /optimize+ /platform:anycpu "/out:$out" "/win32icon:$ico" "/resource:$ico,orbweaver_keymap.ico" `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $src
if ($LASTEXITCODE -ne 0) { throw "csc failed ($LASTEXITCODE)" }
Write-Output "built $out ($((Get-Item $out).Length) bytes)"
