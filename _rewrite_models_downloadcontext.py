from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
text=p.read_text(encoding="utf-8", errors="replace")

# Ensure Callable is imported
old="from typing import Optional, List, Dict, Any"
new="from typing import Optional, List, Dict, Any, Callable"
if old in text and new not in text:
    text=text.replace(old,new)

start=text.find("class DownloadContext(BaseModel):")
if start==-1:
    raise SystemExit("DownloadContext not found")

# Replace till EOF
prefix=text[:start]

new_class='''class DownloadContext(BaseModel):
    """涓嬭浇涓婁笅鏂?""

    output_dir: str = Field(..., description="杈撳嚭鐩綍")
    template: str = Field("{title}", description="鏂囦欢鍚嶆ā鏉?)
    meta_mode: str = Field("json", description="鍏冩暟鎹ā寮忥細json|filename|both")
    cookies: Optional[str] = Field(None, description="Cookies 鏂囦欢璺緞")
    backend: Backend = Field(Backend.AUTO, description="涓嬭浇鍚庣")
    dry_run: bool = Field(False, description="浠呴瑙堬紝涓嶄笅杞?)
    verbose: bool = Field(False, description="璇︾粏鏃ュ織")
    prefer_no_watermark: bool = Field(True, description="浼樺厛鏃犳按鍗?)

    # 鍦ㄤ笅杞界嚎绋嬮噷鍥炰紶杩涘害锛屼氦鐢?UI 绾跨▼灞曠ず銆?    progress_callback: Optional[Callable[[float, str], None]] = Field(
        None, description="杩涘害鍥炶皟(0-100, status)", exclude=True
    )

    # 娓呮櫚搴﹂€夋嫨锛歨ighest(榛樿鏈€楂?, 1080p/720p/480p/360p/low(鏈€浣庡彲鐢?
    quality: str = Field("highest", description="娓呮櫚搴﹂€夋嫨")
'''

text=prefix+new_class
p.write_text(text, encoding="utf-8")
print("rewrote DownloadContext")
