from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont
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
from app.theme import Colors, FONT_UI, playlist_style


class PlaylistPanel(QWidget):
    track_selected = Signal(str)
    clear_result_requested = Signal(str)
    remove_track_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaylistPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(248)
        self.setStyleSheet(playlist_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 12)
        layout.setSpacing(8)
        title = QLabel("播放列表")
        title.setObjectName("PlaylistTitle")
        layout.addWidget(title)
        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setSpacing(2)
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
            row = self._make_row(track, track.id == current_id)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            if track.id == current_id:
                current_row = i
        if current_row >= 0:
            self.list.setCurrentRow(current_row)
        self.list.blockSignals(False)

    def _make_row(self, track: TrackItem, selected: bool) -> QWidget:
        row = QWidget()
        row.setObjectName("PlaylistRowSelected" if selected else "PlaylistRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(10, 8, 6, 8)
        outer.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        name = QLabel(track.display_name)
        name.setWordWrap(True)
        name.setObjectName("TrackName")
        name_font = QFont(FONT_UI)
        name_font.setPointSize(12)
        name_font.setWeight(QFont.Weight.DemiBold)
        name.setFont(name_font)

        status = QLabel(track.status.label)
        status.setObjectName("TrackStatus")
        status_font = QFont(FONT_UI)
        status_font.setPointSize(11)
        status.setFont(status_font)
        if track.status == TrackStatus.DONE:
            tone = Colors.ok
        elif track.status == TrackStatus.FAILED:
            tone = Colors.err
        elif track.status.is_busy:
            tone = Colors.busy
        else:
            tone = Colors.ink_faint
        status.setStyleSheet(
            f"color:{tone};background:transparent;border:none;"
        )

        can_remove = not track.status.is_active_pipeline
        btn = QPushButton("×")
        btn.setObjectName("RemoveTrack")
        btn.setFixedSize(22, 22)
        btn.setToolTip("从列表移除（保留工程文件）" if can_remove else "正在处理，无法移除")
        btn.setEnabled(can_remove)
        tid = track.id
        btn.clicked.connect(lambda _=False, x=tid: self.remove_track_requested.emit(x))

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(name)
        text_col.addWidget(status)
        top.addLayout(text_col, 1)
        top.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        row.setMinimumHeight(52)
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
