"""Pipeline 集成测试（使用 fake MediaItem / fake Downloader）"""

import asyncio
import json
from pathlib import Path

import pytest

from multi_video_dl.core.models import (
    Backend,
    DownloadContext,
    MediaInfo,
    MediaItem,
    MediaType,
)
from multi_video_dl.core.pipeline import Pipeline
from multi_video_dl.core.downloaders import BaseDownloader, DownloaderFactory


class FakeDownloader(BaseDownloader):
    """假下载器：直接写入一个小文件到目标路径"""

    async def download(self, item: MediaItem, output_path: Path, headers=None) -> Path:  # type: ignore[override]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake binary content")
        return output_path


@pytest.mark.asyncio
async def test_pipeline_process_with_fake_downloader(tmp_path, monkeypatch):
    """使用 fake MediaItem + fake Downloader 验证 Pipeline.process 能正确生成文件和 metadata.json。"""

    # 构造下载上下文
    ctx = DownloadContext(
        output_dir=str(tmp_path),
        template="{author} - {title} ({id})",
        meta_mode="json",
        cookies=None,
        backend=Backend.HTTPX,  # 强制 HTTPX 路径，方便 monkeypatch
        dry_run=False,
        verbose=False,
        prefer_no_watermark=True,
    )

    # 构造 fake MediaInfo / MediaItem（不依赖真实网络）
    item = MediaItem(
        direct_url="https://example.com/video.mp4",
        manifest_url=None,
        ext="mp4",
        headers={},
        quality="720p",
        height=720,
        width=1280,
        filesize=123456,
        type=MediaType.VIDEO,
        backend=Backend.HTTPX,
        extra={"no_watermark": True},
    )

    media_info = MediaInfo(
        platform="test-platform",
        id="video123",
        title="测试视频",
        author="测试作者",
        publish_time=None,
        tags=["tag1", "tag2"],
        source_url="https://example.com/video123",
        items=[item],
        description="这是一个用于测试的假视频条目",
        duration=60.0,
        thumbnail="https://example.com/thumb.jpg",
        extra={},
    )

    # monkeypatch DownloaderFactory，避免真实网络 / ffmpeg / yt-dlp 调用
    def fake_create(backend: Backend, _item: MediaItem) -> BaseDownloader:  # type: ignore[override]
        assert backend == Backend.HTTPX
        return FakeDownloader()

    monkeypatch.setattr(DownloaderFactory, "create", staticmethod(fake_create))

    pipeline = Pipeline(ctx)
    media_path, metadata_path = await pipeline.process(media_info)

    # 断言：媒体文件已生成
    assert media_path is not None
    assert media_path.exists()
    assert media_path.read_bytes() == b"fake binary content"

    # 断言：metadata.json 已生成且关键字段正确
    assert metadata_path is not None
    assert metadata_path.exists()

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["platform"] == "test-platform"
    assert data["id"] == "video123"
    assert data["title"] == "测试视频"
    assert data["author"] == "测试作者"
    assert data["source_url"] == "https://example.com/video123"
    assert isinstance(data.get("items"), list)
    assert len(data["items"]) == 1
