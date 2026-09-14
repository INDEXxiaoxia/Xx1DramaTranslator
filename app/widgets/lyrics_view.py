from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models import Cue
from app.icons import icon_minus, icon_plus
from app.theme import Colors, cue_row_style
from app.utils import format_cue_time, parse_cue_time


class CueRow(QFrame):
    translate_clicked = Signal(str)
    text_edited = Signal(str, str, str)  # cue_id, source, target
    timing_edited = Signal(str, int, int)  # cue_id, start_ms, end_ms
    delete_clicked = Signal(str)
    insert_after_clicked = Signal(str)
    activated = Signal(str)  # cue_id — 点击/聚焦，用于定位进度

    def __init__(self, cue: Cue, parent=None) -> None:
        super().__init__(parent)
        self.cue_id = cue.id
        self._start_ms = int(cue.start_ms)
        self._end_ms = int(cue.end_ms)
        self._level = 2
        self._editable = True
        self.setObjectName("CueRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)

        self.start_edit = QLineEdit(format_cue_time(self._start_ms))
        self.end_edit = QLineEdit(format_cue_time(self._end_ms))
        for ed in (self.start_edit, self.end_edit):
            ed.setFixedWidth(92)
            ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ed.setToolTip("时间格式如 1:23.456")
            ed.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            ed.setStyleSheet(
                "QLineEdit{font-family:'Cascadia Mono','Consolas','Microsoft YaHei UI';"
                "font-size:12px;}"
            )
        self.start_edit.editingFinished.connect(self._emit_timing)
        self.end_edit.editingFinished.connect(self._emit_timing)

        def _time_row(title: str, edit: QLineEdit) -> QWidget:
            wrap = QWidget()
            row = QHBoxLayout(wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lab = QLabel(title)
            lab.setFixedWidth(14)
            lab.setStyleSheet(f"color:{Colors.ink_faint};font-size:11px;")
            row.addWidget(lab)
            row.addWidget(edit)
            wrap.installEventFilter(self)
            lab.installEventFilter(self)
            return wrap

        time_col = QVBoxLayout()
        time_col.setContentsMargins(0, 0, 0, 0)
        time_col.setSpacing(6)
        time_col.addWidget(_time_row("起", self.start_edit))
        time_col.addWidget(_time_row("止", self.end_edit))
        layout.addLayout(time_col, 0)

        self.source_edit = QLineEdit(cue.source_text)
        self.source_edit.setObjectName("ContentEdit")
        self.source_edit.setPlaceholderText("原文")
        self.source_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.target_edit = QLineEdit(cue.target_text)
        self.target_edit.setObjectName("ContentEdit")
        self.target_edit.setPlaceholderText("译文")
        self.target_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)
        text_col.addWidget(self.source_edit)
        text_col.addWidget(self.target_edit)
        layout.addLayout(text_col, 1)

        self.btn_translate = QPushButton("翻译")
        self.btn_translate.setFixedWidth(72)
        self.btn_translate.setFixedHeight(28)
        self.btn_translate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_translate.clicked.connect(self._on_translate_click)

        self.btn_insert = QPushButton()
        self.btn_insert.setObjectName("IconQuiet")
        self.btn_insert.setIcon(icon_plus())
        self.btn_insert.setFixedSize(28, 28)
        self.btn_insert.setToolTip("在这句后面插入一句")
        self.btn_insert.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_insert.clicked.connect(lambda: self.insert_after_clicked.emit(self.cue_id))
        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("IconDanger")
        self.btn_delete.setIcon(icon_minus())
        self.btn_delete.setFixedSize(28, 28)
        self.btn_delete.setToolTip("删除这一句")
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.clicked.connect(lambda: self.delete_clicked.emit(self.cue_id))

        btn_top = QHBoxLayout()
        btn_top.setContentsMargins(0, 0, 0, 0)
        btn_top.addWidget(self.btn_translate)
        btn_bot = QHBoxLayout()
        btn_bot.setContentsMargins(0, 0, 0, 0)
        btn_bot.setSpacing(6)
        btn_bot.addWidget(self.btn_insert)
        btn_bot.addWidget(self.btn_delete)
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(6)
        btn_col.addLayout(btn_top)
        btn_col.addLayout(btn_bot)
        layout.addLayout(btn_col, 0)

        self.source_edit.editingFinished.connect(self._emit_edit)
        self.target_edit.editingFinished.connect(self._emit_edit)
        for w in (
            self.source_edit,
            self.target_edit,
            self.start_edit,
            self.end_edit,
            self.btn_translate,
            self.btn_insert,
            self.btn_delete,
        ):
            w.installEventFilter(self)

        self.set_editable(True)
        self.set_active_level(2)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress:
            if (
                isinstance(event, QMouseEvent)
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self.activated.emit(self.cue_id)
        elif event.type() == QEvent.Type.FocusIn:
            self.activated.emit(self.cue_id)
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.activated.emit(self.cue_id)
        super().mousePressEvent(event)

    def _on_translate_click(self) -> None:
        self._emit_edit()
        self._emit_timing()
        self.translate_clicked.emit(self.cue_id)

    def _emit_edit(self) -> None:
        self.text_edited.emit(
            self.cue_id,
            self.source_edit.text(),
            self.target_edit.text(),
        )

    def _emit_timing(self) -> None:
        start = parse_cue_time(self.start_edit.text())
        end = parse_cue_time(self.end_edit.text())
        if start is None or end is None:
            self.start_edit.setText(format_cue_time(self._start_ms))
            self.end_edit.setText(format_cue_time(self._end_ms))
            return
        if end < start:
            end = start
        self._start_ms = start
        self._end_ms = end
        self.start_edit.setText(format_cue_time(start))
        self.end_edit.setText(format_cue_time(end))
        self.timing_edited.emit(self.cue_id, start, end)

    def set_texts(self, source: str, target: str) -> None:
        self.source_edit.setText(source)
        self.target_edit.setText(target)

    def set_timing(self, start_ms: int, end_ms: int) -> None:
        self._start_ms = int(start_ms)
        self._end_ms = int(end_ms)
        self.start_edit.setText(format_cue_time(self._start_ms))
        self.end_edit.setText(format_cue_time(self._end_ms))

    def set_editable(self, editable: bool) -> None:
        """播放中只读：仍显示编辑框，禁止改动。"""
        self._editable = editable
        for ed in (self.source_edit, self.target_edit, self.start_edit, self.end_edit):
            ed.setReadOnly(not editable)
        for btn in (self.btn_translate, self.btn_insert, self.btn_delete):
            btn.setEnabled(editable)
        self.setCursor(
            Qt.CursorShape.ArrowCursor if editable else Qt.CursorShape.ArrowCursor
        )

    def set_translate_enabled(self, enabled: bool) -> None:
        # 播放只读时按钮本身已禁用；忙碌时额外锁翻译
        self.btn_translate.setEnabled(enabled and self._editable)
        self.btn_translate.setText("翻译" if enabled else "…")

    def set_active_level(self, level: int, content_width: int | None = None) -> None:
        """0=当前句（左侧色条高亮），其它=普通。content_width 保留兼容。"""
        del content_width
        self._level = level
        self.setStyleSheet(cue_row_style(level == 0))

    def reflow(self, content_width: int | None = None) -> None:
        del content_width
        self.updateGeometry()


class LyricsView(QWidget):
    translate_cue = Signal(str)
    cue_edited = Signal(str, str, str)
    cue_timing_edited = Signal(str, int, int)
    cue_delete_requested = Signal(str)
    cue_insert_after_requested = Signal(str)
    cue_seek_requested = Signal(int)  # 点击/切句时通知进度条

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cues: list[Cue] = []
        self._rows: list[CueRow] = []
        self._current_index = -1
        self._editable = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.container = QWidget()
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 12, 4, 12)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll)
        self.scroll.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _content_width(self) -> int:
        viewport_w = self.scroll.viewport().width()
        if viewport_w < 80:
            viewport_w = max(self.width() - 24, 480)
        return max(80, viewport_w - 24)

    def set_cues(self, cues: list[Cue]) -> None:
        self._cues = list(cues)
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows.clear()
        for cue in self._cues:
            self._rows.append(self._make_row(cue))
            self.container_layout.addWidget(self._rows[-1])
        self.container_layout.addStretch(1)
        self._current_index = -1
        QTimer.singleShot(0, self._reflow_all)

    def _make_row(self, cue: Cue) -> CueRow:
        row = CueRow(cue)
        row.translate_clicked.connect(self.translate_cue.emit)
        row.text_edited.connect(self.cue_edited.emit)
        row.timing_edited.connect(self.cue_timing_edited.emit)
        row.delete_clicked.connect(self.cue_delete_requested.emit)
        row.insert_after_clicked.connect(self.cue_insert_after_requested.emit)
        row.activated.connect(self._on_row_activated)
        row.set_editable(self._editable)
        return row

    def step_current(self, delta: int) -> None:
        if not self._cues:
            return
        if self._current_index < 0:
            idx = 0 if delta >= 0 else len(self._cues) - 1
        else:
            idx = max(0, min(len(self._cues) - 1, self._current_index + delta))
        self.highlight_index(idx, ensure_visible=True)
        self.cue_seek_requested.emit(self._cues[idx].start_ms)

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        for row in self._rows:
            row.set_editable(editable)

    def set_retranslate_busy(self, busy: bool) -> None:
        for row in self._rows:
            row.set_translate_enabled(not busy)

    def update_cue_target(self, cue_id: str, target: str) -> None:
        for cue in self._cues:
            if cue.id == cue_id:
                cue.target_text = target
                break
        for row in self._rows:
            if row.cue_id == cue_id:
                row.set_texts(row.source_edit.text(), target)
                break

    def update_position(self, position_ms: int, *, scroll: bool = True) -> None:
        if not self._cues:
            return
        idx = 0
        for i, cue in enumerate(self._cues):
            if cue.start_ms <= position_ms <= cue.end_ms:
                idx = i
                break
            if position_ms < cue.start_ms:
                idx = max(0, i - 1)
                break
            idx = i
        if idx != self._current_index:
            self._current_index = idx
            self._refresh_levels()
            if scroll:
                self._ensure_index_visible(idx)

    def highlight_index(self, idx: int, *, scroll: bool = False, ensure_visible: bool | None = None) -> None:
        if idx < 0 or idx >= len(self._rows):
            return
        if idx != self._current_index:
            self._current_index = idx
            self._refresh_levels()
        if ensure_visible is None:
            ensure_visible = scroll
        if ensure_visible:
            self._ensure_index_visible(idx)

    def _on_row_activated(self, cue_id: str) -> None:
        for i, cue in enumerate(self._cues):
            if cue.id == cue_id:
                self.highlight_index(i, ensure_visible=True)
                self.cue_seek_requested.emit(cue.start_ms)
                return

    def _refresh_levels(self) -> None:
        for i, row in enumerate(self._rows):
            level = 0 if i == self._current_index else 2
            row.set_active_level(level)

    def _reflow_all(self) -> None:
        viewport_w = self.scroll.viewport().width()
        if viewport_w > 40:
            self.container.setMinimumWidth(viewport_w)
        for row in self._rows:
            row.reflow()
        self.container_layout.activate()
        self.container.adjustSize()
        self.container.updateGeometry()

    def _ensure_index_visible(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._rows):
            return
        QTimer.singleShot(0, lambda i=idx: self._ensure_index_visible_now(i))

    def _ensure_index_visible_now(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._rows):
            return
        self._reflow_all()
        row = self._rows[idx]
        vp = self.scroll.viewport()
        bar = self.scroll.verticalScrollBar()
        area_h = max(1, vp.height())
        center = row.mapTo(self.container, row.rect().center())
        target = int(center.y() - area_h * 0.5)
        # 中间句尽量让上一句、下一句都露出来；首尾句自然夹在两端
        if 0 < idx < len(self._rows) - 1:
            prev_row = self._rows[idx - 1]
            next_row = self._rows[idx + 1]
            prev_top = prev_row.mapTo(self.container, prev_row.rect().topLeft()).y()
            next_bot = next_row.mapTo(self.container, next_row.rect().bottomLeft()).y()
            if next_bot - prev_top <= area_h:
                lo = next_bot - area_h
                hi = prev_top
                if lo <= hi:
                    target = max(lo, min(hi, target))
        target = max(bar.minimum(), min(bar.maximum(), target))
        bar.setValue(target)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_all()
        if self._current_index >= 0:
            self._ensure_index_visible(self._current_index)
