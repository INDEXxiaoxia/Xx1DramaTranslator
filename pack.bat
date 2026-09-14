@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 检查 PyInstaller...
python -m pip install -q "pyinstaller>=6.0"
if errorlevel 1 (
  echo 安装 PyInstaller 失败，请确认已安装 Python 并加入 PATH。
  pause
  exit /b 1
)

echo [2/2] 打包单文件 exe（无控制台窗口，使用 assets\app.ico）...
python -m PyInstaller --noconfirm --clean Xx1DramaTranslator.spec
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

echo.
echo 完成：dist\Xx1DramaTranslator.exe
echo 首次运行会在 exe 同目录生成 config.json，请在软件里填写 API，不要把该文件发到网上。
pause
