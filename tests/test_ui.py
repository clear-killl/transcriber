import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
import pytest

from transcriber.ui import MainWindow, STYLE


@pytest.fixture(autouse=True)
def no_hardware_probe(monkeypatch):
    monkeypatch.setattr("transcriber.vulkan.list_devices", lambda: [])


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def test_drop_queue_duplicates_and_removal(app, tmp_path):
    source = tmp_path / "Большая запись.mkv"
    source.write_bytes(b"media")
    window = MainWindow(tmp_path, tmp_path / "data")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.drop.dropEvent(event)
    window.add_files([str(source), str(tmp_path)])
    assert window.paths == [source]
    assert window.table.rowCount() == 1 and window.start_button.isEnabled()
    window.table.selectRow(0)
    window.remove_selected()
    assert not window.paths and not window.start_button.isEnabled()
    window.close()


def test_preferences_roundtrip(app, tmp_path):
    window = MainWindow(tmp_path, tmp_path / "data")
    window.quality.setCurrentIndex(2)
    window.timestamps.setChecked(False)
    window.close()
    restored = MainWindow(tmp_path, tmp_path / "data")
    assert restored.quality.currentData() == "medium"
    assert not restored.timestamps.isChecked()
    restored.close()


def test_amd_and_intel_gpu_choices_restore_preference(app, tmp_path):
    window = MainWindow(tmp_path, tmp_path / "data")
    window.preferences["device"] = "vulkan:1"
    window.show_gpu_devices([
        {"index": 0, "name": "AMD Radeon RX 6700 XT"},
        {"index": 1, "name": "Intel(R) Iris(R) Xe Graphics"},
    ], "")
    assert window.device.currentData() == "vulkan:1"
    assert "Intel" in window.device.currentText()
    assert window.device.findData("vulkan:0") >= 0
    window.close()
