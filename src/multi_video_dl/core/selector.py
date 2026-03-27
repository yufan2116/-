"""媒体项选择器"""

import logging
from typing import Optional, List

from .models import MediaInfo, MediaItem, MediaType

logger = logging.getLogger(__name__)


class Selector:
    """媒体项选择器（选择最佳质量的项）"""

    def __init__(self, prefer_no_watermark: bool = True):
        self.prefer_no_watermark = prefer_no_watermark

    def select(self, media_info: MediaInfo) -> Optional[MediaItem]:
        """选择最佳媒体项"""
        if not media_info.items:
            logger.warning("No items available in media_info")
            return None

        # 优先选择视频
        video_items: List[MediaItem] = [
            item for item in media_info.items if item.type == MediaType.VIDEO
        ]
        if not video_items:
            # 如果没有视频，选择所有项
            video_items = list(media_info.items)

        # 过滤：如果有无水印标记，优先选择（目前 B 站可能没有，但保留逻辑）
        if self.prefer_no_watermark:
            no_watermark_items: List[MediaItem] = []
            for item in video_items:
                extra = getattr(item, "extra", None)
                if extra and extra.get("no_watermark", False):
                    no_watermark_items.append(item)
            if no_watermark_items:
                video_items = no_watermark_items

        # 按质量排序
        def sort_key(item: MediaItem) -> tuple:
            # 优先按 height（数值）
            height = item.height or 0
            # 其次按 quality 字符串（简单映射）
            quality_map = {
                "1080p": 1080,
                "720p": 720,
                "480p": 480,
                "360p": 360,
                "240p": 240,
            }
            quality_value = quality_map.get((item.quality or "").lower(), 0)
            # 如果 quality 字符串有数值，也尝试提取
            if quality_value == 0 and item.quality:
                import re

                match = re.search(r"(\d+)p?", item.quality, re.IGNORECASE)
                if match:
                    quality_value = int(match.group(1))

            # 使用 max(height, quality_value) 作为主要排序键
            primary_quality = max(height, quality_value)

            # 次要排序：文件大小（越大越好，可能表示质量更高）
            filesize = item.filesize or 0

            return (primary_quality, filesize)

        sorted_items = sorted(video_items, key=sort_key, reverse=True)

        if sorted_items:
            selected = sorted_items[0]
            logger.info(
                "Selected item: quality=%s, height=%s, ext=%s",
                selected.quality,
                selected.height,
                selected.ext,
            )
            return selected

        return None

