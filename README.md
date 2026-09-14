# Xx1DramaTranslator

日剧 / 日语音频字幕工具 **V1.0**：识别日文对白，大模型切句并译成中文，支持歌词式校对、时间轴微调、SRT/ASS 导出。

## 功能

- 拖入或添加 mp3 / wav，一音频一工程（同目录 `.xx1proj`）
- ASR 识别（默认阿里云 Paraformer）+ 大模型语义断句、翻译、统校
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

音频切分若用 pydub 处理较长文件，本机需能调用 ffmpeg。

## 配置（请勿把密钥提交到 Git）

1. 复制示例配置：

```bat
copy config.example.json config.json
```

2. 用记事本或程序内「设置」填写：

- **ASR**：接口地址、API Key、模型（如 `paraformer-v2`）
- **大模型**：OpenAI 兼容接口的 `api_url`、`api_key`、`model`

`config.json` 已在 `.gitignore` 中，本地密钥不会进仓库。

## 运行

```bat
run.bat
```

或：

```bat
python main.py
```

## 使用

1. 拖入音频或点播放列表添加
2. 配置好 API 后点「开始翻译」
3. 完成后校对、改时间、单句重译
4. 「导出」为 SRT 或 ASS

## 隐私

不要把下列文件推送到远程：

- `config.json`（API Key）
- `*.xx1proj`（可能含完整字幕与路径）
- 音频原文件、`tests/_live_full/` 等调试回包

## 许可

个人 / 学习使用。请遵守各语音识别与大模型服务商的条款。
