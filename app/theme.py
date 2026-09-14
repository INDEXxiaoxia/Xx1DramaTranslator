"""雾纱蓝粉主题 — 低饱和浅蓝粉色系。"""

from __future__ import annotations


# UI 控件用黑体族；正文/原文译文用宋体族（Windows 常见回退）
FONT_UI = "Microsoft YaHei UI"
FONT_UI_FALLBACKS = ("Microsoft YaHei UI", "SimHei", "Microsoft YaHei", "Segoe UI")
FONT_CONTENT = "SimSun"
FONT_CONTENT_CSS = "'SimSun','NSimSun','宋体','STSong'"
FONT_UI_CSS = "'Microsoft YaHei UI','SimHei','Microsoft YaHei','Segoe UI'"
FONT_MONO_CSS = "'Cascadia Mono','Consolas','Microsoft YaHei UI'"


class Colors:
    """命名色板：雾纱浅蓝底 + 柔粉强调，低饱和易读。"""

    paper = "#F6F5FA"
    surface = "#EEEAF4"
    raised = "#FFFFFF"
    ink = "#2E2A36"
    ink_muted = "#6A6478"
    ink_faint = "#9A94A8"
    line = "#D8D4E2"
    line_soft = "#E8E4F0"
    accent = "#9AABD0"
    accent_soft = "#EDE6F2"
    accent_deep = "#6E7FA8"
    accent_glow = "#D9D0E8"
    busy = "#8A9BB5"
    busy_soft = "#E4E8F0"
    ok = "#6E9B8F"
    ok_soft = "#E2EEE9"
    err = "#C08090"
    err_soft = "#F5E6EA"
    warn = "#B89A78"


def app_stylesheet() -> str:
    c = Colors
    return f"""
/* —— 全局底 —— */
QMainWindow, QDialog {{
    background: {c.paper};
    color: {c.ink};
}}
QWidget {{
    color: {c.ink};
    font-family: {FONT_UI_CSS};
    font-size: 13px;
}}
QToolTip {{
    background: {c.ink};
    color: {c.raised};
    border: none;
    padding: 6px 10px;
    border-radius: 6px;
    font-family: {FONT_UI_CSS};
}}

/* —— 输入 —— */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {c.raised};
    color: {c.ink};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: {c.accent_soft};
    selection-color: {c.ink};
    font-family: {FONT_UI_CSS};
}}
QLineEdit#ContentEdit, QPlainTextEdit#ContentEdit {{
    font-family: {FONT_CONTENT_CSS};
    font-size: 14px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c.accent};
}}
QLineEdit:read-only {{
    background: {c.surface};
    color: {c.ink_muted};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {c.raised};
    color: {c.ink};
    border: 1px solid {c.line};
    selection-background-color: {c.accent_soft};
    selection-color: {c.ink};
    outline: none;
    font-family: {FONT_UI_CSS};
}}

/* —— 按钮 —— */
QPushButton {{
    background: {c.surface};
    color: {c.ink};
    border: 1px solid {c.line};
    border-radius: 9px;
    padding: 6px 14px;
    font-family: {FONT_UI_CSS};
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {c.accent_soft};
    border-color: {c.accent};
    color: {c.accent_deep};
}}
QPushButton:pressed {{
    background: {c.accent_glow};
}}
QPushButton:disabled {{
    background: {c.line_soft};
    color: {c.ink_faint};
    border-color: {c.line_soft};
}}
QPushButton:focus {{
    outline: none;
    border: 1px solid {c.accent};
}}

QPushButton#PrimaryButton {{
    background: {c.accent_deep};
    color: {c.raised};
    border: 1px solid {c.accent_deep};
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background: #5A6B96;
    color: {c.raised};
    border-color: #5A6B96;
}}
QPushButton#PrimaryButton:pressed {{
    background: #4C5C86;
    color: {c.raised};
}}
QPushButton#PrimaryButton:disabled {{
    background: {c.line};
    color: {c.ink_faint};
    border-color: {c.line};
}}

QPushButton#DangerButton {{
    background: {c.err_soft};
    color: {c.err};
    border: 1px solid #E5CDD4;
}}
QPushButton#DangerButton:hover {{
    background: #EDD5DC;
    color: #A86878;
    border-color: {c.err};
}}

QPushButton#GhostButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {c.ink_muted};
}}
QPushButton#GhostButton:hover {{
    background: {c.surface};
    border-color: {c.line};
    color: {c.ink};
}}

QPushButton#IconButton {{
    background: {c.surface};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 0;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#IconButton:hover {{
    background: {c.accent_soft};
    border-color: {c.accent};
}}
QPushButton#IconButton:disabled {{
    background: {c.line_soft};
    border-color: {c.line_soft};
}}

QPushButton#IconQuiet {{
    background: {c.raised};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 0;
    min-width: 28px;
    min-height: 28px;
}}
QPushButton#IconQuiet:hover {{
    background: {c.accent_soft};
    border-color: {c.accent};
}}
QPushButton#IconQuiet:disabled {{
    background: {c.line_soft};
    border-color: {c.line_soft};
}}

QPushButton#IconDanger {{
    background: {c.raised};
    border: 1px solid #E5CDD4;
    border-radius: 8px;
    padding: 0;
    min-width: 28px;
    min-height: 28px;
}}
QPushButton#IconDanger:hover {{
    background: {c.err_soft};
    border-color: {c.err};
}}
QPushButton#IconDanger:disabled {{
    background: {c.line_soft};
    border-color: {c.line_soft};
}}

/* —— 滑条 —— */
QSlider::groove:horizontal {{
    height: 6px;
    background: {c.line};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 3px;
}}
QSlider::add-page:horizontal {{
    background: {c.line_soft};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    background: {c.raised};
    border: 2px solid {c.accent};
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    border-color: {c.accent_deep};
    background: {c.accent_soft};
}}
QSlider::groove:horizontal:disabled {{
    background: {c.line_soft};
}}
QSlider::handle:horizontal:disabled {{
    border-color: {c.line};
    background: {c.surface};
}}

/* —— 分组 / 列表 / 菜单 —— */
QGroupBox {{
    background: {c.raised};
    border: 1px solid {c.line_soft};
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-family: {FONT_UI_CSS};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {c.ink_muted};
    font-size: 12px;
    font-weight: 600;
}}
QMenu {{
    background: {c.raised};
    color: {c.ink};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 4px;
    font-family: {FONT_UI_CSS};
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {c.accent_soft};
    color: {c.accent_deep};
}}
QCheckBox {{
    spacing: 8px;
    color: {c.ink};
    font-family: {FONT_UI_CSS};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c.line};
    border-radius: 4px;
    background: {c.raised};
}}
QCheckBox::indicator:checked {{
    background: {c.accent};
    border-color: {c.accent_deep};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c.line};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.ink_faint};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c.line};
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QLabel#HintLabel {{
    color: {c.ink_faint};
    font-size: 11px;
    font-family: {FONT_UI_CSS};
}}
QLabel#StatusOk {{
    color: {c.ok};
}}
QLabel#StatusErr {{
    color: {c.err};
}}
QLabel#StatusBusy {{
    color: {c.busy};
}}
"""


def cue_row_style(active: bool) -> str:
    c = Colors
    if active:
        return (
            "#CueRow {"
            f"  background: {c.accent_soft};"
            f"  border: 1px solid {c.accent_glow};"
            "  border-radius: 12px;"
            "}"
        )
    return (
        "#CueRow {"
        f"  background: {c.raised};"
        f"  border: 1px solid {c.line_soft};"
        "  border-radius: 12px;"
        "}"
    )


def controls_style() -> str:
    c = Colors
    return (
        "#Controls {"
        f"  background: {c.raised};"
        f"  border: 1px solid {c.line_soft};"
        "  border-radius: 16px;"
        "}"
        "#Controls QLabel#FileName {"
        "  font-weight: 600;"
        f"  color: {c.ink};"
        "  font-size: 13px;"
        f"  font-family: {FONT_UI_CSS};"
        "}"
        "#Controls QLabel#TimeLabel {"
        f"  color: {c.ink_muted};"
        "  font-size: 12px;"
        f"  font-family: {FONT_MONO_CSS};"
        "  min-width: 42px;"
        "}"
    )


def playlist_style() -> str:
    c = Colors
    return (
        "#PlaylistPanel {"
        f"  background: {c.surface};"
        f"  border-left: 1px solid {c.line_soft};"
        "}"
        "#PlaylistTitle {"
        "  font-weight: 600;"
        "  font-size: 13px;"
        f"  color: {c.ink_muted};"
        f"  font-family: {FONT_UI_CSS};"
        "}"
        "#PlaylistPanel QListWidget {"
        "  background: transparent;"
        "  border: none;"
        "  outline: none;"
        "  padding: 0;"
        "}"
        "#PlaylistPanel QListWidget::item {"
        "  background: transparent;"
        "  border: none;"
        "  padding: 0;"
        "  margin: 0 0 4px 0;"
        "}"
        "#PlaylistPanel QListWidget::item:selected,"
        "#PlaylistPanel QListWidget::item:hover {"
        "  background: transparent;"
        "}"
        "#PlaylistRow, #PlaylistRowSelected {"
        "  border: none;"
        "  border-radius: 10px;"
        "}"
        "#PlaylistRow {"
        "  background: transparent;"
        "}"
        "#PlaylistRowSelected {"
        f"  background: {c.accent_soft};"
        "}"
        "#TrackName {"
        f"  color: {c.ink};"
        "  background: transparent;"
        "  border: none;"
        "}"
        "#TrackStatus {"
        "  background: transparent;"
        "  border: none;"
        "}"
        "QPushButton#RemoveTrack {"
        "  border: none;"
        f"  color: {c.ink_faint};"
        "  font-size: 14px;"
        "  background: transparent;"
        "  border-radius: 6px;"
        "  padding: 0;"
        "}"
        "QPushButton#RemoveTrack:hover {"
        f"  color: {c.err};"
        f"  background: {c.err_soft};"
        "}"
        "QPushButton#RemoveTrack:disabled {"
        f"  color: {c.line};"
        "  background: transparent;"
        "}"
    )


def status_page_style() -> str:
    c = Colors
    return (
        "#StatusCard {"
        f"  background: {c.raised};"
        f"  border: 1px dashed {c.line};"
        "  border-radius: 20px;"
        "}"
        "#StatusEyebrow {"
        f"  color: {c.accent};"
        "  font-size: 12px;"
        "  font-weight: 600;"
        f"  font-family: {FONT_UI_CSS};"
        "}"
        "#StatusTitle {"
        f"  color: {c.ink};"
        "  font-size: 18px;"
        "  font-weight: 600;"
        f"  font-family: {FONT_UI_CSS};"
        "}"
        "#StatusBody {"
        f"  color: {c.ink_muted};"
        "  font-size: 13px;"
        f"  font-family: {FONT_UI_CSS};"
        "}"
        "#DropZone {"
        f"  background: {c.raised};"
        f"  border: 1.5px dashed {c.accent};"
        "  border-radius: 24px;"
        "}"
        "#DropZone QLabel {"
        f"  color: {c.ink_muted};"
        "}"
    )
