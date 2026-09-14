from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QThread
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from app.config import (
    AppConfig,
    ConfigStore,
    is_project_file,
    load_project,
    project_path_for_audio,
    save_project,
)
from app.models import Cue, TrackItem, TrackStatus, new_cue_id, new_track_id
from app.icons import icon_list, icon_pause, icon_play, icon_settings
from app.services.audio_player import AudioPlayer
from app.services.exporter import export_subtitles
from app.theme import Colors, controls_style, status_page_style
from app.utils import format_time, is_audio_file, probe_duration_ms
from app.widgets.dialogs import ExportDialog, PromptDialog, SettingsDialog
from app.widgets.lyrics_view import LyricsView
from app.widgets.playlist_panel import PlaylistPanel
from app.workers import PipelineWorker, RetranslateWorker, WorkerHost


def _format_status_text(text: str, limit: int = 500) -> str:
    """避免超长单行错误把窗口撑宽。"""
    t = (text or "").strip()
    if len(t) > limit:
        t = t[:limit] + "…"
    # JSON/URL 中间插入软换行机会：按标点拆开显示
    return t.replace("},{", "},\n{").replace("; ", ";\n")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Xx1DramaTranslator")
        self.resize(960, 640)
        self.setAcceptDrops(True)

        self.store = ConfigStore()
        self.config: AppConfig = self.store.load_config()
        self.tracks: list[TrackItem] = []
        self.current_track_id: str | None = None
        self.queue: list[str] = []
        self.worker_host = WorkerHost()
        self._retranslate_thread: QThread | None = None
        self._retranslate_worker: RetranslateWorker | None = None
        self._seek_dragging = False
        self._nav_last_key: int | None = None
        self._nav_last_t: float = 0.0
        self._wheel_acc: int = 0

        self.player = AudioPlayer(self)
        self.player.position_changed.connect(self._on_player_position)
        self.player.duration_changed.connect(self._on_player_duration)
        self.player.playing_changed.connect(self._on_playing_changed)
        self.player.error_occurred.connect(self._on_player_error)
        self.player.output_changed.connect(self._on_player_output_changed)

        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        # 首次打开不自动恢复工程，保持初始空界面
        self._refresh_all()

        self._project_save_timer = QTimer(self)
        self._project_save_timer.setSingleShot(True)
        self._project_save_timer.setInterval(800)
        self._project_save_timer.timeout.connect(self._save_project)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        main_col = QVBoxLayout()
        main_col.setContentsMargins(20, 18, 20, 14)
        main_col.setSpacing(14)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(status_page_style())

        # —— 空态：拖入区 ——
        self.empty_label = QLabel(
            "将 mp3 / wav 拖到这里\n或拖入 .xx1proj 继续上次的工作"
        )
        self.empty_label.setObjectName("StatusTitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setWeight(QFont.Weight.DemiBold)
        self.empty_label.setFont(title_font)

        empty_hint = QLabel("先在设置里配好识别与翻译接口，再点「开始翻译」")
        empty_hint.setObjectName("StatusBody")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setWordWrap(True)

        empty_eyebrow = QLabel("拖入开始")
        empty_eyebrow.setObjectName("StatusEyebrow")
        empty_eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)

        drop = QFrame()
        drop.setObjectName("DropZone")
        drop.setMinimumHeight(220)
        drop.setMinimumWidth(440)
        drop.setMaximumWidth(560)
        drop_l = QVBoxLayout(drop)
        drop_l.setContentsMargins(36, 40, 36, 40)
        drop_l.setSpacing(12)
        drop_l.addStretch(1)
        drop_l.addWidget(empty_eyebrow)
        drop_l.addWidget(self.empty_label)
        drop_l.addWidget(empty_hint)
        drop_l.addStretch(1)

        self.page_empty = QWidget()
        pe = QVBoxLayout(self.page_empty)
        pe.setContentsMargins(24, 28, 24, 12)
        pe.addStretch(1)
        pe.addWidget(drop, 0, Qt.AlignmentFlag.AlignHCenter)
        pe.addStretch(1)

        # —— 等待 / 失败 / 取消 ——
        self.wait_label = QLabel("正在等待翻译任务开始")
        self.wait_label.setObjectName("StatusBody")
        self.wait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wait_label.setWordWrap(True)
        self.wait_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.wait_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        wait_title = QLabel("稍候")
        wait_title.setObjectName("StatusTitle")
        wait_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wait_title.setFont(title_font)
        self._wait_title = wait_title

        wait_eyebrow = QLabel("待命")
        wait_eyebrow.setObjectName("StatusEyebrow")
        wait_eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._wait_eyebrow = wait_eyebrow

        wait_card = QFrame()
        wait_card.setObjectName("StatusCard")
        wait_card.setMinimumWidth(420)
        wait_card.setMaximumWidth(560)
        wc = QVBoxLayout(wait_card)
        wc.setContentsMargins(32, 36, 32, 36)
        wc.setSpacing(10)
        wc.addWidget(wait_eyebrow)
        wc.addWidget(wait_title)
        wc.addWidget(self.wait_label)

        self.page_wait = QWidget()
        pw = QVBoxLayout(self.page_wait)
        pw.setContentsMargins(24, 28, 24, 12)
        pw.addStretch(1)
        pw.addWidget(wait_card, 0, Qt.AlignmentFlag.AlignHCenter)
        pw.addStretch(1)

        # —— 进度 ——
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("StatusBody")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setWordWrap(True)
        self.progress_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.progress_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        progress_title = QLabel("正在处理")
        progress_title.setObjectName("StatusTitle")
        progress_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_title.setFont(title_font)

        progress_eyebrow = QLabel("处理中")
        progress_eyebrow.setObjectName("StatusEyebrow")
        progress_eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._breath_dot = QLabel("●")
        self._breath_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._breath_dot.setStyleSheet(f"color:{Colors.accent};font-size:14px;")
        self._breath_effect = QGraphicsOpacityEffect(self._breath_dot)
        self._breath_dot.setGraphicsEffect(self._breath_effect)
        self._breath_anim = QPropertyAnimation(self._breath_effect, b"opacity", self)
        self._breath_anim.setDuration(1600)
        self._breath_anim.setStartValue(0.28)
        self._breath_anim.setEndValue(1.0)
        self._breath_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._breath_anim.setLoopCount(-1)

        progress_card = QFrame()
        progress_card.setObjectName("StatusCard")
        progress_card.setMinimumWidth(420)
        progress_card.setMaximumWidth(560)
        pc = QVBoxLayout(progress_card)
        pc.setContentsMargins(32, 36, 32, 36)
        pc.setSpacing(10)
        pc.addWidget(progress_eyebrow)
        pc.addWidget(self._breath_dot)
        pc.addWidget(progress_title)
        pc.addWidget(self.progress_label)

        self.page_progress = QWidget()
        pp = QVBoxLayout(self.page_progress)
        pp.setContentsMargins(24, 28, 24, 12)
        pp.addStretch(1)
        pp.addWidget(progress_card, 0, Qt.AlignmentFlag.AlignHCenter)
        pp.addStretch(1)

        self.lyrics = LyricsView()
        self.lyrics.translate_cue.connect(self._on_retranslate_cue)
        self.lyrics.cue_edited.connect(self._on_cue_edited)
        self.lyrics.cue_timing_edited.connect(self._on_cue_timing_edited)
        self.lyrics.cue_delete_requested.connect(self._on_cue_delete)
        self.lyrics.cue_insert_after_requested.connect(self._on_cue_insert_after)
        self.lyrics.cue_seek_requested.connect(self._on_cue_seek_requested)
        self.page_lyrics = self.lyrics

        self.stack.addWidget(self.page_empty)
        self.stack.addWidget(self.page_wait)
        self.stack.addWidget(self.page_progress)
        self.stack.addWidget(self.page_lyrics)
        self.stack.currentChanged.connect(self._on_stack_changed)
        main_col.addWidget(self.stack, 1)

        # Controls
        controls = QFrame()
        controls.setObjectName("Controls")
        controls.setStyleSheet(controls_style())
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        time_row = QHBoxLayout()
        time_row.setSpacing(10)
        self.pos_label = QLabel("0:00")
        self.pos_label.setObjectName("TimeLabel")
        self.dur_label = QLabel("0:00")
        self.dur_label.setObjectName("TimeLabel")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.sliderPressed.connect(self._on_seek_press)
        self.slider.sliderReleased.connect(self._on_seek_release)
        self.slider.sliderMoved.connect(self._on_seek_moved)
        time_row.addWidget(self.pos_label)
        time_row.addWidget(self.slider, 1)
        time_row.addWidget(self.dur_label)
        cl.addLayout(time_row)

        self.filename_label = QLabel("未选择文件")
        self.filename_label.setObjectName("FileName")
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.filename_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_play = QPushButton()
        self.btn_play.setObjectName("IconButton")
        self.btn_play.setIcon(icon_play())
        self.btn_play.setFixedSize(36, 36)
        self.btn_play.setToolTip("播放")
        self.btn_play.clicked.connect(self._toggle_play)
        self._speed_options = (1.0, 1.25, 1.5, 2.0, 3.0)
        self._speed_index = 0
        self.btn_speed = QPushButton("x1")
        self.btn_speed.setObjectName("GhostButton")
        self.btn_speed.setFixedWidth(56)
        self.btn_speed.setToolTip("播放倍速")
        self.btn_speed.clicked.connect(self._cycle_playback_speed)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setToolTip("音量")
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("IconButton")
        self.btn_settings.setIcon(icon_settings())
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.setToolTip("设置")
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_prompt = QPushButton("附加提示词")
        self.btn_prompt.clicked.connect(self._open_prompt)
        self.btn_main = QPushButton("开始翻译")
        self.btn_main.setObjectName("PrimaryButton")
        self.btn_main.clicked.connect(self._on_main_action)
        self.btn_export = QPushButton("导出")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.hide()
        self.btn_cancel = QPushButton("取消翻译")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.hide()
        self.btn_playlist = QPushButton()
        self.btn_playlist.setObjectName("IconButton")
        self.btn_playlist.setIcon(icon_list())
        self.btn_playlist.setFixedSize(36, 36)
        self.btn_playlist.setToolTip("播放列表")
        self.btn_playlist.clicked.connect(self._toggle_playlist)

        for b in (
            self.btn_play,
            self.btn_speed,
            self.volume_slider,
            self.btn_settings,
            self.btn_prompt,
            self.btn_main,
            self.btn_export,
            self.btn_cancel,
            self.btn_playlist,
        ):
            btn_row.addWidget(b)
            if isinstance(b, QPushButton):
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._on_player_output_changed(self.player.output_name())
        cl.addLayout(btn_row)
        main_col.addWidget(controls)

        main_wrap = QWidget()
        main_wrap.setLayout(main_col)
        root_layout.addWidget(main_wrap, 1)

        self.playlist_panel = PlaylistPanel()
        self.playlist_panel.track_selected.connect(self._select_track)
        self.playlist_panel.clear_result_requested.connect(self._clear_track_result)
        self.playlist_panel.remove_track_requested.connect(self._remove_track)
        self.playlist_panel.setVisible(self.config.playlist_expanded)
        root_layout.addWidget(self.playlist_panel)

    def _on_stack_changed(self, index: int) -> None:
        """进度页开启呼吸动效，离开时停下。"""
        if self.stack.widget(index) is self.page_progress:
            if self._breath_anim.state() != QPropertyAnimation.State.Running:
                self._breath_anim.start()
        else:
            self._breath_anim.stop()
            self._breath_effect.setOpacity(1.0)

    # ---- project ----
    def _schedule_project_save(self) -> None:
        if not self.tracks:
            return
        self._project_save_timer.start()

    def _project_path_of(self, track: TrackItem) -> Path:
        return project_path_for_audio(track.path)

    def _update_window_title(self) -> None:
        track = self._current_track()
        if track:
            self.setWindowTitle(
                f"Xx1DramaTranslator — {self._project_path_of(track).name}"
            )
        else:
            self.setWindowTitle("Xx1DramaTranslator")

    def _build_track_payload(self, track: TrackItem) -> dict:
        if track.id == self.current_track_id:
            track.position_ms = self.player.position()
        return {
            "version": 2,
            "additional_prompt": self.config.additional_prompt,
            "source_lang": self.config.source_lang,
            "target_lang": self.config.target_lang,
            "track": track.to_dict(),
            # 兼容旧读取逻辑
            "tracks": [track.to_dict()],
            "current_track_id": track.id,
        }

    def _save_project(self) -> None:
        """每个音频各自保存到同名 .xx1proj。"""
        if not self.tracks:
            return
        errors: list[str] = []
        for track in self.tracks:
            path = self._project_path_of(track)
            try:
                save_project(path, self._build_track_payload(track))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self._update_window_title()
        if errors:
            QMessageBox.warning(self, "保存工程失败", "\n".join(errors[:8]))

    def _load_project_file(self, path: str) -> None:
        path = str(Path(path).resolve())
        try:
            data = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "打开工程失败", str(exc))
            return

        # v2: 单 track；v1: 多 tracks → 拆成多个工程加入列表
        raw_tracks: list[TrackItem] = []
        if isinstance(data.get("track"), dict):
            raw_tracks = [TrackItem.from_dict(data["track"])]
        else:
            raw_tracks = [TrackItem.from_dict(t) for t in data.get("tracks", [])]

        if not raw_tracks:
            QMessageBox.warning(self, "打开工程失败", "工程中没有音频条目")
            return

        missing = [t for t in raw_tracks if not Path(t.path).exists()]
        if missing:
            names = "\n".join(f"• {t.path}" for t in missing[:20])
            more = "" if len(missing) <= 20 else f"\n…共 {len(missing)} 个"
            reply = QMessageBox.question(
                self,
                "音频文件缺失",
                f"以下音频文件不存在：\n{names}{more}\n\n"
                "是否跳过缺失项并继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            missing_ids = {t.id for t in missing}
            raw_tracks = [t for t in raw_tracks if t.id not in missing_ids]
            if not raw_tracks:
                return

        if data.get("additional_prompt") is not None:
            self.config.additional_prompt = str(data.get("additional_prompt", ""))
        if data.get("source_lang"):
            self.config.source_lang = str(data["source_lang"])
        if data.get("target_lang"):
            self.config.target_lang = str(data["target_lang"])

        # 旧多轨工程：拆分保存为各自工程后加入播放列表
        added_ids: list[str] = []
        for track in raw_tracks:
            existing = next((t for t in self.tracks if t.path == track.path), None)
            if existing:
                # 用工程内容覆盖会话中的同路径条目
                idx = self.tracks.index(existing)
                self.tracks[idx] = track
                added_ids.append(track.id)
            else:
                self.tracks.append(track)
                added_ids.append(track.id)
            try:
                save_project(self._project_path_of(track), self._build_track_payload(track))
            except Exception:
                pass

        self.current_track_id = added_ids[0]
        track = self._track_by_id(self.current_track_id)
        if track:
            self._load_player_for(track)
        self._update_window_title()
        self._save_project()
        self._refresh_all()

        if len(raw_tracks) > 1:
            QMessageBox.information(
                self,
                "已拆分工程",
                "检测到旧版多音频工程，已按「一音频一工程」拆成多个 .xx1proj 并加入播放列表。",
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.worker_host.cancel()
        self.worker_host.stop_join()
        if self.tracks:
            self._save_project()
        super().closeEvent(event)

    # ---- tracks helpers ----
    def _current_track(self) -> TrackItem | None:
        return self._track_by_id(self.current_track_id)

    def _track_by_id(self, track_id: str | None) -> TrackItem | None:
        if not track_id:
            return None
        for t in self.tracks:
            if t.id == track_id:
                return t
        return None

    def _has_busy_queue(self) -> bool:
        if self.queue:
            return True
        return any(t.status.is_busy for t in self.tracks)

    def _active_pipeline_track(self) -> TrackItem | None:
        for t in self.tracks:
            if t.status.is_active_pipeline:
                return t
        return None

    # ---- drag drop ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        audio_paths: list[str] = []
        project_paths: list[str] = []
        ignored = False
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if is_project_file(path):
                project_paths.append(path)
            elif is_audio_file(path):
                audio_paths.append(path)
            else:
                ignored = True

        if project_paths:
            for pp in project_paths:
                self._load_project_file(pp)
            return

        if ignored and not audio_paths:
            QMessageBox.information(
                self,
                "提示",
                "仅支持 mp3 / wav 音频，或 .xx1proj 工程文件",
            )
            return
        for path in audio_paths:
            self._add_track(path)
        self._refresh_all()

    def _add_track(self, path: str) -> None:
        path = str(Path(path).resolve())
        if not Path(path).exists():
            QMessageBox.warning(self, "文件缺失", f"音频文件不存在：\n{path}")
            return
        if any(t.path == path for t in self.tracks):
            for t in self.tracks:
                if t.path == path:
                    self._select_track(t.id)
                    return

        proj = project_path_for_audio(path)
        if proj.exists():
            # 已有独立工程：读入后加入列表
            try:
                data = load_project(proj)
                if isinstance(data.get("track"), dict):
                    track = TrackItem.from_dict(data["track"])
                elif data.get("tracks"):
                    # 旧多轨里找同路径
                    track = None
                    for td in data["tracks"]:
                        t = TrackItem.from_dict(td)
                        if Path(t.path).resolve() == Path(path):
                            track = t
                            break
                    if track is None:
                        track = TrackItem.from_dict(data["tracks"][0])
                        track.path = path
                        track.display_name = Path(path).name
                else:
                    track = None
                if track is not None:
                    track.path = path
                    track.display_name = Path(path).name
                    self.tracks.append(track)
                    if self.current_track_id is None:
                        self._select_track(track.id)
                    else:
                        self._schedule_project_save()
                        self._refresh_all()
                    return
            except Exception:
                pass

        name = Path(path).name
        track = TrackItem(
            id=new_track_id(),
            path=path,
            display_name=name,
            duration_ms=probe_duration_ms(path),
        )
        self.tracks.append(track)
        if self.current_track_id is None:
            self._select_track(track.id)
        self._schedule_project_save()

    def _remove_track(self, track_id: str) -> None:
        track = self._track_by_id(track_id)
        if not track:
            return
        if track.status.is_active_pipeline:
            QMessageBox.information(self, "无法移除", "该文件正在识别/翻译中，请先取消或等完成。")
            return
        # 移出队列
        self.queue = [q for q in self.queue if q != track_id]
        was_current = self.current_track_id == track_id
        if was_current:
            track.position_ms = self.player.position()
            self.player.stop()
        self.tracks = [t for t in self.tracks if t.id != track_id]
        if was_current:
            self.current_track_id = self.tracks[0].id if self.tracks else None
            if self.current_track_id:
                self._load_player_for(self._track_by_id(self.current_track_id))  # type: ignore[arg-type]
        self._update_window_title()
        self._schedule_project_save()
        self._refresh_all()

    def _select_track(self, track_id: str) -> None:
        prev = self._current_track()
        if prev:
            prev.position_ms = self.player.position()
        self.current_track_id = track_id
        track = self._track_by_id(track_id)
        if track:
            if not Path(track.path).exists():
                QMessageBox.warning(
                    self,
                    "文件缺失",
                    f"音频文件不存在：\n{track.path}",
                )
            else:
                self._load_player_for(track)
        self._update_window_title()
        self._schedule_project_save()
        self._refresh_all()

    def _load_player_for(self, track: TrackItem) -> None:
        if not Path(track.path).exists():
            return
        self.player.load(track.path)
        if track.duration_ms:
            self.slider.setRange(0, track.duration_ms)
            self.dur_label.setText(format_time(track.duration_ms))
        QTimer.singleShot(100, lambda: self.player.seek(track.position_ms))

    def _clear_track_result(self, track_id: str) -> None:
        track = self._track_by_id(track_id)
        if not track:
            return
        reply = QMessageBox.question(
            self,
            "清除翻译结果",
            f"确认清除「{track.display_name}」的翻译结果？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        track.cues = []
        track.status = TrackStatus.IDLE
        track.progress_text = "正在等待翻译任务开始"
        track.error_message = ""
        track.warning_message = ""
        self._refresh_all()
        self._schedule_project_save()

    # ---- refresh UI ----
    def _refresh_all(self) -> None:
        track = self._current_track()
        self.playlist_panel.set_tracks(self.tracks, self.current_track_id)
        self.playlist_panel.setVisible(self.config.playlist_expanded)
        self.btn_playlist.setToolTip(
            "收起列表" if self.config.playlist_expanded else "播放列表"
        )

        if not track:
            self.stack.setCurrentWidget(self.page_empty)
            self.filename_label.setText("未选择文件")
            self.btn_play.setEnabled(False)
            self.slider.setEnabled(False)
            self.btn_export.hide()
            self._update_main_button()
            self._update_cancel_button()
            return

        self.filename_label.setText(track.display_name)
        self.btn_play.setEnabled(True)
        self.slider.setEnabled(True)
        if track.duration_ms:
            self.slider.setRange(0, max(1, track.duration_ms))
            self.dur_label.setText(format_time(track.duration_ms))

        if track.status == TrackStatus.DONE and track.cues:
            self.stack.setCurrentWidget(self.page_lyrics)
            self.lyrics.set_cues(track.cues)
            self.lyrics.set_editable(not self.player.is_playing())
            self.lyrics.update_position(self.player.position())
            self.btn_export.show()
            if track.warning_message:
                self.wait_label.setText(track.warning_message)
        elif track.status.is_active_pipeline or (
            track.status == TrackStatus.QUEUED and track.id == (self.queue[0] if self.queue else None)
        ):
            self.stack.setCurrentWidget(self.page_progress)
            self.progress_label.setText(_format_status_text(track.progress_text or "处理中…"))
            self.btn_export.hide()
        elif track.status == TrackStatus.QUEUED:
            self.stack.setCurrentWidget(self.page_wait)
            self._wait_eyebrow.setText("排队")
            self._wait_title.setText("排队中")
            self.wait_label.setText("已加入翻译队列，等待中…")
            self.btn_export.hide()
        elif track.status == TrackStatus.FAILED:
            self.stack.setCurrentWidget(self.page_wait)
            self._wait_eyebrow.setText("失败")
            self._wait_title.setText("出错了")
            self.wait_label.setText(_format_status_text(f"失败：{track.error_message}"))
            self.btn_export.hide()
        elif track.status == TrackStatus.CANCELLED:
            self.stack.setCurrentWidget(self.page_wait)
            self._wait_eyebrow.setText("取消")
            self._wait_title.setText("已取消")
            self.wait_label.setText("已取消，可重新开始")
            self.btn_export.hide()
        else:
            self.stack.setCurrentWidget(self.page_wait)
            self._wait_eyebrow.setText("待命")
            self._wait_title.setText("准备就绪")
            self.wait_label.setText("正在等待翻译任务开始")
            self.btn_export.hide()

        self._update_main_button()
        self._update_cancel_button()

    def _update_main_button(self) -> None:
        busy = self._has_busy_queue()
        self.btn_main.setText("加入翻译队列" if busy else "开始翻译")
        track = self._current_track()
        enabled = False
        if track and self.config.is_api_configured():
            if track.status in {TrackStatus.IDLE, TrackStatus.FAILED, TrackStatus.CANCELLED}:
                if track.id not in self.queue and not track.status.is_active_pipeline:
                    enabled = True
        self.btn_main.setEnabled(enabled)

    def _update_cancel_button(self) -> None:
        show = self._active_pipeline_track() is not None
        self.btn_cancel.setVisible(show)

    # ---- playback ----
    def _toggle_play(self) -> None:
        track = self._current_track()
        if not track:
            return
        if not Path(track.path).exists():
            QMessageBox.warning(self, "无法播放", f"音频文件不存在：\n{track.path}")
            return
        # 确保已加载当前曲目
        if self.player._path != str(Path(track.path).resolve()):
            self._load_player_for(track)
        self.player.toggle()
        out = self.player.output_name()
        if out:
            self.btn_play.setToolTip(f"当前输出设备：{out}")

    def _speed_label(self, rate: float) -> str:
        if abs(rate - round(rate)) < 1e-6:
            return f"x{int(round(rate))}"
        text = f"{rate:.2f}".rstrip("0").rstrip(".")
        return f"x{text}"

    def _cycle_playback_speed(self) -> None:
        self._speed_index = (self._speed_index + 1) % len(self._speed_options)
        rate = self._speed_options[self._speed_index]
        self.player.set_playback_rate(rate)
        self.btn_speed.setText(self._speed_label(rate))

    def _can_step_lyrics(self) -> bool:
        if not self.isActiveWindow():
            return False
        track = self._current_track()
        return bool(
            track
            and track.status == TrackStatus.DONE
            and track.cues
            and self.stack.currentWidget() is self.page_lyrics
        )

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.Wheel:
            return self._filter_lyrics_wheel(obj, event)
        if et not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return super().eventFilter(obj, event)
        if event.key() not in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return super().eventFilter(obj, event)
        if not self._lyrics_nav_context(obj):
            return super().eventFilter(obj, event)
        # ShortcutOverride 只占键，不切句，避免和下一次 KeyPress 叠成跳两句
        event.accept()
        if et == QEvent.Type.ShortcutOverride:
            return True
        now = time.perf_counter()
        key = int(event.key())
        if key == self._nav_last_key and (now - self._nav_last_t) < 0.012:
            return True
        self._nav_last_key = key
        self._nav_last_t = now
        self.lyrics.step_current(-1 if key == Qt.Key.Key_Up else 1)
        return True

    def _lyrics_nav_context(self, obj) -> bool:
        widget = obj if isinstance(obj, QWidget) else None
        if widget is not None:
            win = widget.window()
            if win is not self and win is not self.window():
                return False
        if not self._can_step_lyrics():
            return False
        fw = self.focusWidget()
        if fw is not None and self.playlist_panel.isAncestorOf(fw):
            return False
        return True

    def _filter_lyrics_wheel(self, obj, event) -> bool:
        if not self._can_step_lyrics():
            return super().eventFilter(obj, event)
        widget = obj if isinstance(obj, QWidget) else None
        if widget is None:
            return super().eventFilter(obj, event)
        win = widget.window()
        if win is not self and win is not self.window():
            return super().eventFilter(obj, event)
        if widget is not self.lyrics and not self.lyrics.isAncestorOf(widget):
            return super().eventFilter(obj, event)
        delta = int(event.angleDelta().y())
        if delta == 0:
            delta = int(event.pixelDelta().y())
        if delta == 0:
            return True
        self._wheel_acc += delta
        # 一格滚轮 = 一句，与键盘上下相同
        while self._wheel_acc >= 120:
            self._wheel_acc -= 120
            self.lyrics.step_current(-1)
        while self._wheel_acc <= -120:
            self._wheel_acc += 120
            self.lyrics.step_current(1)
        return True

    def _on_volume_changed(self, value: int) -> None:
        self.player.set_volume(value / 100.0)
        self.volume_slider.setToolTip(f"音量 {value}%")

    def _on_player_error(self, message: str) -> None:
        QMessageBox.warning(self, "播放失败", message or "未知错误")

    def _on_player_output_changed(self, name: str) -> None:
        action = "暂停" if self.player.is_playing() else "播放"
        tip = f"{action} · {name}" if name else action
        self.btn_play.setToolTip(tip)

    def _on_playing_changed(self, playing: bool) -> None:
        self.btn_play.setIcon(icon_pause() if playing else icon_play())
        out = self.player.output_name()
        action = "暂停" if playing else "播放"
        self.btn_play.setToolTip(f"{action} · {out}" if out else action)
        track = self._current_track()
        if track and track.status == TrackStatus.DONE:
            self.lyrics.set_editable(not playing)

    def _on_player_position(self, pos: int) -> None:
        if not self._seek_dragging:
            self.slider.blockSignals(True)
            self.slider.setValue(pos)
            self.slider.blockSignals(False)
        self.pos_label.setText(format_time(pos))
        track = self._current_track()
        if track and track.status == TrackStatus.DONE:
            # 暂停时由点击/方向键决定当前句，避免 seek 回传旧位置把选中打回去
            if self.player.is_playing() or self._seek_dragging:
                self.lyrics.update_position(pos, scroll=True)

    def _on_player_duration(self, dur: int) -> None:
        if dur > 0:
            self.slider.setRange(0, dur)
            self.dur_label.setText(format_time(dur))
            track = self._current_track()
            if track and track.duration_ms <= 0:
                track.duration_ms = dur

    def _on_seek_press(self) -> None:
        self._seek_dragging = True

    def _on_seek_release(self) -> None:
        self._seek_dragging = False
        self.player.seek(self.slider.value())

    def _on_seek_moved(self, value: int) -> None:
        self.pos_label.setText(format_time(value))
        track = self._current_track()
        if track and track.status == TrackStatus.DONE:
            self.lyrics.update_position(value, scroll=True)

    # ---- dialogs ----
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self.store.save_config(self.config)
            self._refresh_all()

    def _open_prompt(self) -> None:
        dlg = PromptDialog(self.config.additional_prompt, self)
        if dlg.exec():
            self.config.additional_prompt = dlg.prompt_text()
            # 提示词属于工程专属配置，写入工程；语言等全局项仍在程序配置
            self._schedule_project_save()

    def _toggle_playlist(self) -> None:
        self.config.playlist_expanded = not self.config.playlist_expanded
        self.playlist_panel.setVisible(self.config.playlist_expanded)
        self.btn_playlist.setToolTip(
            "收起列表" if self.config.playlist_expanded else "播放列表"
        )
        self.store.save_config(self.config)

    # ---- translate queue ----
    def _on_main_action(self) -> None:
        track = self._current_track()
        if not track or not self.config.is_api_configured():
            return
        track.prompt_snapshot = self.config.additional_prompt
        track.error_message = ""
        track.warning_message = ""
        track.cues = []
        if track.id not in self.queue:
            self.queue.append(track.id)
        track.status = TrackStatus.QUEUED
        track.progress_text = "已加入翻译队列，等待中…"
        self._refresh_all()
        self._schedule_project_save()
        self._pump_queue()

    def _pump_queue(self) -> None:
        if self.worker_host.busy:
            return
        while self.queue:
            track_id = self.queue[0]
            track = self._track_by_id(track_id)
            if not track:
                self.queue.pop(0)
                continue
            break
        else:
            self._refresh_all()
            return

        track = self._track_by_id(self.queue[0])
        assert track is not None
        # snapshot config for this job
        worker = PipelineWorker(self.config, track)
        worker.progress.connect(self._on_job_progress)
        worker.finished.connect(self._on_job_finished)
        worker.failed.connect(self._on_job_failed)
        worker.cancelled.connect(self._on_job_cancelled)
        self.worker_host.start(worker)
        self._refresh_all()

    def _on_job_progress(self, track_id: str, message: str) -> None:
        track = self._track_by_id(track_id)
        if not track:
            return
        track.progress_text = message
        if self.current_track_id == track_id:
            self.stack.setCurrentWidget(self.page_progress)
            self.progress_label.setText(_format_status_text(message))
        self.playlist_panel.set_tracks(self.tracks, self.current_track_id)

    def _cleanup_worker_thread(self) -> None:
        thread = self.worker_host.thread
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self.worker_host.thread = None
        self.worker_host.worker = None

    def _on_job_finished(self, track_id: str) -> None:
        if self.queue and self.queue[0] == track_id:
            self.queue.pop(0)
        track = self._track_by_id(track_id)
        if track:
            track.status = TrackStatus.DONE
            track.progress_text = "翻译完成"
        self._cleanup_worker_thread()
        self._refresh_all()
        self._schedule_project_save()
        self._pump_queue()

    def _on_job_failed(self, track_id: str, error: str) -> None:
        if self.queue and self.queue[0] == track_id:
            self.queue.pop(0)
        track = self._track_by_id(track_id)
        if track:
            track.status = TrackStatus.FAILED
            track.error_message = error
            track.progress_text = f"失败: {error}"
            track.cues = []
        self._cleanup_worker_thread()
        self._refresh_all()
        self._schedule_project_save()
        self._pump_queue()

    def _on_job_cancelled(self, track_id: str) -> None:
        if self.queue and self.queue[0] == track_id:
            self.queue.pop(0)
        track = self._track_by_id(track_id)
        if track:
            track.status = TrackStatus.CANCELLED
            track.progress_text = "已取消"
            track.cues = []
        self._cleanup_worker_thread()
        self._refresh_all()
        self._schedule_project_save()
        self._pump_queue()

    def _on_cancel(self) -> None:
        self.worker_host.cancel()

    # ---- lyrics edit ----
    def _on_cue_edited(self, cue_id: str, source: str, target: str) -> None:
        track = self._current_track()
        if not track:
            return
        for cue in track.cues:
            if cue.id == cue_id:
                cue.source_text = source
                cue.target_text = target
                break
        self._schedule_project_save()

    def _on_cue_timing_edited(self, cue_id: str, start_ms: int, end_ms: int) -> None:
        track = self._current_track()
        if not track:
            return
        for cue in track.cues:
            if cue.id == cue_id:
                cue.start_ms = max(0, int(start_ms))
                cue.end_ms = max(cue.start_ms, int(end_ms))
                break
        self._schedule_project_save()

    def _on_cue_delete(self, cue_id: str) -> None:
        track = self._current_track()
        if not track or self.player.is_playing():
            return
        if len(track.cues) <= 1:
            QMessageBox.information(self, "无法删除", "至少保留一句字幕。")
            return
        reply = QMessageBox.question(
            self,
            "删除字幕",
            "确定删除这一句吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        track.cues = [c for c in track.cues if c.id != cue_id]
        pos = self.player.position()
        self.lyrics.set_cues(track.cues)
        self.lyrics.set_editable(not self.player.is_playing())
        self.lyrics.update_position(pos, scroll=False)
        self._schedule_project_save()

    def _on_cue_insert_after(self, cue_id: str) -> None:
        track = self._current_track()
        if not track or self.player.is_playing():
            return
        idx = next((i for i, c in enumerate(track.cues) if c.id == cue_id), -1)
        if idx < 0:
            return
        cur = track.cues[idx]
        if idx + 1 < len(track.cues):
            nxt = track.cues[idx + 1]
            start_ms = cur.end_ms
            if nxt.start_ms > cur.end_ms:
                end_ms = nxt.start_ms
            else:
                end_ms = start_ms + 1000
        else:
            start_ms = cur.end_ms
            dur = track.duration_ms or max(self.slider.maximum(), start_ms + 2000)
            end_ms = min(dur, start_ms + 2000)
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        new_cue = Cue(
            id=new_cue_id(),
            start_ms=start_ms,
            end_ms=end_ms,
            source_text="",
            target_text="",
        )
        track.cues.insert(idx + 1, new_cue)
        self.lyrics.set_cues(track.cues)
        self.lyrics.set_editable(not self.player.is_playing())
        self.lyrics.highlight_index(idx + 1, scroll=True)
        self._on_cue_seek_requested(start_ms)
        self._schedule_project_save()

    def _on_cue_seek_requested(self, start_ms: int) -> None:
        """字幕区点击/滚动定位 → 同步进度条与播放头。"""
        if self._seek_dragging:
            return
        ms = max(0, int(start_ms))
        self.slider.blockSignals(True)
        if self.slider.maximum() > 0:
            self.slider.setValue(min(ms, self.slider.maximum()))
        else:
            self.slider.setValue(ms)
        self.slider.blockSignals(False)
        self.pos_label.setText(format_time(ms))
        self.player.seek(ms)

    def _on_retranslate_cue(self, cue_id: str) -> None:
        track = self._current_track()
        if not track:
            return
        if not self.config.is_api_configured():
            QMessageBox.warning(self, "无法重译", "请先在设置中配置大模型 API（地址、Key、模型）。")
            return
        if self._retranslate_thread is not None and self._retranslate_thread.isRunning():
            QMessageBox.information(self, "请稍候", "正在重译另一句，请稍后再试。")
            return

        cue = next((c for c in track.cues if c.id == cue_id), None)
        if cue is None:
            QMessageBox.warning(self, "重译失败", "找不到该字幕条目。")
            return
        if not (cue.source_text or "").strip():
            QMessageBox.warning(self, "重译失败", "原文为空，请先填写日文后再翻译。")
            return

        self.lyrics.set_retranslate_busy(True)
        worker = RetranslateWorker(self.config, track, cue_id)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def on_ok(cid: str, text: str) -> None:
            for c in track.cues:
                if c.id == cid:
                    c.target_text = text
                    break
            # 只更新这一句，避免整表重建导致“像没反应”
            self.lyrics.update_cue_target(cid, text)
            self.lyrics.set_retranslate_busy(False)
            self.lyrics.set_editable(not self.player.is_playing())
            self._schedule_project_save()
            thread.quit()

        def on_fail(err: str) -> None:
            self.lyrics.set_retranslate_busy(False)
            QMessageBox.warning(self, "重译失败", err or "未知错误")
            thread.quit()

        def on_thread_finished() -> None:
            self.lyrics.set_retranslate_busy(False)
            self._retranslate_worker = None
            self._retranslate_thread = None

        worker.finished.connect(on_ok)
        worker.failed.connect(on_fail)
        thread.finished.connect(on_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # 必须持有引用，否则 worker 被 GC 后点了也没反应
        self._retranslate_worker = worker
        self._retranslate_thread = thread
        thread.start()

    # ---- export ----
    def _on_export(self) -> None:
        track = self._current_track()
        if not track or track.status != TrackStatus.DONE:
            return
        dlg = ExportDialog(self)
        if not dlg.exec():
            return
        fmt, include_source, include_target = dlg.export_options()
        out_path = Path(track.path).with_name(
            f"{Path(track.path).stem}_"
            f"{'双语' if include_source and include_target else '原文' if include_source else '译文'}"
            f".{fmt}"
        )
        if out_path.exists():
            reply = QMessageBox.question(
                self,
                "覆盖确认",
                f"文件已存在：\n{out_path}\n是否覆盖？",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            result = export_subtitles(
                track.cues,
                track.path,
                fmt=fmt,
                include_source=include_source,
                include_target=include_target,
            )
            QMessageBox.information(self, "导出完成", f"已导出到：\n{result}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
