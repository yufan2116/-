# multi_video_dl

统一的多平台视频下载器（B站/抖音/小红书），支持无水印下载。

## 功能特性

- 🎯 支持多个视频平台（B站、抖音、小红书）
- 🚫 优先下载无水印版本
- 📦 批量下载支持
- 🔄 断点续传
- 📝 元数据保存
- 🎨 自定义文件名模板
- ⚡ 并发下载

## 安装

### 方式一：Docker（推荐）

使用 Docker 可以避免本地环境配置问题，所有依赖都已包含在镜像中。

```bash
# 构建镜像
docker build -t multi-video-dl:latest .

# 使用（下载文件会保存到 ./downloads 目录）
docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx
```

详细说明请参考 [Docker 使用指南](README.Docker.md)

### 方式二：本地安装

#### 前置依赖

1. **Python 3.11+**
2. **ffmpeg**（用于 m3u8 下载）
   - Windows: 下载 [ffmpeg](https://ffmpeg.org/download.html) 并添加到 PATH
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg` 或 `sudo yum install ffmpeg`
3. **yt-dlp**（自动通过 pip 安装）

#### 安装步骤

```bash
# 克隆或下载项目后
cd multi_video_dl
pip install -e .

# 或使用 uv/poetry
uv pip install -e .
# 或
poetry install
```

## 使用方法

### 基本用法

```bash
# 下载单个视频
mvd dl https://www.bilibili.com/video/BVxxxxx

# 指定输出目录
mvd dl https://www.bilibili.com/video/BVxxxxx --out ./downloads

# 预览模式（不实际下载）
mvd dl https://www.bilibili.com/video/BVxxxxx --dry-run

# 批量下载
mvd dl -i urls.txt --out ./downloads
```

### 高级选项

```bash
# 自定义文件名模板
mvd dl <url> --template "{author} - {title} ({id})"

# 元数据保存方式
mvd dl <url> --meta json        # 仅保存 .metadata.json
mvd dl <url> --meta filename    # 仅写入文件名
mvd dl <url> --meta both        # 两者都保存

# 并发下载
mvd dl -i urls.txt --concurrency 4

# 指定后端
mvd dl <url> --backend ytdlp   # 使用 yt-dlp
mvd dl <url> --backend auto    # 自动选择

# 分P（B站多P）
# 默认不填则下载全部P；可填如 1 或 1,3-5 或 ALL
mvd dl <url> -I 1
mvd dl <url> -I 1,3-5
mvd dl <url> --only-current

# 合集（playlist）
# 默认不填则下载全部条目；可用 -I 指定，如 1 或 1,3-5
mvd dl <合集链接> -I 1,3-5
mvd dl <合集链接> --only-current
mvd dl <合集链接> --playlist-start 10 --playlist-end 20
mvd dl <合集链接> --match-filter "title*=第01集"
mvd dl <合集链接> --dateafter 20250101
mvd dl <合集链接> --playlist-reverse

# 使用 cookies（可选）
# 支持两种格式：
# - `cookies.txt`：Netscape 格式（yt-dlp 直接使用）
# - `storage_state.json`：Playwright storageState（会自动转换成 cookies.txt）
mvd dl <url> --cookies cookies.txt

# 详细日志
mvd dl <url> --verbose
```

### 一键登录态捕获（Playwright storageState）

```bash
# 打开可见浏览器，手动登录后按回车或点击页面右下角“已登录完成”
mvd capture-login bilibili -o ./auth/bilibili_storage_state.json

# 也可指定抖音/小红书
mvd capture-login douyin -o ./auth/douyin_storage_state.json
mvd capture-login xiaohongshu -o ./auth/xhs_storage_state.json

# 若文件已存在，默认不再弹登录窗口（首次登录后可一直复用）
mvd capture-login douyin -o ./auth/douyin_storage_state.json

# 登录失效时，使用 --force 重新登录并覆盖
mvd capture-login douyin -o ./auth/douyin_storage_state.json --force

# 下载时复用登录态（--cookies 支持传入 storageState json）
mvd dl <url> --cookies ./auth/douyin_storage_state.json
```

### 文件名模板变量

- `{platform}` - 平台名称（bilibili/douyin/xiaohongshu）
- `{author}` - 作者/UP主
- `{title}` - 视频标题
- `{id}` - 视频ID
- `{date}` - 发布日期（YYYYMMDD）
- `{ext}` - 文件扩展名

### urls.txt 格式

```
# 这是注释，会被忽略
https://www.bilibili.com/video/BVxxxxx1
https://www.bilibili.com/video/BVxxxxx2

# 空行也会被忽略
https://www.bilibili.com/video/BVxxxxx3
```

## 架构说明

项目采用插件化架构：

- **Extractors**: 各平台的解析器（`extractors/`）
- **Downloaders**: 下载器（httpx、ffmpeg、yt-dlp）
- **Store**: 文件存储和元数据管理
- **Pipeline**: 统一的处理流程

## 开发

### 添加新平台

1. 在 `extractors/` 目录创建新的 extractor（继承 `BaseExtractor`）
2. 实现 `match()` 和 `parse()` 方法
3. 在 `extractors/__init__.py` 中注册

### 运行测试

```bash
pytest tests/
```

## 许可证

MIT License

## 注意事项

- 请遵守各平台的使用条款
- 下载的内容仅供个人学习使用
- 不要用于商业用途或大规模爬取
