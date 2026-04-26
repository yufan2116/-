# multi_video_dl

Bilibili（B 站）视频下载器：支持 CLI 与本地 Web 控制台，基于 yt-dlp 解析与统一下载管线。

## 功能特性

- B 站视频 / 番剧 / 短链（b23.tv）等链接解析，支持 BV、av、纯数字输入
- 分 P、合集（playlist）与清晰度选择
- 批量下载、并发、元数据与自定义文件名模板
- 可选：Playwright 捕获 B 站登录态（`storageState`）供高码率或风控场景使用

## 安装

### 方式一：Docker

```bash
docker build -t multi-video-dl:latest .

docker run --rm -v $(pwd)/downloads:/downloads \
  multi-video-dl:latest dl https://www.bilibili.com/video/BVxxxxx
```

详细说明见 [Docker 使用指南](README.Docker.md)。

### 方式二：本地安装

1. **Python 3.11+**
2. **ffmpeg**（m3u8 等场景）
3. 项目目录下：`pip install -e .`（会安装 **yt-dlp** 等依赖）

## 使用方法

### Web 控制台

```bash
python run_gui_entry.py
```

默认打开 `http://127.0.0.1:8765`，可进行链接预览、一键登录 B 站、下载与日志查看。

### CLI

```bash
mvd dl https://www.bilibili.com/video/BVxxxxx
mvd dl https://www.bilibili.com/video/BVxxxxx --out ./downloads
mvd dl -i urls.txt --out ./downloads
mvd dl <url> --dry-run
```

分 P / 合集等选项与原先一致，参见 `mvd dl --help`。

### 登录态捕获（可选）

需本地安装：`pip install playwright` 且 `playwright install chromium`。

```bash
mvd capture-login -o ./auth/bilibili_state.json
mvd capture-login -o ./auth/bilibili_state.json --force
mvd dl <url> --cookies ./auth/bilibili_state.json
```

### 文件名模板变量

- `{platform}` - 平台名称（bilibili）
- `{author}` - UP 主
- `{title}` - 标题
- `{id}` - 视频 ID
- `{date}` - 发布日期（YYYYMMDD）
- `{ext}` - 扩展名

### urls.txt

支持 `#` 注释、空行；每行可为完整 URL 或 BV/av 等（与 CLI 一致）。

## 架构说明

- **extractors**：`BilibiliExtractor`（yt-dlp）
- **downloaders**：httpx / ffmpeg / yt-dlp
- **Pipeline**：统一解析、选择清晰度、落盘与元数据

## 开发

```bash
pytest tests/
```

## 许可证

MIT License

## 注意事项

- 请遵守 B 站服务条款与版权规定
- 下载内容仅供个人学习使用
