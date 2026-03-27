# Docker 测试脚本 (PowerShell)

Write-Host "=== 构建 Docker 镜像 ===" -ForegroundColor Green
docker build -t multi-video-dl:latest .

Write-Host ""
Write-Host "=== 测试帮助命令 ===" -ForegroundColor Green
docker run --rm multi-video-dl:latest --help

Write-Host ""
Write-Host "=== 测试 dry-run（需要替换为实际的 B站 URL）===" -ForegroundColor Yellow
# docker run --rm multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx --dry-run

Write-Host ""
Write-Host "=== 镜像信息 ===" -ForegroundColor Green
docker images multi-video-dl:latest

Write-Host ""
Write-Host "✅ Docker 镜像构建成功！" -ForegroundColor Green
Write-Host ""
Write-Host "使用方法：" -ForegroundColor Cyan
Write-Host "  docker run --rm -v `${PWD}/downloads:/downloads \"
Write-Host "    multi-video-dl:latest dl <url>"
