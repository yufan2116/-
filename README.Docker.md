# Docker 使用指南

## 构建镜像

```bash
# 在项目根目录执行
docker build -t multi-video-dl:latest .
```

## 使用方法

### 基本用法

```bash
# 下载单个视频
docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx

# 预览模式（不实际下载）
docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx --dry-run
```

### 使用 docker-compose

```bash
# 下载单个视频
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx

# 批量下载（需要先创建 urls.txt）
docker-compose run --rm mvd dl -i /app/urls.txt

# 指定输出目录和模板
docker-compose run --rm mvd dl <url> \
  --out /downloads \
  --template "{author} - {title} ({id})"
```

### Windows PowerShell 示例

```powershell
# 下载单个视频
docker run --rm -v ${PWD}/downloads:/downloads `
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx

# 使用 docker-compose
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx
```

## 挂载说明

- `./downloads:/downloads` - 下载文件保存到宿主机的 `./downloads` 目录
- `./urls.txt:/app/urls.txt:ro` - 只读挂载 URL 列表文件（可选）
- `./cookies.txt:/app/cookies.txt:ro` - 只读挂载 cookies 文件（可选）

## 环境变量

- `PYTHONUNBUFFERED=1` - 禁用 Python 输出缓冲
- `MVD_OUTPUT_DIR=/downloads` - 默认输出目录

## 注意事项

1. 确保宿主机有足够的磁盘空间
2. 下载的文件会保存在挂载的 `downloads` 目录中
3. 使用 `--rm` 标志会在容器退出后自动删除容器
4. 如果需要持久化配置，可以创建自定义镜像或使用 volumes

## 高级用法

### 交互式使用

```bash
# 进入容器交互式 shell
docker run -it --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest /bin/bash

# 在容器内执行命令
mvd dl https://www.bilibili.com/video/BVxxxxx --verbose
```

### 自定义构建

如果需要添加额外的系统依赖或修改配置，可以基于 Dockerfile 创建自定义镜像：

```dockerfile
FROM multi-video-dl:latest

# 添加额外的依赖
RUN apt-get update && apt-get install -y \
    your-package \
    && rm -rf /var/lib/apt/lists/*

# 复制自定义配置
COPY custom-config.json /app/config.json
```
