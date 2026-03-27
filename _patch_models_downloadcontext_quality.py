from pathlib import Path

def detect_encoding(raw: bytes) -> str:
    # 绠€鍗?BOM 鎺㈡祴锛歎TF-16LE/BE 鎴?UTF-8
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    # 鍏滃簳锛氬皾璇?utf-8
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        # 鍏滃簳鍐嶈瘯 utf-16-le
        return "utf-16-le"

p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
raw=p.read_bytes()
enc=detect_encoding(raw)
s=raw.decode(enc, errors="strict")

# 鍙湪 DownloadContext 閲屾彃鍏?quality锛岄伩鍏嶈浼ゅ叾浠栨ā鍨嬬殑 quality 瀛楁
cls_idx=None
for i,line in enumerate(s.splitlines()):
    if line.startswith("class DownloadContext"):
        cls_idx=i
        break
if cls_idx is None:
    raise SystemExit("DownloadContext not found")

lines=s.splitlines(keepends=True)
# 鎵?DownloadContext 琛屽彿锛堟枃鏈绱㈠紩锛?cls_idx=None
for i,line in enumerate(lines):
    if line.startswith("class DownloadContext"):
        cls_idx=i
        break

# 鍦?DownloadContext 鍖洪棿鍐呮鏌ユ槸鍚﹀凡鏈?quality
# 鐢ㄧ缉杩涚害鏉燂細DownloadContext 鐨勫瓧娈电缉杩涢€氬父鏄?4 spaces
has_quality=False
for j in range(cls_idx, len(lines)):
    if lines[j].startswith("class ") and j!=cls_idx:
        break
    if lines[j].startswith("    quality:") and "Field" in lines[j]:
        has_quality=True
        break

if has_quality:
    print("DownloadContext quality already exists")
    raise SystemExit(0)

# 鎵?progress_callback 瀛楁缁撴潫浣嶇疆
start=None
for j in range(cls_idx, len(lines)):
    if "progress_callback" in lines[j]:
        start=j
        break
if start is None:
    raise SystemExit("progress_callback not found")
end=start
while end < len(lines) and lines[end].strip()!=")":
    end+=1
if end>=len(lines):
    raise SystemExit("could not find end of progress_callback field")

insert="\n    # 娓呮櫚搴﹂€夋嫨锛歨ighest(榛樿鏈€楂?, 1080p/720p/480p/360p/low(鏈€浣庡彲鐢?\n    quality: str = Field(\"highest\", description=\"娓呮櫚搴﹂€夋嫨\")\n"
# 鍙彃鍏ヤ竴娆?lines.insert(end+1, insert)

out="".join(lines)
p.write_bytes(out.encode(enc))
print("patched models.py DownloadContext")
