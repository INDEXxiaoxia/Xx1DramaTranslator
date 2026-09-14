from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Allow running as script: python main.py
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", message=".*urllib3.*chardet.*charset_normalizer.*")

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.theme import FONT_UI_FALLBACKS, app_stylesheet


def _app_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets" / "app.ico"
        if bundled.exists():
            return bundled
        return Path(sys.executable)
    return ROOT / "assets" / "app.ico"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Xx1DramaTranslator")
    app.setOrganizationName("Xx1")
    for family in FONT_UI_FALLBACKS:
        font = QFont(family, 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        if font.exactMatch() or family == "Segoe UI":
            app.setFont(font)
            break
    app.setStyleSheet(app_stylesheet())
    icon = QIcon(str(_app_icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
