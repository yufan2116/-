from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
text=p.read_text(encoding="utf-8")
# 1) ensure Callable import
old_import="from typing import Optional, List, Dict, Any"
new_import="from typing import Optional, List, Dict, Any, Callable"
if old_import in text and new_import not in text:
    text=text.replace(old_import,new_import)

# 2) ensure DownloadContext has progress_callback + quality
if "class DownloadContext" not in text:
    raise SystemExit("DownloadContext not found")
if "progress_callback" not in text:
    insert_after="prefer_no_watermark: bool = Field(True"
    idx=text.find(insert_after)
    if idx==-1:
        raise SystemExit("prefer_no_watermark line not found")
    # find end of that line
    line_end=text.find("\n", idx)
    if line_end==-1:
        line_end=len(text)
    addition="\n    # GUI/鍓嶇鐢細鍦ㄤ笅杞界嚎绋嬮噷鍥炰紶杩涘害锛屼氦鐢?UI 绾跨▼灞曠ず銆俓n    # 璇ュ瓧娈典笉鍙備笌搴忓垪鍖?钀界洏銆俓n    progress_callback: Optional[Callable[[float, str], None]] = Field(\n        None, description=\"杩涘害鍥炶皟(0-100, status)\", exclude=True\n    )\n\n    # 娓呮櫚搴﹂€夋嫨锛歨ighest(榛樿鏈€楂?, 1080p/720p/480p/360p/low(鏈€浣庡彲鐢?\n    quality: str = Field(\"highest\", description=\"娓呮櫚搴﹂€夋嫨\")\n"
    text=text[:line_end+1]+addition+text[line_end+1:]

p.write_text(text, encoding="utf-8")
print("patched disk models.py")
