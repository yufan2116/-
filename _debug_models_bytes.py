from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
b=p.read_bytes()
print('progress_callback bytes found', b'progress_callback' in b)
print('quality bytes found', b'quality:' in b)
