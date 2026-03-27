"""处理管道"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

from .errors import DownloadError, ExtractorError, ErrorStage, ErrorContext
from .models import MediaInfo, DownloadContext, Backend
from .selector import Selector
from .store import Store
from .downloaders import DownloaderFactory
from .utils import (
    load_cookies_file,
    cookies_to_header,
    normalize_cookies_for_yt_dlp,
    get_bilibili_quality_warning,
)

logger = logging.getLogger(__name__)


class Pipeline:
    """统一的处理管道"""
    
    def __init__(self, ctx: DownloadContext):
        self.ctx = ctx
        self.selector = Selector(prefer_no_watermark=ctx.prefer_no_watermark)
        self.store = Store(ctx)
    
    async def process(self, media_info: MediaInfo) -> Tuple[Optional[Path], Optional[Path]]:
        """
        处理媒体信息，返回 (媒体文件路径, 元数据文件路径)
        """
        # 选择最佳媒体项
        item = self.selector.select(media_info)
        if not item:
            raise ExtractorError(
                "没有找到可用的媒体项，请检查该视频是否需要登录或是否为受限内容。",
                stage=ErrorStage.SELECT,
                context=ErrorContext(
                    url=media_info.source_url,
                    platform=media_info.platform,
                ),
            )
        
        # 确定使用的后端
        backend = self.ctx.backend
        if backend == Backend.AUTO and item.backend:
            backend = item.backend
        
        # 如果使用 yt-dlp 且 item 没有 URL，确保 extra 中有 source_url
        if backend == Backend.YTDLP and not item.has_url():
            if "source_url" not in item.extra:
                item.extra["source_url"] = media_info.source_url
        elif not item.has_url() and backend != Backend.YTDLP:
            raise ExtractorError(
                "选中的媒体项缺少可用的下载地址。",
                stage=ErrorStage.PREPARE,
                context=ErrorContext(
                    url=media_info.source_url,
                    platform=media_info.platform,
                    extra={"backend": backend.value},
                ),
            )
        
        # 确定输出路径
        output_path = self.store.get_output_path(media_info, item)
        
        # 如果是 dry-run，只返回路径信息
        if self.ctx.dry_run:
            logger.info(f"[DRY-RUN] Would download to: {output_path}")
            logger.info(f"[DRY-RUN] Selected item: quality={item.quality}, ext={item.ext}")
            metadata_path = None
            if self.ctx.meta_mode in ["json", "both"]:
                metadata_path = output_path.with_suffix(".metadata.json")
                logger.info(f"[DRY-RUN] Would save metadata to: {metadata_path}")
            return (output_path, metadata_path)
        
        # 实际下载
        try:
            # 创建下载器
            downloader = DownloaderFactory.create(backend, item)

            # 将进度回调透传给具体下载器（仅 yt-dlp 需要）
            if self.ctx.progress_callback and isinstance(item.extra, dict):
                item.extra.setdefault("progress_callback", self.ctx.progress_callback)
            # 透传清晰度给具体下载器（yt-dlp 使用 item.extra['quality']）
            if isinstance(item.extra, dict) and getattr(self.ctx, "quality", None):
                item.extra.setdefault("quality", self.ctx.quality)

            # Bilibili 高画质在无 cookies/storage_state 时给出告警（不阻止下载）
            platform_name = (media_info.platform or "").strip().lower()
            quality_value = (getattr(self.ctx, "quality", None) or "highest").strip().lower()
            has_cookies = bool((self.ctx.cookies or "").strip())
            if platform_name == "bilibili":
                warning_text = get_bilibili_quality_warning(
                    quality=quality_value,
                    has_cookies=has_cookies,
                )
                if warning_text:
                    logger.warning(warning_text)

            # 准备 headers（如果有 cookies 文件，可以在这里读取）
            headers: Dict[str, str] = dict(item.headers or {})
            if self.ctx.cookies:
                cookies_for_http_and_ytdlp = normalize_cookies_for_yt_dlp(self.ctx.cookies)
                if cookies_for_http_and_ytdlp:
                    # 从 cookies 文件读取并添加到所有 HTTP 请求的 Cookie 头
                    try:
                        cookies_dict = load_cookies_file(cookies_for_http_and_ytdlp)
                        if cookies_dict:
                            cookie_header = cookies_to_header(cookies_dict)
                            if "Cookie" in headers and headers["Cookie"]:
                                # 如果已有 Cookie，追加（避免丢失已有值）
                                headers["Cookie"] = (
                                    headers["Cookie"].rstrip("; ") + "; " + cookie_header
                                )
                            else:
                                headers["Cookie"] = cookie_header
                    except Exception as e:
                        logger.warning(
                            "Failed to load cookies file %s: %s",
                            cookies_for_http_and_ytdlp,
                            e,
                        )

                    # 同时把 cookies 文件路径传递给 yt-dlp 后端（通过 item.extra）
                    if hasattr(item, "extra") and isinstance(item.extra, dict):
                        # 不覆盖已有的 cookies_file，方便上层自定义
                        item.extra.setdefault("cookies_file", cookies_for_http_and_ytdlp)

            # 下载
            downloaded_path = await downloader.download(item, output_path, headers)

            # 保存元数据
            metadata_path = self.store.save_metadata(media_info, downloaded_path)

            logger.info(f"Successfully processed: {downloaded_path}")
            return (downloaded_path, metadata_path)

        except DownloadError:
            # 已经是结构化的下载错误，直接抛出
            raise
        except Exception as e:
            raise DownloadError(
                "下载媒体文件失败。",
                stage=ErrorStage.DOWNLOAD,
                context=ErrorContext(
                    url=media_info.source_url,
                    platform=media_info.platform,
                    backend=backend.value,
                    extra={"reason": str(e)},
                ),
            ) from e


async def batch_process(
    urls: List[str],
    extractors: Dict[str, Any],
    ctx: DownloadContext,
    concurrency: int = 3,
) -> Tuple[int, int, List[Tuple[str, Exception]]]:
    """
    批量处理 URL
    
    返回: (成功数, 失败数, [(url, error), ...])
    """
    results = []
    semaphore = asyncio.Semaphore(concurrency)
    
    async def process_one(url: str):
        async with semaphore:
            try:
                # 找到匹配的 extractor
                extractor = None
                for ext in extractors.values():
                    if ext.match(url):
                        extractor = ext
                        break
                
                if not extractor:
                    raise ExtractorError(f"No extractor found for URL: {url}")
                
                # 解析
                media_info = await extractor.parse(url, ctx)
                
                # 处理
                pipeline = Pipeline(ctx)
                await pipeline.process(media_info)
                
                return (url, None)
            except Exception as e:
                logger.error(f"Failed to process {url}: {e}", exc_info=ctx.verbose)
                return (url, e)
    
    # 并发执行
    tasks = [process_one(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    # 统计结果
    success_count = sum(1 for _, error in results if error is None)
    fail_count = len(results) - success_count
    failures = [(url, error) for url, error in results if error is not None]
    
    return (success_count, fail_count, failures)
