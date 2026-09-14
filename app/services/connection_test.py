from __future__ import annotations

import queue
import threading
from typing import Callable, TypeVar

from app.config import AsrConfig, LlmConfig
from app.services.asr_client import AsrClient, AsrError
from app.services.llm_client import LlmClient, LlmError


TEST_WALL_SECONDS = 18

T = TypeVar("T")


def _run_with_deadline(fn: Callable[[], T], *, seconds: float) -> T:
    """
    在独立守护线程中执行 fn，seconds 内必须返回。
    超时后立刻抛错，不等待后台网络请求结束（避免 UI 卡死）。
    """
    result_q: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def wrap() -> None:
        try:
            result_q.put((True, fn()))
        except Exception as exc:  # noqa: BLE001 — 原样带回调用方
            result_q.put((False, exc))

    thread = threading.Thread(target=wrap, name="xx1-conn-test", daemon=True)
    thread.start()
    try:
        ok, payload = result_q.get(timeout=seconds)
    except queue.Empty as exc:
        raise TimeoutError(f"超过 {seconds:.0f} 秒未响应") from exc
    if ok:
        return payload  # type: ignore[return-value]
    assert isinstance(payload, BaseException)
    raise payload


def test_llm_connection(config: LlmConfig) -> str:
    if not (config.api_url.strip() and config.api_key.strip() and config.model.strip()):
        raise LlmError("请先填写大模型 API 地址、Key 与模型名称")

    test_cfg = LlmConfig(
        api_url=config.api_url.strip(),
        api_key=config.api_key.strip(),
        model=config.model.strip(),
        temperature=0,
        max_tokens=16,
        timeout_sec=10,
    )
    client = LlmClient(test_cfg)

    def _call() -> str:
        return client.chat("只回复 OK", "ping")

    try:
        reply = _run_with_deadline(_call, seconds=TEST_WALL_SECONDS)
    except TimeoutError as exc:
        raise LlmError(
            f"大模型测试超时（{TEST_WALL_SECONDS}s）。\n"
            f"请确认地址类似：https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            f"实际请求：{client._endpoint()}\n"
            f"若持续超时，请检查代理/防火墙是否拦截 dashscope.aliyuncs.com"
        ) from exc
    except LlmError:
        raise
    except Exception as exc:
        raise LlmError(str(exc)) from exc
    return f"连通成功。模型回复：{str(reply)[:80]}\n接口：{client._endpoint()}"


def test_asr_connection(config: AsrConfig) -> str:
    if not (config.api_url.strip() and config.api_key.strip() and config.model.strip()):
        raise AsrError("请先填写 ASR API 地址、Key 与模型名称")

    client = AsrClient(config, timeout=10)

    def _call() -> str:
        return client.probe_connectivity(timeout=10)

    try:
        return _run_with_deadline(_call, seconds=TEST_WALL_SECONDS)
    except TimeoutError as exc:
        raise AsrError(
            f"ASR 测试超时（{TEST_WALL_SECONDS}s）。\n"
            f"请确认地址为：https://dashscope.aliyuncs.com/api/v1\n"
            f"基址解析为：{client.base}\n"
            f"若持续超时，请检查代理/防火墙是否拦截 dashscope.aliyuncs.com"
        ) from exc
    except AsrError:
        raise
    except Exception as exc:
        raise AsrError(str(exc)) from exc
