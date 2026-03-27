"""下载器实现"""

import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict

import httpx
from yt_dlp import YoutubeDL

from .errors import (
    DownloaderError,
    FFmpegNotFoundError,
    YtDlpNotFoundError,
    DownloadError,
    ErrorStage,
    ErrorContext,
)
from .models import MediaItem, Backend, MediaType
from .utils import check_ffmpeg, check_ytdlp, get_ffmpeg_path

logger = logging.getLogger(__name__)


class BaseDownloader:
    """下载器基类"""
    
    async def download(
        self,
        item: MediaItem,
        output_path: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        """下载媒体项到指定路径"""
        raise NotImplementedError


class HTTPXDownloader(BaseDownloader):
    """使用 httpx 进行流式下载（支持断点续传）"""
    
    async def download(
        self,
        item: MediaItem,
        output_path: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        """下载文件"""
        if not item.direct_url:
            raise DownloadError(
                "媒体项缺少直接下载地址（direct_url）。",
                stage=ErrorStage.PREPARE,
                context=ErrorContext(extra={"item_ext": item.ext, "quality": item.quality}),
            )
        
        url = item.direct_url
        merged_headers = {**(item.headers or {}), **(headers or {})}
        
        # 检查是否已存在部分文件（断点续传）
        resume_pos = 0
        if output_path.exists():
            resume_pos = output_path.stat().st_size
            if resume_pos > 0:
                logger.info(f"Resuming download from position {resume_pos}")
                merged_headers["Range"] = f"bytes={resume_pos}-"
        
        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=merged_headers) as response:
                    response.raise_for_status()

                    # 如果是断点续传且服务器不支持 Range，从头开始
                    if resume_pos > 0 and response.status_code != 206:
                        logger.warning("Server doesn't support Range, restarting download")
                        resume_pos = 0
                        output_path.unlink(missing_ok=True)

                    # 确保输出目录存在
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    mode = "ab" if resume_pos > 0 else "wb"
                    with open(output_path, mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)

                    logger.info(f"Downloaded to {output_path}")
                    return output_path
        except Exception as e:
            raise DownloadError(
                "HTTP 下载失败，请检查网络连接或重试。",
                stage=ErrorStage.DOWNLOAD,
                context=ErrorContext(
                    extra={
                        "url": url,
                        "resume_pos": resume_pos,
                        "reason": str(e),
                    }
                ),
            ) from e


class FFmpegDownloader(BaseDownloader):
    """使用 ffmpeg 下载 m3u8 等流媒体"""
    
    def __init__(self):
        if not check_ffmpeg():
            raise FFmpegNotFoundError(
                "未检测到 ffmpeg，请确认已安装并加入 PATH。",
                stage=ErrorStage.DEPENDENCY,
            )
        self.ffmpeg_path = get_ffmpeg_path()
    
    async def download(
        self,
        item: MediaItem,
        output_path: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        """使用 ffmpeg 下载"""
        url = item.manifest_url or item.direct_url
        if not url:
            raise DownloadError(
                "媒体项既没有 manifest_url 也没有 direct_url。",
                stage=ErrorStage.PREPARE,
            )
        
        merged_headers = {**(item.headers or {}), **(headers or {})}
        
        # 构建 ffmpeg 命令
        cmd = [self.ffmpeg_path, "-y"]  # -y 覆盖输出文件
        
        # 添加 headers（通过 -headers 参数）
        if merged_headers:
            header_str = "\r\n".join(f"{k}: {v}" for k, v in merged_headers.items())
            cmd.extend(["-headers", header_str])
        
        # 输入 URL
        cmd.extend(["-i", url])
        
        # 输出参数
        cmd.extend(["-c", "copy"])  # 直接复制流，不重新编码
        cmd.append(str(output_path))
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 运行 ffmpeg（异步执行）
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore")
                raise DownloadError(
                    "ffmpeg 执行失败，请检查 ffmpeg 是否正常可用。",
                    stage=ErrorStage.DOWNLOAD,
                    context=ErrorContext(extra={"ffmpeg_error": error_msg.strip()}),
                )

            logger.info(f"Downloaded via ffmpeg to {output_path}")
            return output_path
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                "找不到 ffmpeg 可执行文件，请检查安装路径。",
                stage=ErrorStage.DEPENDENCY,
            )
        except Exception as e:
            raise DownloadError(
                "使用 ffmpeg 下载时发生未知错误。",
                stage=ErrorStage.DOWNLOAD,
                context=ErrorContext(extra={"reason": str(e)}),
            ) from e


class YtDlpDownloader(BaseDownloader):
    """使用 yt-dlp 下载（直接委托给 yt-dlp）"""
    
    def __init__(self):
        if not check_ytdlp():
            raise YtDlpNotFoundError(
                "未检测到 yt-dlp，请先安装：pip install yt-dlp",
                stage=ErrorStage.DEPENDENCY,
            )
    
    async def download(
        self,
        item: MediaItem,
        output_path: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        """使用 yt-dlp 下载"""
        # yt-dlp 通常需要源 URL，从 item.extra 获取
        source_url = item.extra.get("source_url") if item.extra else None
        if not source_url:
            # 如果没有 source_url，尝试使用 direct_url 或 manifest_url
            source_url = item.direct_url or item.manifest_url
        if not source_url:
            raise DownloadError(
                "yt-dlp 下载器需要 source_url 或可用的直链 URL。",
                stage=ErrorStage.PREPARE,
            )
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建 yt-dlp 选项
        # 使用不带扩展名的路径，让 yt-dlp 自动添加
        base_path = output_path.with_suffix("")
        # 注意：
        # 1) 使用 bestvideo+bestaudio 会触发合并（merge），merge 依赖 ffmpeg。
        # 2) 当系统没装 ffmpeg 时，这类合并会直接中止。
        #    为了让下载任务不至于失败，这里在无 ffmpeg 情况下改成“只下载视频 + 只下载音频（不合并）”。
        #    后续你装好 ffmpeg 后，再次下载即可自动合并（若平台提供可合并的流）。

        cookies_file = None
        if item.extra and isinstance(item.extra, dict):
            cookies_file = item.extra.get("cookies_file")

        quality_norm = "highest"
        if item.extra and isinstance(item.extra, dict):
            q = item.extra.get("quality")
            if isinstance(q, str) and q.strip():
                quality_norm = q.strip().lower()

        allowed_qualities = {"highest", "1080p", "720p", "480p", "360p", "low"}
        if quality_norm not in allowed_qualities:
            raise ValueError(f"不支持的清晰度: {quality_norm}")

        height_map = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "low": 360}
        max_height = height_map.get(quality_norm)

        if check_ffmpeg():
            # 有 ffmpeg：允许分离音视频并合并
            ydl_opts = {
                "outtmpl": str(base_path) + ".%(ext)s",  # yt-dlp 会自动替换 %(ext)s
            }
            if quality_norm != "highest":
                # 限制最高分辨率；如果过滤后找不到合适流，就回退到 best
                format_selector = (
                    f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={max_height}]+bestaudio/"
                    f"best[height<={max_height}]/best"
                )
                ydl_opts["format"] = format_selector
            # yt-dlp 合并时默认从 PATH 查找 ffmpeg，这里显式指定本地 ffmpeg 目录。
            ffmpeg_path = get_ffmpeg_path()
            if ffmpeg_path:
                from pathlib import Path as _Path

                ydl_opts["ffmpeg_location"] = str(_Path(ffmpeg_path).parent)
            ydl_opts_video = None
            ydl_opts_audio = None
        else:
            # 无 ffmpeg：两次下载，避免 yt-dlp 内部 merge 直接中止
            if quality_norm == "highest":
                video_format = "bestvideo"
            else:
                video_format = f"bestvideo[height<={max_height}]/bestvideo"
            ydl_opts_video = {
                "outtmpl": str(base_path) + ".%(ext)s",
                "format": video_format,
            }
            ydl_opts_audio = {
                "outtmpl": str(base_path) + ".audio.%(ext)s",
                "format": "bestaudio",
            }
            ydl_opts = None

        # 如果有 cookies 文件，通过 yt-dlp 的 cookiefile 选项传递
        if cookies_file:
            # 等价于命令行 --cookies cookies.txt
            if ydl_opts:
                ydl_opts["cookiefile"] = cookies_file
            if ydl_opts_video:
                ydl_opts_video["cookiefile"] = cookies_file
            if ydl_opts_audio:
                ydl_opts_audio["cookiefile"] = cookies_file

        # 如果有进度回调（GUI 使用），通过 yt-dlp 的 progress_hooks 回传 0-100
        progress_callback = None
        if item.extra and isinstance(item.extra, dict):
            progress_callback = item.extra.get("progress_callback")

        def _make_progress_hook(cb):
            def _hook(d: dict) -> None:
                try:
                    status = str(d.get("status") or "")
                    downloaded = d.get("downloaded_bytes") or d.get("downloaded_bytes_estimate")
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total:
                        percent = float(downloaded) * 100.0 / float(total)
                        # 限制在 0-100
                        percent = max(0.0, min(100.0, percent))
                        cb(percent, status)
                    else:
                        # 没有 total 时，保持不更新或用状态提示
                        cb(0.0, status)
                except Exception:
                    # 进度回调失败不应影响下载主体
                    return

            return _hook

        if callable(progress_callback):
            # 给两种选项都加 hook（无 ffmpeg 时会走多次 download）
            if ydl_opts:
                ydl_opts["progress_hooks"] = [_make_progress_hook(progress_callback)]
            if ydl_opts_video:
                ydl_opts_video["progress_hooks"] = [_make_progress_hook(progress_callback)]
            if ydl_opts_audio:
                ydl_opts_audio["progress_hooks"] = [_make_progress_hook(progress_callback)]
        
        try:
            # yt-dlp 是同步的，需要在线程池中运行
            loop = asyncio.get_event_loop()
            if ydl_opts:
                await loop.run_in_executor(
                    None,
                    self._download_sync,
                    source_url,
                    ydl_opts,
                )
            else:
                # 无 ffmpeg：先下视频（会产出 base_path.mp4），再下音频（base_path.audio.m4a）
                if ydl_opts_video:
                    await loop.run_in_executor(
                        None,
                        self._download_sync,
                        source_url,
                        ydl_opts_video,
                    )
                if ydl_opts_audio:
                    await loop.run_in_executor(
                        None,
                        self._download_sync,
                        source_url,
                        ydl_opts_audio,
                    )

            # yt-dlp 可能改变了文件扩展名，查找实际文件
            # 首先检查期望的路径
            if output_path.exists():
                logger.info(f"Downloaded via yt-dlp to {output_path}")
                return output_path

            # 尝试查找同名但不同扩展名的文件（常见视频格式）
            parent = output_path.parent
            base_name = base_path.name
            video_extensions = [".mp4", ".webm", ".mkv", ".flv", ".m4a", ".mp3"]

            for ext in video_extensions:
                candidate = parent / f"{base_name}{ext}"
                if candidate.exists():
                    logger.info(f"Downloaded via yt-dlp to {candidate} (expected {output_path})")
                    return candidate

            # 如果还是找不到，尝试 glob 匹配
            for f in parent.glob(f"{base_name}.*"):
                if f.is_file() and f.suffix not in [".part", ".ytdl"]:  # 排除临时文件
                    logger.info(f"Downloaded via yt-dlp to {f} (expected {output_path})")
                    return f

            raise DownloadError(
                "yt-dlp 下载完成但未找到输出文件。",
                stage=ErrorStage.DOWNLOAD,
                context=ErrorContext(extra={"expected": str(output_path)}),
            )
        except Exception as e:
            raise DownloadError(
                "使用 yt-dlp 下载时发生错误。",
                stage=ErrorStage.DOWNLOAD,
                context=ErrorContext(extra={"reason": str(e)}),
            ) from e
    
    def _download_sync(self, url: str, opts: dict):
        """同步下载（在线程池中运行）"""
        with YoutubeDL(opts) as ydl:
            ydl.download([url])


class DownloaderFactory:
    """下载器工厂"""
    
    @staticmethod
    def create(backend: Backend, item: MediaItem) -> BaseDownloader:
        """根据后端和媒体项创建下载器"""
        if backend == Backend.AUTO:
            # 自动选择
            if item.backend == Backend.YTDLP:
                return YtDlpDownloader()
            elif item.ext == "m3u8" or item.manifest_url:
                return FFmpegDownloader()
            else:
                return HTTPXDownloader()
        elif backend == Backend.HTTPX:
            return HTTPXDownloader()
        elif backend == Backend.FFMPEG:
            return FFmpegDownloader()
        elif backend == Backend.YTDLP:
            return YtDlpDownloader()
        else:
            raise DownloaderError(f"Unknown backend: {backend}")
