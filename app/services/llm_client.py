from __future__ import annotations
import json
import re
from typing import Any, Callable
import requests
from app.config import LlmConfig
from app.models import Cue
CancelCheck = Callable[[], bool]

class LlmError(RuntimeError):
    pass

class LlmClient:
    def __init__(self, config: LlmConfig) -> None:
        self.config = config
    def _endpoint(self) -> str:
        url = self.config.api_url.strip()
        if url.endswith("/chat/completions"):
            return url
        return url.rstrip("/") + "/chat/completions"
    def chat(
        self,
        system: str,
        user: str,
        *,
        cancel_check: CancelCheck | None = None,
        disable_thinking: bool = True,
    ) -> str:
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        headers = {
            "Authorization": f"Bearer {self.config.api_key.strip()}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.config.model.strip(),
            "temperature": self.config.temperature,
            "max_tokens": max(256, int(self.config.max_tokens)),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # DeepSeek V4 等：思考 token 与正文共享 max_tokens，易导致 content 为空
        if disable_thinking:
            payload["thinking"] = {"type": "disabled"}
            payload["enable_thinking"] = False
        data = self._post_chat(payload, headers, cancel_check=cancel_check)
        content = self._extract_content(data)
        if content.strip():
            return content.strip()
        if disable_thinking and ("thinking" in payload or "enable_thinking" in payload):
            payload.pop("thinking", None)
            payload.pop("enable_thinking", None)
            data = self._post_chat(payload, headers, cancel_check=cancel_check)
            content = self._extract_content(data)
            if content.strip():
                return content.strip()
        finish = ""
        try:
            finish = str((data.get("choices") or [{}])[0].get("finish_reason") or "")
        except Exception:
            pass
        raise LlmError(
            "大模型返回空译文"
            + (f"（finish_reason={finish}）" if finish else "")
            + "。若使用 DeepSeek V4 等思考模型，请关闭思考模式，或增大 max_tokens。"
        )
    def _post_chat(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        *,
        cancel_check: CancelCheck | None,
    ) -> dict[str, Any]:
        try:
            resp = requests.post(
                self._endpoint(),
                headers=headers,
                json=payload,
                timeout=(5, max(5, int(self.config.timeout_sec))),
            )
        except requests.RequestException as exc:
            raise LlmError(f"大模型网络错误: {exc}") from exc
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        if resp.status_code >= 400 and (
            "thinking" in payload or "enable_thinking" in payload
        ):
            body = (resp.text or "").lower()
            if resp.status_code == 400 or "thinking" in body or "enable_thinking" in body:
                payload = dict(payload)
                payload.pop("thinking", None)
                payload.pop("enable_thinking", None)
                try:
                    resp = requests.post(
                        self._endpoint(),
                        headers=headers,
                        json=payload,
                        timeout=(5, max(5, int(self.config.timeout_sec))),
                    )
                except requests.RequestException as exc:
                    raise LlmError(f"大模型网络错误: {exc}") from exc
        if resp.status_code >= 400:
            raise LlmError(f"大模型请求失败 ({resp.status_code}): {resp.text[:500]}")
        try:
            data = resp.json()
        except Exception as exc:
            raise LlmError(f"大模型响应不是 JSON: {resp.text[:300]}") from exc
        if not isinstance(data, dict):
            raise LlmError("大模型响应格式异常")
        return data
    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        try:
            msg = (data.get("choices") or [{}])[0].get("message") or {}
        except Exception as exc:
            raise LlmError(
                f"大模型响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}"
            ) from exc
        content = msg.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") in {"text", "output_text"} and item.get("text"):
                        parts.append(str(item["text"]))
                    elif item.get("text"):
                        parts.append(str(item["text"]))
            return "".join(parts)
        if content is None:
            return ""
        return str(content)
    def translate_batch(
        self,
        cues: list[Cue],
        *,
        source_lang: str,
        target_lang: str,
        prompt_snapshot: str,
        context_cues: list[Cue],
        cancel_check: CancelCheck | None = None,
    ) -> list[str]:
        n = len(cues)
        system = (
            f"你是专业的{source_lang}到{target_lang}字幕翻译器。"
            f"必须逐条翻译，共 {n} 条，顺序与编号不可改变。"
            "每条只对应翻译该条原文，不要把相邻条目合并成故事叙述。"
            f"只输出 {n} 行，每行格式严格为：编号|译文"
            "不要 JSON，不要解释，不要空行。"
        )
        context_lines = []
        for c in context_cues[-6:]:
            context_lines.append(
                f"[{c.start_ms}-{c.end_ms}] {c.source_text} => {c.target_text}"
            )
        numbered = "\n".join(f"{i+1}. {c.source_text}" for i, c in enumerate(cues))
        user = (
            f"附加提示词:\n{prompt_snapshot or '(无)'}\n\n"
            f"上文参考:\n{json.dumps(context_lines, ensure_ascii=False)}\n\n"
            f"请翻译以下 {n} 条原文:\n{numbered}"
        )
        raw = self.chat(system, user, cancel_check=cancel_check, disable_thinking=True)
        try:
            return self._parse_string_list(raw, expected=n)
        except LlmError:
            # 再试一次：更短指令 + 强调格式
            retry_system = (
                f"把下面 {n} 条{source_lang}译成{target_lang}。"
                f"只输出 {n} 行：编号|译文。禁止其它文字。"
            )
            raw2 = self.chat(
                retry_system, numbered, cancel_check=cancel_check, disable_thinking=True
            )
            return self._parse_string_list(raw2, expected=n)
    def translate_one(
        self,
        cue: Cue,
        *,
        source_lang: str,
        target_lang: str,
        prompt_snapshot: str,
        neighbor_cues: list[Cue],
        cancel_check: CancelCheck | None = None,
    ) -> str:
        system = (
            f"你是专业的{source_lang}到{target_lang}字幕翻译器。"
            "只翻译当前这一句，只输出译文纯文本，不要 JSON，不要解释。"
        )
        neighbors = [
            {"source": n.source_text, "target": n.target_text} for n in neighbor_cues
        ]
        user = (
            f"附加提示词:\n{prompt_snapshot}\n\n"
            f"上下文:\n{json.dumps(neighbors, ensure_ascii=False)}\n\n"
            f"当前句原文:\n{cue.source_text}"
        )
        return self.chat(system, user, cancel_check=cancel_check, disable_thinking=True)
    def segment_subtitle_text(
        self,
        text: str,
        *,
        source_lang: str = "日语",
        soft_max_chars: int = 42,
        cancel_check: CancelCheck | None = None,
    ) -> list[str]:
        """按完整句子/语气停顿断句。不得增删改写文字。"""
        text = re.sub(r"\s+", "", text or "")
        if not text:
            return []
        if len(text) <= 12:
            return [text]
        system = (
            f"你是{source_lang}广播剧/听书字幕断句编辑，最终切分与合并由你语义审定。"
            "按完整语句或自然语气停顿换行。"
            "原则："
            "1) 句子可长可短，以语义完整为准，不要为凑长度而切或并；"
            "2) 两句虽短但是不同的话，必须分行，禁止合并无关短句；"
            "3) 只有语义上同属一句、被错误切开的半截，才应放在同一行；"
            "4) 主谓宾能成句时放在同一行；连体修饰尽量跟被修饰语在一起；"
            "5) 优先在句末标点、逗号停顿、承接连词处断开；"
            f"6) 仅当一句明显过长（译成中文大约会超过 35 字，或原文超过约 {soft_max_chars} 字）时，才在语气停顿处再拆；"
            "7) 不得增删改任何文字，只能插入换行；所有行去掉空白后拼接必须与原文完全一致；"
            "8) 只输出断句结果，每行一句，不要编号，不要解释，不要举例。"
        )
        user = f"原文：\n{text}"
        raw = self.chat(system, user, cancel_check=cancel_check, disable_thinking=True)
        lines = self._parse_segment_lines(raw, original=text)
        if lines:
            return lines
        retry = self.chat(
            "按语义完整语句换行。禁止改字。"
            "短但独立的句子必须分行；只有半截才合并。"
            f"过长句（约>{soft_max_chars}字）才再拆。每行一句，无编号无举例。拼接必须等于原文。",
            text,
            cancel_check=cancel_check,
            disable_thinking=True,
        )
        lines = self._parse_segment_lines(retry, original=text)
        if lines:
            return lines
        raise LlmError("断句结果无法与原文对齐")

    @staticmethod
    def _parse_segment_lines(raw: str, *, original: str) -> list[str] | None:
        text = (raw or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:\w+)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        lines: list[str] = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                continue
            # 去掉可能的编号前缀
            s = re.sub(r"^\d+\s*[|｜.．、:：)\）]\s*", "", s).strip()
            s = re.sub(r"\s+", "", s)
            if s:
                lines.append(s)
        if not lines:
            return None
        joined = "".join(lines)
        expect = re.sub(r"\s+", "", original)
        if joined == expect:
            return lines
        return None

    def proofread_batch(
        self,
        cues: list[Cue],
        *,
        source_lang: str,
        target_lang: str,
        prompt_snapshot: str,
        cancel_check: CancelCheck | None = None,
    ) -> list[str] | None:
        n = len(cues)
        system = (
            f"你是{source_lang}/{target_lang}字幕统校编辑。"
            "统一专名译法，修正明显漏译或错译。不要增删条目，不要改顺序。"
            f"只输出 {n} 行，格式：编号|修订后译文。不要 JSON，不要解释。"
        )
        lines = []
        for i, c in enumerate(cues, start=1):
            lines.append(f"{i}. 原文: {c.source_text}\n   译文: {c.target_text}")
        user = (
            f"附加提示词:\n{prompt_snapshot or '(无)'}\n\n"
            f"待统校条目:\n" + "\n".join(lines)
        )
        try:
            raw = self.chat(system, user, cancel_check=cancel_check, disable_thinking=True)
            return self._parse_string_list(raw, expected=n)
        except LlmError:
            return None
    def _parse_string_list(self, raw: str, expected: int) -> list[str]:
        text = (raw or "").strip()
        if not text:
            raise LlmError("无法解析翻译结果: （空响应）")
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        lined = self._parse_numbered_lines(text, expected)
        if lined is not None:
            return lined
        data = self._loads_json_array(text)
        if data is None:
            raise LlmError(f"无法解析翻译结果: {raw[:300]}")
        if isinstance(data, dict):
            for key in ("translations", "items", "results", "data"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            raise LlmError("翻译结果不是数组")
        values: list[str] = []
        for item in data:
            if isinstance(item, str):
                values.append(item.strip())
            elif isinstance(item, dict):
                for key in ("target", "translation", "text", "content", "zh", "cn"):
                    if key in item and item[key] is not None:
                        values.append(str(item[key]).strip())
                        break
                else:
                    values.append(str(item).strip())
            else:
                values.append(str(item).strip())
        if len(values) != expected:
            raise LlmError(f"翻译条目数不一致: 期望 {expected}, 实际 {len(values)}")
        return values
    @staticmethod
    def _parse_numbered_lines(text: str, expected: int) -> list[str] | None:
        """解析 1|译文 / 1. 译文 / 1、译文。"""
        pattern = re.compile(
            r"^\s*(\d+)\s*(?:[|｜]|[.．、:：\)）]\s*)\s*(.+?)\s*$"
        )
        found: dict[int, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if not m:
                continue
            idx = int(m.group(1))
            found[idx] = m.group(2).strip().strip('"“”\'')
        if len(found) == expected and all(i in found for i in range(1, expected + 1)):
            return [found[i] for i in range(1, expected + 1)]
        # 无编号但行数刚好等于期望
        plain = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("```")]
        plain = [re.sub(r"^\d+\s*[|｜.．、:：)\）]\s*", "", ln) for ln in plain]
        if len(plain) == expected:
            return plain
        return None
    @staticmethod
    def _loads_json_array(text: str) -> Any | None:
        candidates = [text]
        match = re.search(r"\[.*\]", text, re.S)
        if match:
            candidates.append(match.group(0))
        # 截断修复：补全未闭合引号与括号
        repaired = text.strip()
        if repaired.startswith("["):
            if repaired.count('"') % 2 == 1:
                repaired += '"'
            repaired = re.sub(r",\s*$", "", repaired)
            if not repaired.endswith("]"):
                repaired += "]"
            candidates.append(repaired)
        obj_match = re.search(r"\{.*\}", text, re.S)
        if obj_match:
            candidates.append(obj_match.group(0))
        for cand in candidates:
            cleaned = cand.strip()
            cleaned = re.sub(r",\s*([\]\}])", r"\1", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
        return None
