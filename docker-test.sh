#!/bin/bash
# Docker 测试脚本

set -e

echo "=== 构建 Docker 镜像 ==="
docker build -t multi-video-dl:latest .

echo ""
echo "=== 测试帮助命令 ==="
docker run --rm multi-video-dl:latest --help

echo ""
echo "=== 测试 dry-run（需要替换为实际的 B站 URL）==="
# docker run --rm multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx --dry-run

echo ""
echo "=== 镜像信息 ==="
docker images multi-video-dl:latest

echo ""
echo "✅ Docker 镜像构建成功！"
echo ""
echo "使用方法："
echo "  docker run --rm -v \$(pwd)/downloads:/downloads \\"
echo "    multi-video-dl:latest dl <url>"
