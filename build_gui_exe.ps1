param(
    [string]$Name = "MultiVideoDL",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
cd $projectRoot

# venv 在 D:\Download-tool\.venv（而不是 multi_video_dl/ 内）
$repoRoot = Split-Path -Parent $projectRoot
$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $venvPy)) {
    throw "找不到虚拟环境 python：$venvPy"
}

& $venvPy -m pip install -U pyinstaller

$pyinstallerArgs = @(
    "--noconfirm"
    "--onefile"
    "--windowed"
    "--name", $Name
    "--add-data", "ffmpeg\bin\ffmpeg.exe;ffmpeg\bin"
    "run_gui_entry.py"
)

if ($Clean) {
    $pyinstallerArgs += "--clean"
}

& $venvPy -m PyInstaller @pyinstallerArgs

Write-Host "Done. exe output: $projectRoot\dist\$Name.exe"

