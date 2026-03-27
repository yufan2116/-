"""Extractors 模块"""

from .base import BaseExtractor
from .bilibili import BilibiliExtractor
from .douyin import DouyinExtractor
from .xhs import XHSExtractor

# 注册所有 extractors
EXTRACTORS = {
    "bilibili": BilibiliExtractor(),
    "douyin": DouyinExtractor(),
    "xhs": XHSExtractor(),
}


def get_extractor_for_url(url: str) -> BaseExtractor | None:
    """根据 URL 获取匹配的 extractor"""
    for extractor in EXTRACTORS.values():
        if extractor.match(url):
            return extractor
    return None
