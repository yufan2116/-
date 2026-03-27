# Docker 快速启动指南

## 第一步：构建镜像

在项目根目录（`multi_video_dl`）执行：

```bash
docker build -t multi-video-dl:latest .
```

## 第二步：运行容器

### Windows PowerShell

```powershell
# 1. 先创建下载目录（如果不存在）
New-Item -ItemType Directory -Force -Path downloads

# 2. 下载单个视频
docker run --rm -v ${PWD}/downloads:/downloads `
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx

# 3. 预览模式（不实际下载，只查看信息）
docker run --rm -v ${PWD}/downloads:/downloads `
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx --dry-run

# 4. 批量下载（需要先创建 urls.txt 文件）
docker run --rm -v ${PWD}/downloads:/downloads -v ${PWD}/urls.txt:/app/urls.txt:ro `
  multi-video-dl:latest dl -i /app/urls.txt
```

### Linux/Mac

```bash
# 1. 先创建下载目录（如果不存在）
mkdir -p downloads

# 2. 下载单个视频
docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx

# 3. 预览模式
docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx --dry-run

# 4. 批量下载
docker run --rm -v $(pwd)/downloads:/downloads -v $(pwd)/urls.txt:/app/urls.txt:ro \
  multi-video-dl:latest dl -i /app/urls.txt
```

## 方法二：使用 docker-compose（推荐）

### Windows PowerShell

```powershell
# 1. 构建并运行（首次会自动构建）
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx

# 2. 预览模式
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx --dry-run

# 3. 批量下载（需要先创建 urls.txt）
docker-compose run --rm mvd dl -i /app/urls.txt

# 4. 带更多参数
docker-compose run --rm mvd dl <url> `
  --out /downloads `
  --template "{author} - {title} ({id})" `
  --verbose
```

### Linux/Mac

```bash
# 1. 构建并运行
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx

# 2. 预览模式
docker-compose run --rm mvd dl https://www.bilibili.com/video/BVxxxxx --dry-run

# 3. 批量下载
docker-compose run --rm mvd dl -i /app/urls.txt
```

## 完整示例

### 示例 1：下载 B站视频

```powershell
# Windows PowerShell
docker run --rm -v ${PWD}/downloads:/downloads `
  multi-video-dl:latest dl https://www.bilibili.com/video/BV1xx411c7mD
```

### 示例 2：自定义文件名模板

```powershell
docker run --rm -v ${PWD}/downloads:/downloads `
  multi-video-dl:latest dl <url> `
  --template "{author} - {title} ({id})"
```

### 示例 3：批量下载

```powershell
# 1. 创建 urls.txt 文件
@"
https://www.bilibili.com/video/BVxxxxx1
https://www.bilibili.com/video/BVxxxxx2
https://www.bilibili.com/video/BVxxxxx3
"@ | Out-File -Encoding utf8 urls.txt

# 2. 批量下载
docker run --rm -v ${PWD}/downloads:/downloads -v ${PWD}/urls.txt:/app/urls.txt:ro `
  multi-video-dl:latest dl -i /app/urls.txt --concurrency 3
```

## 常用参数说明

- `--rm` - 容器运行后自动删除
- `-v ${PWD}/downloads:/downloads` - 将下载目录挂载到容器
- `--dry-run` - 预览模式，不实际下载
- `--verbose` - 显示详细日志
- `--out /downloads` - 指定输出目录（容器内路径）
- `--template` - 自定义文件名模板
- `-i /app/urls.txt` - 批量下载，从文件读取 URL

## 查看帮助

```bash
docker run --rm multi-video-dl:latest --help
docker run --rm multi-video-dl:latest dl --help
```

## 注意事项

1. **首次使用需要构建镜像**：`docker build -t multi-video-dl:latest .`
2. **下载的文件位置**：会保存在项目目录下的 `downloads` 文件夹中
3. **替换 URL**：将命令中的 `BVxxxxx` 替换为实际的 B站视频 ID
4. **PowerShell 换行**：使用反引号 `` ` `` 进行换行
