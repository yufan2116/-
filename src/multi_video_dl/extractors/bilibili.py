"""Bilibili Extractor"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

from yt_dlp import YoutubeDL

from ..core.errors import ParseError, YtDlpNotFoundError
from ..core.models import MediaInfo, MediaItem, MediaType, Backend
from ..core.utils import check_ytdlp, normalize_cookies_for_yt_dlp
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class BilibiliExtractor(BaseExtractor):
    """Bilibili 视频提取器（使用 yt-dlp）"""
    
    def match(self, url: str) -> bool:
        """检查是否为 Bilibili URL"""
        patterns = [
            r"bilibili\.com/video/(BV\w+)",
            r"b23\.tv/\w+",
            r"bilibili\.com/bangumi/play/",
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)
    
    async def parse(self, url: str, ctx) -> MediaInfo:
        """解析 Bilibili 视频"""
        if not check_ytdlp():
            raise YtDlpNotFoundError("yt-dlp is required for Bilibili extraction")

        # yt-dlp 是同步的，需要在线程池中运行
        loop = asyncio.get_event_loop()
        cookies_file = getattr(ctx, "cookies", None)
        info_dict = await loop.run_in_executor(None, self._extract_info, url, cookies_file)
        
        # 转换为统一 schema
        return self._convert_to_media_info(info_dict, url)
    
    def _extract_info(self, url: str, cookies_file: Optional[str] = None) -> dict:
        """使用 yt-dlp 提取信息（同步）"""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,  # 只提取信息，不下载
        }

        cookies_file = normalize_cookies_for_yt_dlp(cookies_file)

        # 如果提供了 cookies 文件，则让 yt-dlp 直接使用（等价于命令行 --cookies）
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            raise ParseError(f"Failed to extract info from {url}: {e}") from e
    
    def _convert_to_media_info(self, info_dict: dict, source_url: str) -> MediaInfo:
        """将 yt-dlp 的 info_dict 转换为 MediaInfo"""
        # 提取基本信息
        video_id = info_dict.get("id") or info_dict.get("display_id", "")
        title = info_dict.get("title", "Untitled")
        uploader = info_dict.get("uploader") or info_dict.get("channel", "Unknown")
        
        # 提取发布时间
        publish_time = None
        if "upload_date" in info_dict:
            try:
                # yt-dlp 的 upload_date 格式通常是 YYYYMMDD
                date_str = str(info_dict["upload_date"])
                if len(date_str) == 8:
                    publish_time = datetime.strptime(date_str, "%Y%m%d")
            except Exception:
                pass
        
        # 提取标签
        tags = info_dict.get("tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        
        # 提取描述
        description = info_dict.get("description") or info_dict.get("info", "")
        
        # 提取时长
        duration = info_dict.get("duration")
        
        # 提取缩略图
        thumbnail = info_dict.get("thumbnail") or info_dict.get("thumbnails", [{}])[0].get("url", "")
        
        # 构建 MediaItem 列表
        items = []
        
        # 处理格式列表
        formats = info_dict.get("formats", [])
        if not formats:
            # 如果没有 formats，尝试从 info_dict 直接构建
            url = info_dict.get("url")
            if url:
                ext = info_dict.get("ext", "mp4")
                height = info_dict.get("height")
                width = info_dict.get("width")
                quality = f"{height}p" if height else None
                
                items.append(MediaItem(
                    direct_url=url,
                    ext=ext,
                    height=height,
                    width=width,
                    quality=quality,
                    filesize=info_dict.get("filesize"),
                    type=MediaType.VIDEO,
                    backend=Backend.YTDLP,
                    extra={"source_url": source_url},
                ))
        else:
            # 处理多个格式
            for fmt in formats:
                fmt_url = fmt.get("url")
                if not fmt_url:
                    continue
                
                ext = fmt.get("ext", "mp4")
                height = fmt.get("height")
                width = fmt.get("width")
                quality = fmt.get("format_note") or (f"{height}p" if height else None)
                filesize = fmt.get("filesize")
                
                # 判断是直接 URL 还是 manifest
                is_manifest = ext == "m3u8" or "m3u8" in fmt_url.lower()
                
                item = MediaItem(
                    direct_url=fmt_url if not is_manifest else None,
                    manifest_url=fmt_url if is_manifest else None,
                    ext=ext,
                    height=height,
                    width=width,
                    quality=quality,
                    filesize=filesize,
                    type=MediaType.VIDEO,
                    backend=Backend.YTDLP if not is_manifest else Backend.FFMPEG,
                    headers={},  # yt-dlp 通常不需要额外 headers
                    extra={"source_url": source_url, "format_id": fmt.get("format_id")},
                )
                items.append(item)
        
        # 如果没有 items，创建一个默认的（让 yt-dlp 处理）
        if not items:
            items.append(MediaItem(
                direct_url=None,
                ext="mp4",
                type=MediaType.VIDEO,
                backend=Backend.YTDLP,
                extra={"source_url": source_url, "use_ytdlp_direct": True},
            ))
        
        return MediaInfo(
            platform="bilibili",
            id=video_id,
            title=title,
            author=uploader,
            publish_time=publish_time,
            tags=tags,
            source_url=source_url,
            items=items,
            description=description,
            duration=duration,
            thumbnail=thumbnail,
            extra={"ytdlp_info": info_dict},  # 保存原始信息以备后用
        )
