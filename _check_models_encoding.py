from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
raw=p.read_bytes()
print('len',len(raw),'head',raw[:12])
encs=['utf-8','utf-8-sig','utf-16-le','utf-16-be','gbk','gb2312']
for enc in encs:
    try:
        txt=raw.decode(enc, errors='replace')
    except Exception as e:
        print(enc,'decode err',e)
        continue
    print(enc,'progress_callback',('progress_callback' in txt), 'quality:',('quality:' in txt), 'class DownloadContext',('class DownloadContext' in txt))
