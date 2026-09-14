from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import TrackItem, TrackStatus


class PlaylistPanel(QWidget):
    track_selected = Signal(str)
    clear_result_requested = Signal(str)
    remove_track_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("播放列表")
        title.setStyleSheet("font-weight:600;font-size:14px;")
        layout.addWidget(title)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_click)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)
        layout.addWidget(self.list)
        self._tracks: dict[str, TrackItem] = {}

    def set_tracks(self, tracks: list[TrackItem], current_id: str | None) -> None:
        self._tracks = {t.id: t for t in tracks}
        self.list.blockSignals(True)
        self.list.clear()
        current_row = -1
        for i, track in enumerate(tracks):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track.id)
            item.setSizeHint(self._make_row(track, track.id == current_id).sizeHint())
            self.list.addItem(item)
            row = self._make_row(track, track.id == current_id)
            self.list.setItemWidget(item, row)
            if track.id == current_id:
                current_row = i
        if current_row >= 0:
            self.list.setCurrentRow(current_row)
        self.list.blockSignals(False)

    def _make_row(self, track: TrackItem, selected: bool) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(6, 4, 4, 4)
        hl.setSpacing(4)

        text = QLabel(f"{track.display_name}\n{track.status.label}")
        text.setWordWrap(True)
        if track.status == TrackStatus.DONE:
            text.setStyleSheet("color:#1a7f37;")
        elif track.status == TrackStatus.FAILED:
            text.setStyleSheet("color:#c01c28;")
        elif track.status.is_busy:
            text.setStyleSheet("color:#1a5fb4;")
        if selected:
            row.setStyleSheet("background:#e8e8e8;border-radius:4px;")
        hl.addWidget(text, 1)

        # 识别/翻译进行中不可叉掉
        can_remove = not track.status.is_active_pipeline
        btn = QPushButton("×")
        btn.setFixedSize(24, 24)
        btn.setToolTip("从列表移除（保留工程文件）" if can_remove else "正在处理，无法移除")
        btn.setEnabled(can_remove)
        btn.setStyleSheet(
            "QPushButton{border:none;color:#666;font-size:16px;}"
            "QPushButton:hover{color:#c01c28;}"
            "QPushButton:disabled{color:#ccc;}"
        )
        tid = track.id
        btn.clicked.connect(lambda _=False, x=tid: self.remove_track_requested.emit(x))
        hl.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        row.setMinimumHeight(44)
        return row

    def _on_click(self, item: QListWidgetItem) -> None:
        track_id = item.data(Qt.ItemDataRole.UserRole)
        if track_id:
            self.track_selected.emit(str(track_id))

    def _on_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        track_id = str(item.data(Qt.ItemDataRole.UserRole))
        track = self._tracks.get(track_id)
        if not track:
            return
        menu = QMenu(self)
        if track.status == TrackStatus.DONE:
            act = QAction("清除翻译结果", self)
            act.triggered.connect(lambda: self.clear_result_requested.emit(track_id))
            menu.addAction(act)
        if not track.status.is_active_pipeline:
            act2 = QAction("从列表移除", self)
            act2.triggered.connect(lambda: self.remove_track_requested.emit(track_id))
            menu.addAction(act2)
        if menu.actions():
            menu.exec(self.list.mapToGlobal(pos))
