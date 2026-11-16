"""Render the real Qt UI offscreen, without opening a window on the desktop."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from transcriber.ui import MainWindow, STYLE

root = Path(__file__).resolve().parents[1]
app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeuib.ttf")
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow(root, root / "data" / "preview")
window.show()
app.processEvents()
target = root / "data" / "ui-preview.png"
target.parent.mkdir(parents=True, exist_ok=True)
window.grab().save(str(target))
print(target)
window.close()
