"""Run a real Qt worker, then save a screenshot and check the resulting Word."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HF_HUB_OFFLINE"] = "1"
from pathlib import Path
import sys
import shutil
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from transcriber.ui import MainWindow, STYLE

root = Path(__file__).resolve().parents[1]
app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeuib.ttf")
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow(root, root / "data")
window.save_preferences = lambda: None
window.device.setCurrentIndex(window.device.findData(sys.argv[1] if len(sys.argv) > 1 else "cpu"))
window.quality.setCurrentIndex(window.quality.findData("small"))
window.output_dir = root / "data" / "gui-smoke-output"
window.folder.setText(str(window.output_dir))
source = root / "data" / "gui-sample.wav"
shutil.copyfile(root / "data" / "russian-sample.wav", source)
window.add_files([str(source)])
window.show()
window.start()


def finish():
    if window.is_busy():
        return
    timer.stop()
    assert not window.errors, window.errors
    assert len(window.results) == 1, window.results
    target = next(iter(window.results.values()))
    text = "\n".join(p.text for p in Document(target).paragraphs)
    assert "Здравствуйте" in text
    assert "пятницу" in text
    window.grab().save(str(root / "data" / "ui-completed.png"))
    print(text)
    window.close()
    app.quit()


timer = QTimer()
timer.timeout.connect(finish)
timer.start(200)
# Avoid a stuck test if model inference never returns. No timeout on user jobs.
QTimer.singleShot(180000, lambda: os._exit(2))
raise SystemExit(app.exec())
