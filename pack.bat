@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 检查 PyInstaller / Pillow...
python -m pip install -q "pyinstaller>=6.0" pillow
if errorlevel 1 (
  echo 安装依赖失败，请确认已安装 Python 并加入 PATH。
  pause
  exit /b 1
)

echo [2/3] 生成 Windows 兼容的 app.ico...
python tools\make_ico.py
if errorlevel 1 (
  echo 生成 ico 失败，请确认 assets\icon.png 存在。
  pause
  exit /b 1
)

echo [3/3] 打包单文件 exe（嵌入 assets\app.ico，不用 UPX）...
python -m PyInstaller --noconfirm --clean Xx1DramaTranslator.spec
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

echo.
echo 完成：dist\Xx1DramaTranslator.exe
echo 窗口/任务栏用的是程序内图标；资源管理器里的 exe 图标是打进文件的。
echo 若文件夹里仍显示蟒蛇：关掉该文件夹再打开，或把 exe 复制到别的目录（系统会缓存旧图标）。
echo 首次运行会在 exe 同目录生成 config.json，请在软件里填写 API。
pause
