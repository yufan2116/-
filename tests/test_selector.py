"""测试选择器"""

import pytest

from multi_video_dl.core.models import MediaInfo, MediaItem, MediaType
from multi_video_dl.core.selector import Selector


def test_selector_select_best_quality():
    """测试选择最佳质量"""
    selector = Selector()
    
    items = [
        MediaItem(ext="mp4", height=360, quality="360p", type=MediaType.VIDEO),
        MediaItem(ext="mp4", height=720, quality="720p", type=MediaType.VIDEO),
        MediaItem(ext="mp4", height=1080, quality="1080p", type=MediaType.VIDEO),
    ]
    
    media_info = MediaInfo(
        platform="bilibili",
        id="test",
        title="test",
        author="test",
        source_url="https://example.com",
        items=items,
    )
    
    selected = selector.select(media_info)
    assert selected is not None
    assert selected.height == 1080


def test_selector_empty_items():
    """测试空 items"""
    selector = Selector()
    
    media_info = MediaInfo(
        platform="bilibili",
        id="test",
        title="test",
        author="test",
        source_url="https://example.com",
        items=[],
    )
    
    selected = selector.select(media_info)
    assert selected is None
