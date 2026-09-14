from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any
import json
import sys


def app_dir() -> Path:
    """Directory of the executable / project root (where config.json lives)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # development: repo root (parent of app/)
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    return app_dir() / "config.json"


PROJECT_EXTENSION = ".xx1proj"


@dataclass
class AsrConfig:
    api_url: str = "https://dashscope.aliyuncs.com/api/v1"
    api_key: str = ""
    model: str = "paraformer-v2"


@dataclass
class LlmConfig:
    api_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_sec: int = 120


@dataclass
class AppConfig:
    asr: AsrConfig = field(default_factory=AsrConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    source_lang: str = "日语"
    target_lang: str = "简体中文"
    translate_batch_size: int = 20
    proofread_batch_size: int = 40
    asr_max_seconds: int = 14400
    asr_chunk_seconds: int = 1800
    additional_prompt: str = ""
    playlist_expanded: bool = False

    def is_api_configured(self) -> bool:
        return bool(
            self.asr.api_url.strip()
            and self.asr.api_key.strip()
            and self.asr.model.strip()
            and self.llm.api_url.strip()
            and self.llm.api_key.strip()
            and self.llm.model.strip()
            and self.source_lang.strip()
            and self.target_lang.strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asr": asdict(self.asr),
            "llm": asdict(self.llm),
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "translate_batch_size": self.translate_batch_size,
            "proofread_batch_size": self.proofread_batch_size,
            "asr_max_seconds": self.asr_max_seconds,
            "asr_chunk_seconds": self.asr_chunk_seconds,
            "additional_prompt": self.additional_prompt,
            "playlist_expanded": self.playlist_expanded,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AppConfig":
        asr_data = data.get("asr") or {}
        llm_data = data.get("llm") or {}
        return AppConfig(
            asr=AsrConfig(
                api_url=str(asr_data.get("api_url", "") or "https://dashscope.aliyuncs.com/api/v1"),
                api_key=str(asr_data.get("api_key", "")),
                model=str(asr_data.get("model", "") or "paraformer-v2"),
            ),
            llm=LlmConfig(
                api_url=str(llm_data.get("api_url", "")),
                api_key=str(llm_data.get("api_key", "")),
                model=str(llm_data.get("model", "")),
                temperature=float(llm_data.get("temperature", 0.3)),
                max_tokens=int(llm_data.get("max_tokens", 4096)),
                timeout_sec=int(llm_data.get("timeout_sec", 120)),
            ),
            source_lang=str(data.get("source_lang", "日语")),
            target_lang=str(data.get("target_lang", "简体中文")),
            translate_batch_size=int(data.get("translate_batch_size", 20)),
            proofread_batch_size=int(data.get("proofread_batch_size", 40)),
            asr_max_seconds=int(data.get("asr_max_seconds", 14400)),
            asr_chunk_seconds=int(data.get("asr_chunk_seconds", 1800)),
            additional_prompt=str(data.get("additional_prompt", "")),
            playlist_expanded=bool(data.get("playlist_expanded", False)),
        )


class ConfigStore:
    """App-wide settings stored next to the program."""

    def __init__(self, path: Path | None = None) -> None:
        self.config_path = path or default_config_path()

    def load_config(self) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return AppConfig.from_dict(data)
        except Exception:
            return AppConfig()

    def save_config(self, config: AppConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def is_project_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() == PROJECT_EXTENSION


def load_project(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("工程文件格式无效")
    return data


def save_project(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def project_path_for_audio(audio_path: str | Path) -> Path:
    """一个音频对应一个同名工程文件。"""
    return Path(audio_path).with_suffix(PROJECT_EXTENSION)


# backward-compatible alias used by older imports
def default_config_dir() -> Path:
    return app_dir()
