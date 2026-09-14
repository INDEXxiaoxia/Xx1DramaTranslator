from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Allow running as script: python main.py
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", message=".*urllib3.*chardet.*charset_normalizer.*")

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Xx1DramaTranslator")
    app.setOrganizationName("Xx1")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
