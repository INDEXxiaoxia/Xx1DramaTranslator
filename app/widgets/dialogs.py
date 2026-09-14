from __future__ import annotations

import threading

from PySide6.QtCore import QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, AsrConfig, LlmConfig, default_config_path
from app.services.connection_test import test_asr_connection, test_llm_connection
from app.theme import Colors


LANG_OPTIONS = ["日语", "简体中文", "英语", "繁体中文", "韩语"]

LLM_URL_HINT = (
    "示例（填到 /v1 即可，程序会自动补 /chat/completions）：\n"
    "https://dashscope.aliyuncs.com/compatible-mode/v1\n"
    "或 OpenAI 兼容网关：https://api.openai.com/v1\n"
    "也可直接填完整地址：…/v1/chat/completions"
)

ASR_URL_HINT = (
    "填写百炼 API 基址即可（推荐）：\n"
    "https://dashscope.aliyuncs.com/api/v1\n"
    "本地音频会先上传到百炼临时 OSS，再走\n"
    "/services/audio/asr/transcription（file_urls / oss://）\n"
    "推荐模型：paraformer-v2"
)


class _NoWheelSpinBox(QSpinBox):
    """忽略滚轮，防止在滚动设置页时误改数值。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class _NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class _NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(620, 640)
        self._config = config
        self._test_result: tuple[bool, str] | None = None
        self._test_kind: str | None = None
        self._test_lock = threading.Lock()
        self._test_poll = QTimer(self)
        self._test_poll.setInterval(200)
        self._test_poll.timeout.connect(self._poll_test_result)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)
        layout.setContentsMargins(4, 4, 8, 4)

        # ---- 基础设置 ----
        basic = QGroupBox("基础设置（必填）")
        basic_layout = QVBoxLayout(basic)

        asr_box = QGroupBox("阿里云 ASR（音频识别）")
        asr_form = QFormLayout(asr_box)
        self.asr_url = QLineEdit(config.asr.api_url or "https://dashscope.aliyuncs.com/api/v1")
        self.asr_url.setPlaceholderText("https://dashscope.aliyuncs.com/api/v1")
        self.asr_key = QLineEdit(config.asr.api_key)
        self.asr_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.asr_model = QLineEdit(config.asr.model or "paraformer-v2")
        self.asr_model.setPlaceholderText("广播剧推荐：paraformer-v2（有时间戳）")
        asr_form.addRow("API 地址", self.asr_url)
        asr_hint = QLabel(ASR_URL_HINT)
        asr_hint.setObjectName("HintLabel")
        asr_hint.setWordWrap(True)
        asr_form.addRow("", asr_hint)
        asr_form.addRow("Key", self.asr_key)
        asr_form.addRow("模型名称", self.asr_model)
        tip = QLabel(
            "说明：qwen3-asr-flash 走同步接口，句级时间戳较弱；"
            "paraformer-v2 走临时 OSS 转写，适合字幕。"
        )
        tip.setObjectName("HintLabel")
        tip.setWordWrap(True)
        asr_form.addRow("", tip)
        asr_test_row = QHBoxLayout()
        self.btn_test_asr = QPushButton("测试 ASR 连通")
        self.btn_test_asr.clicked.connect(lambda: self._run_test("asr"))
        self.asr_test_result = QLabel("")
        self.asr_test_result.setWordWrap(True)
        asr_test_row.addWidget(self.btn_test_asr)
        asr_test_row.addWidget(self.asr_test_result, 1)
        asr_form.addRow("", asr_test_row)
        basic_layout.addWidget(asr_box)

        llm_box = QGroupBox("大模型（OpenAI 格式）")
        llm_form = QFormLayout(llm_box)
        self.llm_url = QLineEdit(config.llm.api_url)
        self.llm_url.setPlaceholderText(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.llm_key = QLineEdit(config.llm.api_key)
        self.llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_model = QLineEdit(config.llm.model)
        self.llm_model.setPlaceholderText("例如：qwen-plus / gpt-4o-mini")
        llm_form.addRow("API 地址", self.llm_url)
        llm_hint = QLabel(LLM_URL_HINT)
        llm_hint.setObjectName("HintLabel")
        llm_hint.setWordWrap(True)
        llm_form.addRow("", llm_hint)
        llm_form.addRow("Key", self.llm_key)
        llm_form.addRow("模型名称", self.llm_model)
        llm_test_row = QHBoxLayout()
        self.btn_test_llm = QPushButton("测试大模型连通")
        self.btn_test_llm.clicked.connect(lambda: self._run_test("llm"))
        self.llm_test_result = QLabel("")
        self.llm_test_result.setWordWrap(True)
        llm_test_row.addWidget(self.btn_test_llm)
        llm_test_row.addWidget(self.llm_test_result, 1)
        llm_form.addRow("", llm_test_row)
        basic_layout.addWidget(llm_box)

        lang_box = QGroupBox("语言")
        lang_form = QFormLayout(lang_box)
        self.source_lang = _NoWheelComboBox()
        self.target_lang = _NoWheelComboBox()
        for lang in LANG_OPTIONS:
            self.source_lang.addItem(lang)
            self.target_lang.addItem(lang)
        self._set_combo(self.source_lang, config.source_lang)
        self._set_combo(self.target_lang, config.target_lang)
        lang_form.addRow("原文语言", self.source_lang)
        lang_form.addRow("译文语言", self.target_lang)
        basic_layout.addWidget(lang_box)

        layout.addWidget(basic)

        # ---- 高级设置 ----
        advanced = QGroupBox("高级设置")
        adv_form = QFormLayout(advanced)
        self.temperature = _NoWheelDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(config.llm.temperature)
        self.max_tokens = _NoWheelSpinBox()
        self.max_tokens.setRange(256, 128000)
        self.max_tokens.setValue(config.llm.max_tokens)
        self.timeout_sec = _NoWheelSpinBox()
        self.timeout_sec.setRange(10, 3600)
        self.timeout_sec.setValue(config.llm.timeout_sec)
        self.translate_batch = _NoWheelSpinBox()
        self.translate_batch.setRange(1, 200)
        self.translate_batch.setValue(config.translate_batch_size)
        self.proof_batch = _NoWheelSpinBox()
        self.proof_batch.setRange(1, 400)
        self.proof_batch.setValue(config.proofread_batch_size)
        self.asr_max = _NoWheelSpinBox()
        self.asr_max.setRange(60, 86400)
        self.asr_max.setValue(config.asr_max_seconds)
        self.asr_chunk = _NoWheelSpinBox()
        self.asr_chunk.setRange(60, 14400)
        self.asr_chunk.setValue(config.asr_chunk_seconds)
        adv_form.addRow("温度", self.temperature)
        adv_form.addRow("最大输出 token", self.max_tokens)
        adv_form.addRow("请求超时（秒）", self.timeout_sec)
        adv_form.addRow("翻译批次大小", self.translate_batch)
        adv_form.addRow("统校批次大小", self.proof_batch)
        adv_form.addRow("单次识别软上限（秒）", self.asr_max)
        adv_form.addRow("超限分片时长（秒）", self.asr_chunk)
        layout.addWidget(advanced)

        cfg_path_hint = QLabel(f"设置将保存到程序目录：\n{default_config_path()}")
        cfg_path_hint.setObjectName("HintLabel")
        cfg_path_hint.setWordWrap(True)
        layout.addWidget(cfg_path_hint)
        layout.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText("保存")
        save_btn.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _snapshot_for_test(self) -> tuple[AsrConfig, LlmConfig]:
        asr = AsrConfig(
            api_url=self.asr_url.text().strip(),
            api_key=self.asr_key.text().strip(),
            model=self.asr_model.text().strip(),
        )
        llm = LlmConfig(
            api_url=self.llm_url.text().strip(),
            api_key=self.llm_key.text().strip(),
            model=self.llm_model.text().strip(),
            temperature=float(self.temperature.value()),
            max_tokens=int(self.max_tokens.value()),
            timeout_sec=int(self.timeout_sec.value()),
        )
        return asr, llm

    def _set_testing_ui(self, testing: bool) -> None:
        self.btn_test_asr.setEnabled(not testing)
        self.btn_test_llm.setEnabled(not testing)

    def _run_test(self, kind: str) -> None:
        if self._test_poll.isActive():
            QMessageBox.information(self, "测试", "已有测试正在进行，请稍候（最多约 18 秒）")
            return
        asr, llm = self._snapshot_for_test()
        label = self.llm_test_result if kind == "llm" else self.asr_test_result
        label.setText("测试中（最长约 18 秒）…")
        label.setStyleSheet(f"color:{Colors.busy};")
        self._set_testing_ui(True)
        self._test_kind = kind
        with self._test_lock:
            self._test_result = None

        def job() -> None:
            try:
                if kind == "llm":
                    msg = test_llm_connection(llm)
                else:
                    msg = test_asr_connection(asr)
                payload = (True, msg)
            except Exception as exc:  # noqa: BLE001
                payload = (False, str(exc))
            with self._test_lock:
                self._test_result = payload

        threading.Thread(target=job, name=f"xx1-test-{kind}", daemon=True).start()
        self._test_poll.start()

    def _poll_test_result(self) -> None:
        with self._test_lock:
            payload = self._test_result
            if payload is None:
                return
            self._test_result = None
        self._test_poll.stop()
        kind = self._test_kind or "llm"
        label = self.llm_test_result if kind == "llm" else self.asr_test_result
        ok, msg = payload
        label.setText(msg)
        label.setStyleSheet(
            f"color:{Colors.ok};" if ok else f"color:{Colors.err};"
        )
        self._set_testing_ui(False)
        self._test_kind = None

    def done(self, result: int) -> None:  # noqa: A003
        self._test_poll.stop()
        self._set_testing_ui(True)
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._test_poll.stop()
        super().closeEvent(event)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.addItem(value)
            combo.setCurrentText(value)

    def result_config(self) -> AppConfig:
        cfg = self._config
        cfg.asr.api_url = self.asr_url.text().strip()
        cfg.asr.api_key = self.asr_key.text().strip()
        cfg.asr.model = self.asr_model.text().strip()
        cfg.llm.api_url = self.llm_url.text().strip()
        cfg.llm.api_key = self.llm_key.text().strip()
        cfg.llm.model = self.llm_model.text().strip()
        cfg.llm.temperature = float(self.temperature.value())
        cfg.llm.max_tokens = int(self.max_tokens.value())
        cfg.llm.timeout_sec = int(self.timeout_sec.value())
        cfg.source_lang = self.source_lang.currentText()
        cfg.target_lang = self.target_lang.currentText()
        cfg.translate_batch_size = int(self.translate_batch.value())
        cfg.proofread_batch_size = int(self.proof_batch.value())
        cfg.asr_max_seconds = int(self.asr_max.value())
        cfg.asr_chunk_seconds = int(self.asr_chunk.value())
        return cfg


class PromptDialog(QDialog):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("附加提示词")
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)
        head = QLabel("人名、专有名词对照、额外翻译要求")
        head.setStyleSheet(f"color:{Colors.ink};font-weight:600;font-size:14px;")
        layout.addWidget(head)
        tip = QLabel("写清楚角色名与固定译法，会带进后续翻译与统校。")
        tip.setObjectName("HintLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.editor = QPlainTextEdit(text)
        self.editor.setObjectName("ContentEdit")
        self.editor.setPlaceholderText("例如：太郎 → 太郎\n学校祭 → 校园祭")
        layout.addWidget(self.editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("保存")
        ok_btn.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def prompt_text(self) -> str:
        return self.editor.toPlainText()


class ExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出设置")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)
        head = QLabel("导出字幕")
        head.setStyleSheet(f"color:{Colors.ink};font-weight:600;font-size:14px;")
        layout.addWidget(head)
        form = QFormLayout()
        form.setSpacing(10)
        self.format_box = _NoWheelComboBox()
        self.format_box.addItems(["ASS", "SRT"])
        form.addRow("导出格式", self.format_box)

        row = QHBoxLayout()
        self.chk_source = QCheckBox("原文")
        self.chk_target = QCheckBox("译文")
        self.chk_source.setChecked(True)
        self.chk_target.setChecked(True)
        row.addWidget(self.chk_source)
        row.addWidget(self.chk_target)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("导出内容", wrap)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("确认导出")
        ok.setObjectName("PrimaryButton")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self._on_ok)
        self.chk_source.stateChanged.connect(self._update_ok)
        self.chk_target.stateChanged.connect(self._update_ok)
        layout.addWidget(self.buttons)
        self._update_ok()

    def _update_ok(self) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(self.chk_source.isChecked() or self.chk_target.isChecked())

    def _on_ok(self) -> None:
        if not (self.chk_source.isChecked() or self.chk_target.isChecked()):
            QMessageBox.warning(self, "导出", "至少勾选原文或译文之一")
            return
        self.accept()

    def export_options(self) -> tuple[str, bool, bool]:
        return (
            self.format_box.currentText().lower(),
            self.chk_source.isChecked(),
            self.chk_target.isChecked(),
        )
