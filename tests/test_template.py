"""测试文件名模板"""

import pytest
from pathlib import Path
from datetime import datetime

from multi_video_dl.core.models import MediaInfo, MediaItem, MediaType, DownloadContext
from multi_video_dl.core.store import Store
from multi_video_dl.core.utils import sanitize_filename


def test_sanitize_filename():
    """测试文件名清理"""
    assert sanitize_filename("test/video.mp4") == "test_video.mp4"
    assert sanitize_filename("test<>video") == "test__video"
    assert sanitize_filename("  test  ") == "test"
    assert len(sanitize_filename("a" * 300)) <= 200


def test_template_generation(tmp_path):
    """测试模板生成"""
    ctx = DownloadContext(
        output_dir=str(tmp_path),
        template="{author} - {title} ({id})",
        meta_mode="json",
    )
    store = Store(ctx)
    
    media_info = MediaInfo(
        platform="bilibili",
        id="BV1234567890",
        title="测试视频",
        author="测试UP主",
        source_url="https://www.bilibili.com/video/BV1234567890",
        publish_time=datetime(2024, 1, 1),
    )
    
    item = MediaItem(ext="mp4", type=MediaType.VIDEO)
    path = store.generate_filename(media_info, "mp4", item)
    
    assert "测试UP主" in str(path)
    assert "测试视频" in str(path)
    assert "BV1234567890" in str(path)
    assert path.suffix == ".mp4"
