"""命令行接口"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, cast

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

from .core.errors import (
    PlatformNotSupportedError,
    FFmpegNotFoundError,
    YtDlpNotFoundError,
    MultiVideoDLError,
)
from .core.models import Backend, DownloadContext
from .core.pipeline import Pipeline, batch_process
from .core.utils import check_ffmpeg, check_ytdlp, read_urls_file
from .extractors import EXTRACTORS, get_extractor_for_url
from .browser.login_capture import (
    capture_login_storage_state,
    HOME_URLS,
    ConfirmMode,
    BrowserType,
)
from .tools.bilibili_id_resolver import resolve_bilibili_input_to_url
from .tools.bilibili_playlist_utils import expand_bilibili_playlist_urls
from .tools.bilibili_playlist_tools import (
    is_bilibili_playlist_url,
    download_bilibili_playlist_direct,
)

app = typer.Typer(
    name="mvd",
    help="Multi Video Downloader - 统一的多平台视频下载器",
    add_completion=False,
)
console = Console()

# 安装 rich traceback，美观显示调用栈
install_rich_traceback(show_locals=False)


def setup_logging(verbose: bool = False):
    """设置日志（使用 rich 美化输出 + 结构化字段）"""
    # 避免重复添加 handler
    import logging

    level = logging.DEBUG if verbose else logging.INFO

    # 根 logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # 清理已有 handler，防止在多次调用时重复输出
    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=False,
    )
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


@app.command()
def dl(
    url: Optional[str] = typer.Argument(
        None, help="视频 URL（也支持 Bilibili 直接输入 BV/av/纯数字）"
    ),
    input_file: Optional[str] = typer.Option(
        None, "-i", "--input", help="从文件读取 URL 列表"
    ),
    out: str = typer.Option("./downloads", "--out", help="输出目录"),
    template: str = typer.Option(
        "{author} - {title} ({id})", "--template", help="文件名模板"
    ),
    meta: str = typer.Option(
        "json", "--meta", help="元数据模式：json|filename|both"
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="并发数"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不下载"),
    quality: str = typer.Option(
        "highest",
        "--quality",
        "-q",
        help="清晰度选择: highest(默认最高), 1080p, 720p, 480p, 360p, low(最低可用)",
    ),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="Cookies 文件路径"),
    backend: str = typer.Option("auto", "--backend", help="下载后端：auto|httpx|ffmpeg|ytdlp"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
    playlist_items: Optional[str] = typer.Option(
        None,
        "--playlist-items",
        "-I",
        help="分P序号：如 1 或 1,3-5 或 ALL（不填默认下载全部P）",
    ),
    only_current: bool = typer.Option(
        False,
        "--only-current",
        help="只下载当前P（等价于不下载整个 playlist）",
    ),
    playlist_start: Optional[int] = typer.Option(
        None,
        "--playlist-start",
        help="playlist-start：从第 N 个条目开始下载（yt-dlp）",
    ),
    playlist_end: Optional[int] = typer.Option(
        None,
        "--playlist-end",
        help="playlist-end：下载到第 M 个条目结束（yt-dlp）",
    ),
    match_filter: Optional[str] = typer.Option(
        None,
        "--match-filter",
        help="match-filter：如 'title*=关键词'（yt-dlp）",
    ),
    dateafter: Optional[str] = typer.Option(
        None,
        "--dateafter",
        help="dateafter：如 20250101（yt-dlp）",
    ),
    playlist_reverse: bool = typer.Option(
        False,
        "--playlist-reverse",
        help="playlist-reverse：倒序下载（yt-dlp）",
    ),
):
    """下载视频"""
    setup_logging(verbose)
    
    # 验证参数
    if not url and not input_file:
        rprint("[red]错误: 必须提供 URL 或输入文件[/red]")
        raise typer.Exit(1)
    
    if url and input_file:
        rprint("[red]错误: 不能同时提供 URL 和输入文件[/red]")
        raise typer.Exit(1)
    
    # 验证 meta 参数
    if meta not in ["json", "filename", "both"]:
        rprint(f"[red]错误: meta 必须是 json|filename|both，当前为 {meta}[/red]")
        raise typer.Exit(1)
    
    # 验证 backend 参数
    try:
        backend_enum = Backend(backend.lower())
    except ValueError:
        rprint(f"[red]错误: backend 必须是 auto|httpx|ffmpeg|ytdlp，当前为 {backend}[/red]")
        raise typer.Exit(1)

    quality_norm = (quality or "highest").strip().lower()
    allowed_qualities = {"highest", "1080p", "720p", "480p", "360p", "low"}
    if quality_norm not in allowed_qualities:
        rprint(
            f"[red]错误: quality 必须是 highest|1080p|720p|480p|360p|low，当前为 {quality}[/red]"
        )
        raise typer.Exit(1)
    
    # 检查依赖
    if backend_enum == Backend.FFMPEG and not check_ffmpeg():
        rprint("[red]错误: ffmpeg 未找到，请安装 ffmpeg 并添加到 PATH[/red]")
        raise typer.Exit(1)
    
    if backend_enum == Backend.YTDLP and not check_ytdlp():
        rprint("[red]错误: yt-dlp 未安装，请运行: pip install yt-dlp[/red]")
        raise typer.Exit(1)
    
    # 创建上下文
    ctx = DownloadContext(
        output_dir=out,
        template=template,
        meta_mode=meta,
        cookies=cookies,
        backend=backend_enum,
        dry_run=dry_run,
        verbose=verbose,
        prefer_no_watermark=True,
        quality=quality_norm,
    )
    
    # 执行下载
    if input_file:
        # 批量下载
        urls = read_urls_file(input_file)
        if not urls:
            rprint(f"[yellow]警告: 输入文件 {input_file} 中没有有效的 URL[/yellow]")
            raise typer.Exit(1)
        
        rprint(f"[green]找到 {len(urls)} 个 URL，开始批量下载...[/green]")
        asyncio.run(
            batch_download(
                urls,
                ctx,
                concurrency,
                playlist_items=playlist_items,
                only_current_p=only_current,
                playlist_start=playlist_start,
                playlist_end=playlist_end,
                match_filter=match_filter,
                dateafter=dateafter,
                playlist_reverse=playlist_reverse,
            )
        )
    else:
        # 单个下载
        asyncio.run(
            single_download(
                url,
                ctx,
                playlist_items=playlist_items,
                only_current_p=only_current,
                playlist_start=playlist_start,
                playlist_end=playlist_end,
                match_filter=match_filter,
                dateafter=dateafter,
                playlist_reverse=playlist_reverse,
            )
        )


async def single_download(
    url: str,
    ctx: DownloadContext,
    playlist_items: Optional[str] = None,
    only_current_p: bool = False,
    playlist_start: Optional[int] = None,
    playlist_end: Optional[int] = None,
    match_filter: Optional[str] = None,
    dateafter: Optional[str] = None,
    playlist_reverse: bool = False,
):
    """单个 URL 下载"""
    try:
        # 支持用户直接输入 BV/av/纯数字
        if not url.strip().lower().startswith(("http://", "https://")):
            resolved = await resolve_bilibili_input_to_url(url)
            if resolved:
                url = resolved.video_url
                rprint(
                    f"[cyan]解析输入为 Bilibili:[/cyan] {resolved.bvid} / {resolved.aid}"
                )
                rprint(f"[cyan]标题:[/cyan] {resolved.title}")
                if resolved.uploader:
                    rprint(f"[cyan]UP:[/cyan] {resolved.uploader}")
                if resolved.pages:
                    rprint(f"[cyan]分P数量:[/cyan] {len(resolved.pages)}")

        # playlist：对 bilibili 的集合/多P“同一个 BV 下的条目列表”，如果链接里没有 ?p=，
        # 直接让 yt-dlp 去识别 playlist（支持 -I/--playlist-items 透传）。
        if is_bilibili_playlist_url(url) and ("?p=" not in url):
            download_bilibili_playlist_direct(
                url=url,
                output_dir=ctx.output_dir,
                filename_template=ctx.template,
                cookies=ctx.cookies,
                playlist_items=playlist_items,
                noplaylist=only_current_p,
                playlist_start=playlist_start,
                playlist_end=playlist_end,
                match_filter=match_filter,
                dateafter=dateafter,
                playlist_reverse=playlist_reverse,
                dry_run=ctx.dry_run,
                progress_callback=None,
            )
            return

        # 否则：保持原有的 ?p= 展开逻辑（用于分P页面）
        urls_to_download = expand_bilibili_playlist_urls(url, playlist_items, only_current_p)
        if not urls_to_download:
            urls_to_download = [url]

        last_media_path: Optional[str] = None
        last_metadata_path: Optional[str] = None

        for page_url in urls_to_download:
            # 查找 extractor
            extractor = get_extractor_for_url(page_url)
            if not extractor:
                rprint(f"[red]错误: 不支持的平台 URL: {page_url}[/red]")
                rprint("[yellow]提示: 目前支持 Bilibili，抖音和小红书待实现[/yellow]")
                raise typer.Exit(1)

            rprint(f"[green]检测到平台: {extractor.get_platform_name()}[/green]")

            # 解析
            rprint("[cyan]正在解析视频信息...[/cyan]")
            media_info = await extractor.parse(page_url, ctx)

            rprint(f"[green]标题: {media_info.title}[/green]")
            rprint(f"[green]作者: {media_info.author}[/green]")
            rprint(f"[green]找到 {len(media_info.items)} 个媒体项[/green]")

            # 处理
            pipeline = Pipeline(ctx)
            media_path, metadata_path = await pipeline.process(media_info)
            last_media_path = str(media_path) if media_path else None
            last_metadata_path = str(metadata_path) if metadata_path else None

            if ctx.dry_run:
                rprint("\n[bold yellow]=== DRY-RUN 预览 ===[/bold yellow]")
                rprint(f"媒体文件: {media_path}")
                if metadata_path:
                    rprint(f"元数据文件: {metadata_path}")
            else:
                rprint(f"\n[bold green]完成下载: {media_path}[/bold green]")
                if metadata_path:
                    rprint(f"[green]元数据已保存: {metadata_path}[/green]")
    
    except PlatformNotSupportedError as e:
        rprint(f"[bold red]平台不支持:[/bold red] {e}")
        raise typer.Exit(1)
    except FFmpegNotFoundError as e:
        rprint(f"[bold red]依赖缺失（ffmpeg）:[/bold red] {e}")
        rprint("[yellow]提示: 请安装 ffmpeg 并添加到 PATH[/yellow]")
        raise typer.Exit(1)
    except YtDlpNotFoundError as e:
        rprint(f"[bold red]依赖缺失（yt-dlp）:[/bold red] {e}")
        rprint("[yellow]提示: 请运行: pip install yt-dlp[/yellow]")
        raise typer.Exit(1)
    except MultiVideoDLError as e:
        # 结构化业务错误
        rprint(f"[bold red]下载失败:[/bold red] {e}")
        if ctx.verbose:
            # rich 已经安装了 traceback hook，这里再输出一次当前异常的堆栈
            console.print_exception()
        raise typer.Exit(1)
    except Exception:
        # 非预期异常：打印完整 traceback + 简要提示
        rprint("[bold red]出现未预期的内部错误。[/bold red]")
        if ctx.verbose:
            console.print_exception()
        else:
            rprint("[yellow]提示: 可以添加 -v 参数查看完整错误堆栈。[/yellow]")
        raise typer.Exit(1)


async def batch_download(
    urls: list[str],
    ctx: DownloadContext,
    concurrency: int,
    playlist_items: Optional[str] = None,
    only_current_p: bool = False,
    playlist_start: Optional[int] = None,
    playlist_end: Optional[int] = None,
    match_filter: Optional[str] = None,
    dateafter: Optional[str] = None,
    playlist_reverse: bool = False,
):
    """批量下载"""
    try:
        # 允许 urls.txt 直接填 BV/av/纯数字；统一交给 single_download（便于 playlist 的直下逻辑生效）
        targets: list[str] = []
        for u in urls:
            u_str = (u or "").strip()
            if not u_str:
                continue
            if u_str.lower().startswith(("http://", "https://")):
                targets.append(u_str)
            else:
                resolved = await resolve_bilibili_input_to_url(u_str)
                targets.append(resolved.video_url if resolved else u_str)

        semaphore = asyncio.Semaphore(concurrency)
        failures: list[tuple[str, Exception]] = []

        async def worker(target_url: str):
            async with semaphore:
                try:
                    await single_download(
                        target_url,
                        ctx,
                        playlist_items=playlist_items,
                        only_current_p=only_current_p,
                        playlist_start=playlist_start,
                        playlist_end=playlist_end,
                        match_filter=match_filter,
                        dateafter=dateafter,
                        playlist_reverse=playlist_reverse,
                    )
                except Exception as e:  # noqa: BLE001
                    failures.append((target_url, e))

        await asyncio.gather(*(worker(t) for t in targets))

        success_count = len(targets) - len(failures)
        fail_count = len(failures)
        
        # 打印摘要
        rprint("\n[bold]=== 下载摘要 ===[/bold]")
        rprint(f"[green]成功: {success_count}[/green]")
        rprint(f"[red]失败: {fail_count}[/red]")
        
        if failures:
            rprint("\n[bold red]失败详情:[/bold red]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("URL", style="cyan", overflow="fold")
            table.add_column("错误", style="red", overflow="fold")
            
            for url, error in failures:
                error_msg = str(error)
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                table.add_row(url, error_msg)
            
            console.print(table)
    
    except MultiVideoDLError as e:
        rprint(f"[bold red]批量下载失败:[/bold red] {e}")
        if ctx.verbose:
            console.print_exception()
        raise typer.Exit(1)
    except Exception:
        rprint("[bold red]批量下载过程中出现未预期的内部错误。[/bold red]")
        if ctx.verbose:
            console.print_exception()
        else:
            rprint("[yellow]提示: 可以添加 -v 参数查看完整错误堆栈。[/yellow]")
        raise typer.Exit(1)


@app.command("capture-login")
def capture_login(
    platform: str = typer.Argument(..., help="平台：bilibili|douyin|xiaohongshu"),
    output: str = typer.Option(
        "./auth/storage_state.json", "--output", "-o", help="storageState 输出 JSON 路径"
    ),
    confirm_mode: str = typer.Option(
        "either", "--confirm-mode", help="确认方式：enter|button|either"
    ),
    browser: str = typer.Option(
        "auto",
        "--browser",
        help="浏览器类型：auto|chromium|firefox|webkit（默认按系统默认浏览器）",
    ),
    force: bool = typer.Option(
        False, "--force", help="强制重新登录并覆盖已存在的 storageState 文件"
    ),
):
    """启动可见浏览器，手动登录后捕获 Playwright storageState。"""
    platform_normalized = platform.strip().lower()
    if platform_normalized not in HOME_URLS:
        rprint(
            f"[red]错误: platform 必须是 bilibili|douyin|xiaohongshu，当前为 {platform}[/red]"
        )
        raise typer.Exit(1)

    if confirm_mode not in {"enter", "button", "either"}:
        rprint(
            f"[red]错误: confirm-mode 必须是 enter|button|either，当前为 {confirm_mode}[/red]"
        )
        raise typer.Exit(1)

    if browser not in {"auto", "chromium", "firefox", "webkit"}:
        rprint(
            f"[red]错误: browser 必须是 auto|chromium|firefox|webkit，当前为 {browser}[/red]"
        )
        raise typer.Exit(1)

    rprint(
        f"[cyan]即将打开 {platform_normalized} 首页，请在浏览器中完成登录，然后确认保存。[/cyan]"
    )
    output_path = Path(output)
    if output_path.exists() and not force:
        rprint(f"[green]已存在登录态文件，跳过登录: {output_path}[/green]")
        rprint(
            "[cyan]如登录失效，请加 --force 重新登录并覆盖该文件。[/cyan]"
        )
        rprint(
            f"[green]后续下载可直接使用: mvd dl <url> --cookies {output_path}[/green]"
        )
        return

    try:
        saved_path = asyncio.run(
            capture_login_storage_state(
                platform=platform_normalized,
                output_file=output,
                confirm_mode=cast(ConfirmMode, confirm_mode),
                browser_type=cast(BrowserType, browser),
            )
        )
        rprint(f"[bold green]登录态已保存: {saved_path}[/bold green]")
        rprint(
            f"[green]后续下载可直接使用: mvd dl <url> --cookies {saved_path}[/green]"
        )
    except Exception as e:
        rprint(f"[bold red]捕获登录态失败:[/bold red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
