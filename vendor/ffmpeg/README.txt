# 可选：把 ffmpeg.exe（建议同时放 ffprobe.exe）放在本目录

处理 MP3 需要 ffmpeg。官方 Windows 包体积较大（essentials 约数十 MB，
full 可上百 MB），因此不随仓库/程序内置。

获取方式：
- winget install --id=Gyan.FFmpeg -e
- 或 https://www.gyan.dev/ffmpeg/builds/ 下载 essentials，复制 bin\ffmpeg.exe 到此处

也可将 ffmpeg.exe 放在程序 exe 同目录，或设置环境变量 XX1_FFMPEG。
