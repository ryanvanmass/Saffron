"""SpiceWidget/ViewerWindow against a fake worker -- no spice-glib needed."""

from PySide6.QtCore import QObject, Qt

from saffron.spec import ConnectionSpec
from saffron.spice.signals import SpiceSessionSignals
from saffron.widget import SpiceWidget


class FakeWorker(QObject):
    def __init__(self):
        super().__init__()
        self.signals = SpiceSessionSignals()
        self.keys = []
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def send_key_scancode(self, code, extended, down):
        self.keys.append((code, extended, down))

    def send_clipboard_text(self, text):
        pass

    def send_resize(self, w, h):
        pass

    def send_mouse_move(self, x, y):
        pass


SPEC = ConnectionSpec(host="h", port=5900)


def test_ctrl_alt_del_presses_then_releases_in_reverse(qtbot):
    worker = FakeWorker()
    w = SpiceWidget(SPEC, worker=worker)
    qtbot.addWidget(w)
    w.send_key_combo([Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Delete])
    assert worker.keys == [
        (0x1D, False, True), (0x38, False, True), (0x53, True, True),
        (0x53, True, False), (0x38, False, False), (0x1D, False, False),
    ]


def test_first_frame_reports_resolution(qtbot):
    worker = FakeWorker()
    w = SpiceWidget(SPEC, worker=worker)
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.resolution_changed) as blocker:
        worker.signals.frame_ready.emit(b"\x00" * 4 * 8 * 2, 0, 2, 8, 2, 32)
    assert blocker.args == [8, 2]
    assert w.sizeHint().toTuple() == (8, 2)


def test_error_is_reported(qtbot):
    worker = FakeWorker()
    w = SpiceWidget(SPEC, worker=worker)
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.failed) as blocker:
        worker.signals.error.emit("Authentication failed")
    assert blocker.args == ["Authentication failed"]


def test_close_session_stops_worker(qtbot):
    worker = FakeWorker()
    w = SpiceWidget(SPEC, worker=worker)
    qtbot.addWidget(w)
    w.close_session()
    assert worker.started and worker.stopped
