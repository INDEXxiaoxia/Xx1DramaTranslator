from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from app.config import AsrConfig
from app.models import Cue, new_cue_id
from app.services.audio_prepare import AudioPreparer


CancelCheck = Callable[[], bool]

DASHSCOPE_SAMPLE_AUDIO = (
    "https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav"
)


class AsrError(RuntimeError):
    def __init__(self, message: str, *, limit_exceeded: bool = False) -> None:
        super().__init__(message)
        self.limit_exceeded = limit_exceeded


def normalize_dashscope_base(api_url: str) -> str:
    u = api_url.strip().rstrip("/")
    suffixes = (
        "/services/audio/asr/transcription",
        "/services/aigc/multimodal-generation/generation",
        "/compatible-mode/v1/chat/completions",
        "/chat/completions",
    )
    for suffix in suffixes:
        if u.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            break
    if u.endswith(".aliyuncs.com"):
        u = u + "/api/v1"
    return u


def transcription_endpoint(base: str) -> str:
    return f"{base.rstrip('/')}/services/audio/asr/transcription"


def multimodal_endpoint(base: str) -> str:
    return f"{base.rstrip('/')}/services/aigc/multimodal-generation/generation"


def tasks_endpoint(base: str, task_id: str) -> str:
    return f"{base.rstrip('/')}/tasks/{task_id}"


def is_filetrans_model(model: str) -> bool:
    """paraformer / sensevoice / fun-asr 等：走临时 OSS + transcription。"""
    m = model.strip().lower()
    if not m:
        return True
    if "flash" in m and "filetrans" not in m:
        return False
    if "filetrans" in m:
        return True
    return any(k in m for k in ("paraformer", "sensevoice", "fun-asr", "funasr"))


def is_http_url(value: str) -> bool:
    try:
        p = urlparse(value)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def _multipart(fields: dict[str, str], file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----xx1asr" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode("utf-8")
    )
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _dashscope_http(
    method: str,
    url: str,
    api_key: str,
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """与 audio_rugcut 相同的 urllib JSON 调用。"""
    data = None
    hdrs = {"Authorization": "Bearer " + api_key}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise AsrError(f"ASR 请求失败 ({exc.code}): {body[:400]}") from exc
    return json.loads(body) if body else {}


class AsrClient:
    def __init__(self, config: AsrConfig, timeout: int = 1800) -> None:
        self.config = config
        self.timeout = timeout
        self.base = normalize_dashscope_base(config.api_url)
        self.model = config.model.strip() or "paraformer-v2"
        self._preparer: AudioPreparer | None = None

    def cleanup(self) -> None:
        if self._preparer is not None:
            self._preparer.cleanup()
            self._preparer = None

    def probe_connectivity(self, timeout: int = 15) -> str:
        if not (self.config.api_url.strip() and self.config.api_key.strip() and self.model):
            raise AsrError("请先填写 ASR API 地址、Key 与模型名称")

        if is_filetrans_model(self.model):
            policy = self._get_upload_policy(timeout=timeout)
            max_mb = policy.get("max_file_size_mb")
            task_id = self._submit_file_urls(
                [DASHSCOPE_SAMPLE_AUDIO], language="zh", timeout=timeout
            )
            return (
                f"连通成功（录音文件转写）。task_id={task_id}\n"
                f"模型：{self.model}\n临时 OSS 上限：{max_mb or '?'}MB"
            )

        # flash：用极短静音 base64 打 multimodal
        import struct
        import tempfile
        import wave

        with tempfile.TemporaryDirectory(prefix="xx1_flash_probe_") as tmp:
            wav = Path(tmp) / "p.wav"
            with wave.open(str(wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"".join(struct.pack("<h", 0) for _ in range(1600)))
            cues = self._recognize_multimodal_file(wav, language="zh", timeout=timeout)
        return (
            f"连通成功（Flash 同步识别）。返回 {len(cues)} 条\n"
            f"模型：{self.model}\n"
            f"提示：广播剧字幕建议改用 paraformer-v2（有句级时间戳）"
        )

    def recognize_file(
        self,
        path: str | Path,
        *,
        offset_ms: int = 0,
        language: str = "ja",
        cancel_check: CancelCheck | None = None,
        progress_cb: Callable[[str], None] | None = None,
    ) -> list[Cue]:
        path_str = str(path)
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")

        if is_http_url(path_str) or path_str.startswith("oss://"):
            if not is_filetrans_model(self.model):
                raise AsrError(
                    f"当前模型 {self.model} 不走 file_urls。请改用 paraformer-v2，或使用本地文件。"
                )
            cues = self._recognize_urls([path_str], language=language, cancel_check=cancel_check)
            return self._apply_offset(cues, offset_ms)

        local = Path(path)
        if not local.exists():
            raise AsrError(f"音频文件不存在: {local}")

        use_filetrans = is_filetrans_model(self.model)
        # flash 单块需满足 base64≤约10MB；filetrans 可更大
        max_mb = 7.0 if not use_filetrans else 18.0
        max_sec = 180 if not use_filetrans else 300
        self._preparer = AudioPreparer(max_chunk_seconds=max_sec, max_chunk_mb=max_mb)
        try:
            if progress_cb:
                mode = "OSS转写" if use_filetrans else "Flash同步"
                progress_cb(f"识别模式：{mode}（{self.model}）")
            chunks = self._preparer.prepare_chunks(local, progress_cb=progress_cb)
            all_cues: list[Cue] = []
            total = len(chunks)
            for i, chunk in enumerate(chunks, start=1):
                if cancel_check and cancel_check():
                    raise InterruptedError("cancelled")
                mb = chunk.path.stat().st_size / 1048576
                if use_filetrans:
                    if progress_cb:
                        progress_cb(f"上传第 {i}/{total} 块（{mb:.1f}MB）…")
                    oss_url = self.upload_local(chunk.path, cancel_check=cancel_check)
                    if progress_cb:
                        progress_cb(f"识别第 {i}/{total} 块…")
                    part = self._recognize_urls(
                        [oss_url], language=language, cancel_check=cancel_check
                    )
                else:
                    if progress_cb:
                        progress_cb(f"Flash 识别第 {i}/{total} 块（{mb:.1f}MB）…")
                    part = self._recognize_multimodal_file(
                        chunk.path, language=language, cancel_check=cancel_check
                    )
                    # flash 常无句级时间戳：按块内均分，保证能滚动
                    part = self._ensure_chunk_timestamps(part, chunk.duration_ms)

                for c in part:
                    c.start_ms += chunk.offset_ms + offset_ms
                    c.end_ms += chunk.offset_ms + offset_ms
                    if c.end_ms <= c.start_ms:
                        c.end_ms = c.start_ms + max(800, chunk.duration_ms // max(1, len(part)))
                all_cues.extend(part)
            all_cues.sort(key=lambda c: c.start_ms)
            return all_cues
        finally:
            self.cleanup()

    @staticmethod
    def _ensure_chunk_timestamps(cues: list[Cue], duration_ms: int) -> list[Cue]:
        if not cues:
            return cues
        if all(c.end_ms > c.start_ms for c in cues):
            return cues
        n = len(cues)
        slot = max(500, duration_ms // n)
        for i, c in enumerate(cues):
            c.start_ms = i * slot
            c.end_ms = min(duration_ms, (i + 1) * slot)
        return cues

    def _recognize_multimodal_file(
        self,
        path: Path,
        *,
        language: str,
        cancel_check: CancelCheck | None = None,
        timeout: int | None = None,
    ) -> list[Cue]:
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        mime = mimetypes.guess_type(str(path))[0] or "audio/wav"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        if len(b64) > 10 * 1024 * 1024:
            raise AsrError("Flash 分块 base64 超过 10MB，请改用 paraformer-v2", limit_exceeded=True)
        data_url = f"data:{mime};base64,{b64}"
        url = multimodal_endpoint(self.base)
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "system", "content": [{"text": ""}]},
                    {"role": "user", "content": [{"audio": data_url}]},
                ]
            },
            "parameters": {
                "asr_options": {
                    "language": language,
                    "enable_itn": False,
                }
            },
        }
        data = _dashscope_http(
            "POST",
            url,
            self.config.api_key.strip(),
            payload,
            timeout=timeout or min(300, self.timeout),
        )
        cues = self._parse_multimodal_cues(data)
        if not cues:
            raise AsrError(f"Flash 未返回文本：{json.dumps(data, ensure_ascii=False)[:300]}")
        return cues

    def _parse_multimodal_cues(self, data: dict[str, Any]) -> list[Cue]:
        output = data.get("output") or {}
        choices = output.get("choices") or []
        texts: list[str] = []
        if choices:
            content = (choices[0].get("message") or {}).get("content") or []
            if isinstance(content, str) and content.strip():
                texts.append(content.strip())
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text"):
                        texts.append(str(part["text"]).strip())
        plain = "\n".join(t for t in texts if t)
        if not plain:
            return []
        # 按换行/句号粗分，便于歌词滚动
        parts = [p.strip() for p in plain.replace("。", "。\n").split("\n") if p.strip()]
        if not parts:
            parts = [plain]
        return [
            Cue(id=new_cue_id(), start_ms=0, end_ms=0, source_text=p) for p in parts
        ]

    def upload_local(
        self,
        path: Path,
        *,
        cancel_check: CancelCheck | None = None,
        retries: int = 3,
    ) -> str:
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        policy = self._get_upload_policy()
        upload_host = policy.get("upload_host") or policy.get("host")
        upload_dir = (
            policy.get("upload_dir")
            or policy.get("key_prefix")
            or policy.get("object_prefix")
        )
        policy_str = policy.get("policy")
        signature = policy.get("signature")
        access_key_id = policy.get("oss_access_key_id") or policy.get("access_key_id")
        if not (upload_host and upload_dir and policy_str and signature and access_key_id):
            raise AsrError(f"上传凭证字段不全：{json.dumps(policy, ensure_ascii=False)[:300]}")

        max_mb = int(policy.get("max_file_size_mb") or 0)
        size = path.stat().st_size
        if max_mb and size > max_mb * 1024 * 1024:
            raise AsrError(
                f"分块仍过大：{size / 1048576:.1f}MB > 上限 {max_mb}MB",
                limit_exceeded=True,
            )

        ext = path.suffix.lstrip(".") or "wav"
        safe_name = f"{uuid.uuid4().hex}.{ext}"
        key = f"{upload_dir.rstrip('/')}/{safe_name}"
        fields = {
            "key": key,
            "OSSAccessKeyId": access_key_id,
            "policy": policy_str,
            "signature": signature,
            "success_action_status": "200",
        }
        if policy.get("x_oss_object_acl"):
            fields["x-oss-object-acl"] = str(policy["x_oss_object_acl"])
        if policy.get("x_oss_forbid_overwrite"):
            fields["x-oss-forbid-overwrite"] = str(policy["x_oss_forbid_overwrite"])

        data = path.read_bytes()
        body, ctype = _multipart(fields, "file", safe_name, data)
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            if cancel_check and cancel_check():
                raise InterruptedError("cancelled")
            try:
                req = urllib.request.Request(
                    upload_host,
                    data=body,
                    method="POST",
                    headers={"Content-Type": ctype, "Content-Length": str(len(body))},
                )
                with urllib.request.urlopen(req, timeout=max(180, self.timeout)) as resp:
                    resp.read()
                return f"oss://{key}"
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last_err = AsrError(f"OSS 上传失败 HTTP {exc.code}: {detail}")
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt < retries:
                    time.sleep(1.5 * attempt)
                    continue
        raise AsrError(f"OSS 上传失败（已重试 {retries} 次）: {last_err}")

    def _get_upload_policy(self, timeout: int | None = None) -> dict[str, Any]:
        q = f"action=getPolicy&model={self.model}"
        url = f"{self.base}/uploads?{q}"
        raw = _dashscope_http(
            "GET",
            url,
            self.config.api_key.strip(),
            timeout=timeout or 30,
        )
        data = raw.get("data") or raw.get("output") or raw
        if not isinstance(data, dict) or not data:
            raise AsrError(f"上传凭证响应异常：{json.dumps(raw, ensure_ascii=False)[:300]}")
        return data

    def _submit_file_urls(
        self,
        file_urls: list[str],
        *,
        language: str,
        timeout: int | None = None,
    ) -> str:
        url = transcription_endpoint(self.base)
        payload = {
            "model": self.model,
            "input": {"file_urls": file_urls},
            "parameters": {
                "channel_id": [0],
                "language_hints": [language],
                "timestamp_alignment_enabled": True,
                "disfluency_removal_enabled": False,
            },
        }
        headers = {"X-DashScope-Async": "enable"}
        if any(u.startswith("oss://") for u in file_urls):
            headers["X-DashScope-OssResourceResolve"] = "enable"
        data = _dashscope_http(
            "POST",
            url,
            self.config.api_key.strip(),
            payload,
            headers=headers,
            timeout=timeout or 60,
        )
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            raise AsrError(f"提交任务失败：{json.dumps(data, ensure_ascii=False)[:300]}")
        return str(task_id)

    def _recognize_urls(
        self,
        file_urls: list[str],
        *,
        language: str,
        cancel_check: CancelCheck | None,
    ) -> list[Cue]:
        task_id = self._submit_file_urls(file_urls, language=language)
        data = self._poll_task(task_id, cancel_check)
        return self._parse_transcription_output(data)

    def _poll_task(
        self,
        task_id: str,
        cancel_check: CancelCheck | None,
        poll_interval: float = 2.0,
        max_wait: float = 1800.0,
    ) -> dict[str, Any]:
        query_url = tasks_endpoint(self.base, task_id)
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if cancel_check and cancel_check():
                raise InterruptedError("cancelled")
            data = _dashscope_http(
                "GET",
                query_url,
                self.config.api_key.strip(),
                timeout=30,
            )
            out = data.get("output") or {}
            status = str(out.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                return out
            if status == "FAILED":
                raise AsrError(f"识别失败：{json.dumps(out, ensure_ascii=False)[:300]}")
            time.sleep(poll_interval)
        raise AsrError("ASR 任务等待超时")

    def _parse_transcription_output(self, out: dict[str, Any]) -> list[Cue]:
        results = out.get("results") or []
        if not results:
            turl = out.get("transcription_url") or (out.get("result") or {}).get("transcription_url")
            if turl:
                return self._download_and_parse_transcript(str(turl))
            raise AsrError(f"无识别结果：{json.dumps(out, ensure_ascii=False)[:300]}")

        cues: list[Cue] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            turl = item.get("transcription_url")
            if turl:
                cues.extend(self._download_and_parse_transcript(str(turl)))
        if not cues:
            raise AsrError("缺少 transcription_url")
        cues.sort(key=lambda c: c.start_ms)
        return cues

    def _download_and_parse_transcript(self, turl: str) -> list[Cue]:
        try:
            resp = requests.get(turl, timeout=60)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise AsrError(f"下载转写结果失败: {exc}") from exc

        cues: list[Cue] = []
        for tr in body.get("transcripts") or []:
            if not isinstance(tr, dict):
                continue
            for sent in tr.get("sentences") or []:
                if not isinstance(sent, dict):
                    continue
                text = str(sent.get("text") or "").strip()
                if not text:
                    continue
                start_ms = int(sent.get("begin_time") or 0)
                end_ms = int(sent.get("end_time") or start_ms)
                if end_ms < start_ms:
                    end_ms = start_ms
                cues.append(
                    Cue(
                        id=new_cue_id(),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        source_text=text,
                    )
                )
        if not cues:
            plain = str(body.get("text") or "").strip()
            if not plain:
                for tr in body.get("transcripts") or []:
                    if isinstance(tr, dict) and tr.get("text"):
                        plain = str(tr["text"]).strip()
                        break
            if plain:
                cues.append(Cue(id=new_cue_id(), start_ms=0, end_ms=0, source_text=plain))
        return cues

    @staticmethod
    def _apply_offset(cues: list[Cue], offset_ms: int) -> list[Cue]:
        if not offset_ms:
            return cues
        for c in cues:
            c.start_ms += offset_ms
            c.end_ms += offset_ms
        return cues
