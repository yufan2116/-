param(
    [string]$InstallDir = "$(Split-Path -Parent $PSCommandPath)\\ffmpeg"
)

Write-Host "Start installing ffmpeg to: $InstallDir"

$binDir = Join-Path $InstallDir "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

if (Test-Path $ffmpegExe) {
    Write-Host "ffmpeg already exists, skip: $ffmpegExe"
    exit 0
}

$urls = @(
    # gyan.dev: ffmpeg.exe / ffprobe.exe essentials build
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)

$tempDir = Join-Path $env:TEMP ("mvd_ffmpeg_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$zipPath = Join-Path $tempDir "ffmpeg.zip"
$downloaded = $false

foreach ($u in $urls) {
    try {
        Write-Host "Downloading: $u"
        Invoke-WebRequest -Uri $u -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
        $downloaded = $true
        break
    } catch {
        Write-Host "Download failed: $u"
    }
}

if (-not $downloaded) {
    throw "All ffmpeg download URLs failed."
}

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

Write-Host "Locating ffmpeg.exe..."
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

