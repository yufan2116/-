"""Extractor 基类"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from ..core.models import MediaInfo, DownloadContext

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Extractor 基类"""
    
    @abstractmethod
    def match(self, url: str) -> bool:
        """检查 URL 是否匹配此 extractor"""
        pass
    
    @abstractmethod
    async def parse(self, url: str, ctx: DownloadContext) -> MediaInfo:
        """
        解析 URL 并返回 MediaInfo
        
        Args:
            url: 要解析的 URL
            ctx: 下载上下文
        
        Returns:
            MediaInfo 对象
        """
        pass
    
    def get_platform_name(self) -> str:
        """返回平台名称"""
        return self.__class__.__name__.replace("Extractor", "").lower()
