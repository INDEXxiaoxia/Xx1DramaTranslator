from __future__ import annotations

from typing import Callable

from app.config import AppConfig
from app.models import Cue, TrackItem, TrackStatus
from app.services.asr_client import AsrClient
from app.services.audio_splitter import AudioSplitter
from app.services.llm_client import LlmClient, LlmError
from app.services.llm_segment import segment_cues_with_llm


ProgressCb = Callable[[str], None]
CancelCheck = Callable[[], bool]


LANG_HINT = {
    "日语": "ja",
    "日文": "ja",
    "日本語": "ja",
    "简体中文": "zh",
    "中文": "zh",
    "英语": "en",
    "英文": "en",
}


class TranslationPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(
        self,
        track: TrackItem,
        *,
        progress_cb: ProgressCb | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> list[Cue]:
        def progress(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        splitter = AudioSplitter(
            max_seconds=self.config.asr_max_seconds,
            chunk_seconds=self.config.asr_chunk_seconds,
        )
        asr = AsrClient(self.config.asr, timeout=max(600, self.config.llm.timeout_sec))
        llm = LlmClient(self.config.llm)
        lang = LANG_HINT.get(self.config.source_lang, "ja")

        try:
            # ASR 客户端内部会做 16k 转码 + 分块上传临时 OSS（对齐 audio_rugcut）
            track.status = TrackStatus.RECOGNIZING
            progress("正在准备识别…")
            if cancelled():
                raise InterruptedError("cancelled")

            all_cues = asr.recognize_file(
                track.path,
                offset_ms=0,
                language=lang,
                cancel_check=cancelled,
                progress_cb=progress,
            )

            if not all_cues:
                raise RuntimeError("ASR 未返回任何字幕条目")

            track.status = TrackStatus.SPLITTING
            progress("正在用大模型断句…")
            if cancelled():
                raise InterruptedError("cancelled")
            try:
                all_cues = segment_cues_with_llm(
                    llm,
                    all_cues,
                    source_lang=self.config.source_lang,
                    soft_max_chars=42,
                    cancel_check=cancelled,
                    progress_cb=progress,
                )
            except LlmError as exc:
                from app.services.cue_utils import split_long_cues

                progress(f"断句异常（{exc}），改用本地规则…")
                all_cues = split_long_cues(all_cues, max_chars=42)

            progress(f"断句完成：{len(all_cues)} 条，开始翻译…")

            # Ensure monotonic end times
            for i, cue in enumerate(all_cues):
                if cue.end_ms <= cue.start_ms:
                    if i + 1 < len(all_cues):
                        cue.end_ms = max(cue.start_ms + 500, all_cues[i + 1].start_ms)
                    else:
                        cue.end_ms = cue.start_ms + 2000

            track.cues = all_cues
            track.status = TrackStatus.TRANSLATING
            avg_len = sum(len(c.source_text) for c in all_cues) / max(1, len(all_cues))
            batch_size = max(1, self.config.translate_batch_size)
            if avg_len > 40:
                batch_size = min(batch_size, 8)
            else:
                batch_size = min(batch_size, 12)
            total_batches = (len(all_cues) + batch_size - 1) // batch_size
            context: list[Cue] = []
            for bi in range(total_batches):
                if cancelled():
                    raise InterruptedError("cancelled")
                progress(f"正在翻译 第 {bi + 1}/{total_batches} 批")
                batch = all_cues[bi * batch_size : (bi + 1) * batch_size]
                translations = llm.translate_batch(
                    batch,
                    source_lang=self.config.source_lang,
                    target_lang=self.config.target_lang,
                    prompt_snapshot=track.prompt_snapshot,
                    context_cues=context,
                    cancel_check=cancelled,
                )
                for cue, text in zip(batch, translations):
                    cue.target_text = text
                context = batch

            track.status = TrackStatus.PROOFREADING
            proof_size = max(1, self.config.proofread_batch_size)
            proof_batches = (len(all_cues) + proof_size - 1) // proof_size
            warning = ""
            for pi in range(proof_batches):
                if cancelled():
                    raise InterruptedError("cancelled")
                progress(f"正在统校 第 {pi + 1}/{proof_batches} 批")
                batch = all_cues[pi * proof_size : (pi + 1) * proof_size]
                revised = llm.proofread_batch(
                    batch,
                    source_lang=self.config.source_lang,
                    target_lang=self.config.target_lang,
                    prompt_snapshot=track.prompt_snapshot,
                    cancel_check=cancelled,
                )
                if revised is None:
                    warning = "统校结果条目数不一致，已保留统校前译文"
                    continue
                for cue, text in zip(batch, revised):
                    cue.target_text = text

            track.warning_message = warning
            track.status = TrackStatus.DONE
            track.progress_text = "翻译完成"
            track.error_message = ""
            return all_cues
        except InterruptedError:
            track.status = TrackStatus.CANCELLED
            track.progress_text = "已取消"
            track.cues = []
            raise
        except Exception as exc:
            track.status = TrackStatus.FAILED
            track.error_message = str(exc)
            track.progress_text = f"失败: {exc}"
            track.cues = []
            raise
        finally:
            splitter.cleanup()
            asr.cleanup()


def retranslate_cue(
    config: AppConfig,
    track: TrackItem,
    cue_id: str,
    *,
    cancel_check: CancelCheck | None = None,
) -> str:
    llm = LlmClient(config.llm)
    idx = next((i for i, c in enumerate(track.cues) if c.id == cue_id), -1)
    if idx < 0:
        raise LlmError("找不到该字幕条目")
    cue = track.cues[idx]
    neighbors: list[Cue] = []
    for j in range(max(0, idx - 2), min(len(track.cues), idx + 3)):
        if j == idx:
            continue
        neighbors.append(track.cues[j])
    text = llm.translate_one(
        cue,
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        prompt_snapshot=track.prompt_snapshot or config.additional_prompt,
        neighbor_cues=neighbors,
        cancel_check=cancel_check,
    )
    cue.target_text = text
    return text
