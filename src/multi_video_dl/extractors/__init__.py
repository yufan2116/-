"""Extractors 模块"""

from .base import BaseExtractor
from .bilibili import BilibiliExtractor

EXTRACTORS = {
    "bilibili": BilibiliExtractor(),
}


def get_extractor_for_url(url: str) -> BaseExtractor | None:
    """根据 URL 获取匹配的 extractor"""
    for extractor in EXTRACTORS.values():
        if extractor.match(url):
            return extractor
    return None
