param(
  [string]$InstallDir = "$(Split-Path -Parent $PSCommandPath)\\ffmpeg"
)

$binDir = Join-Path $InstallDir "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

Write-Host "ffmpeg target: $ffmpegExe"
if (Test-Path $ffmpegExe) {
  Write-Host "ffmpeg already exists, skipping."
  exit 0
}

$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$tempDir = Join-Path $env:TEMP ("mvd_ffmpeg_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$zipPath = Join-Path $tempDir "ffmpeg.zip"
Write-Host "Downloading: $url"
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing -ErrorAction Stop

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

$foundFfmpeg = Get-ChildItem -Path $tempDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
$foundFfprobe = Get-ChildItem -Path $tempDir -Recurse -Filter "ffprobe.exe" | Select-Object -First 1

if (-not $foundFfmpeg) {
  throw "Could not find ffmpeg.exe after extraction."
}

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Copy-Item -Path $foundFfmpeg.FullName -Destination $ffmpegExe -Force
if ($foundFfprobe) {
  Copy-Item -Path $foundFfprobe.FullName -Destination $ffprobeExe -Force
}

Write-Host "Install complete. Verifying..."
& $ffmpegExe -version | Out-Host

