# Xx1DramaTranslator

音频字幕工具 **V1.1**：识别广播剧/对白、大模型切句并翻译，支持歌词式校对、时间轴微调、SRT/ASS 导出。

原文 / 译文可在设置里任选，例如日语、英语、韩语、简体中文、繁体中文等相互转换，不限于某一种语言。

## 功能

- 拖入或添加 mp3 / wav，一音频一工程（同目录 `.xx1proj`）
- ASR 识别（默认阿里云 Paraformer）+ 大模型按所选语言语义断句、翻译、统校
- 设置中选择「原文语言」和「译文语言」，可互译
- 字幕编辑：改原文/译文、起止时间、增删句、单句重译
- 播放时只读高亮当前句；暂停时可编辑
- ↑↓ / 滚轮切句，进度条与当前句绑定；倍速 x1 → x1.25 → x1.5 → x2 → x3

## 环境

- Windows
- Python 3.11+（建议）
- 依赖见 `requirements.txt`

```bat
pip install -r requirements.txt
```

### 关于 ffmpeg（处理 MP3 需要）

- **WAV** 可直接识别，不依赖 ffmpeg。
- **MP3** 等非 WAV 格式需要本机有 ffmpeg。官方 Windows 包体积较大（essentials 约数十 MB，full 可上百 MB），**未内置**进本程序。
- 任选其一即可：
  1. `winget install --id=Gyan.FFmpeg -e`（安装后新开终端确认 `ffmpeg -version`）
  2. 从 [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) 下载 essentials，将 `ffmpeg.exe` 放到程序目录旁，或 `vendor\ffmpeg\`
  3. 设置环境变量 `XX1_FFMPEG` 指向 `ffmpeg.exe` 完整路径  
- 若缺少 ffmpeg，翻译 MP3 时会给出明确中文提示（不再只显示含糊的「找不到文件」）。

## 配置（请勿把密钥提交到 Git）

1. 复制示例配置：

```bat
copy config.example.json config.json
```

2. 用记事本或程序内「设置」填写：

- **ASR**：接口地址、API Key、模型（如 `paraformer-v2`）
- **大模型**：OpenAI 兼容接口的 `api_url`、`api_key`、`model`
- **原文语言 / 译文语言**：按片子实际语言选择

`config.json` 已在 `.gitignore` 中，本地密钥不会进仓库。

## 运行

```bat
run.bat
```

或：

```bat
python main.py
```

## 打包（单文件 exe）

需要已安装 Python，并装好依赖。双击或在项目目录执行：

```bat
pack.bat
```

完成后得到 `dist\Xx1DramaTranslator.exe`（无控制台窗口，图标为 `assets/app.ico`）。exe 会在**同目录**读写 `config.json`，请自行填写 API，不要把带密钥的配置和 exe 一起随意外发。若需支持 MP3，可把 `ffmpeg.exe` 放在 exe 同目录。

## 使用

1. 拖入音频或点播放列表添加
2. 在设置中选好原文/译文语言并配置 API
3. 点「开始翻译」
4. 完成后校对、改时间、单句重译
5. 「导出」为 SRT 或 ASS

## 隐私

不要把下列文件推送到远程：

- `config.json`（API Key）
- `*.xx1proj`（可能含完整字幕与路径）
- 音频原文件、`tests/_live_full/` 等调试回包

## 许可

本项目采用 **GNU GPL v3**（[LICENSE](LICENSE)）。

- 可以自由使用、修改、分发（包括商用）
- 若你的项目引用、修改或基于本软件发布，**整体也必须以开源方式提供源码**，并继续采用兼容 GPL 的许可
- 请同时遵守各语音识别与大模型服务商的条款

