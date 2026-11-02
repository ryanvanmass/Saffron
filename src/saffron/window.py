"""Saffron's main window: one SPICE display plus the handful of controls a
VM viewer needs (full screen, send key, size to guest)."""

import os
import sys

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox

from saffron import __version__
from saffron.spec import ConnectionSpec

# Shift+F11 / Shift+F12 match virt-viewer's defaults, and leave plain F11
# free to reach the guest.
FULLSCREEN_SHORTCUT = "Shift+F11"

SEND_KEYS = [
    ("Ctrl+Alt+Del", [Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Delete]),
    ("Ctrl+Alt+Backspace", [Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Backspace]),
] + [
    (f"Ctrl+Alt+F{n}", [Qt.Key.Key_Control, Qt.Key.Key_Alt, getattr(Qt.Key, f"Key_F{n}")])
    for n in range(1, 13)
]


def show_error(parent, message: str) -> None:
    """An error dialog, or plain stderr when SAFFRON_NO_DIALOGS=1 (headless
    CI, scripts) so nothing blocks waiting for a click."""
    if os.environ.get("SAFFRON_NO_DIALOGS") == "1":
        print(f"saffron: {message}", file=sys.stderr)
    else:
        QMessageBox.critical(parent, "Saffron", message)


class LibvirtResolver(QThread):
    """Looks up a libvirt domain's SPICE display (and opens the SSH tunnel)
    off the UI thread, since --wait can block until the VM starts."""

    resolved = Signal(object, object)  # ConnectionSpec, SshTunnel | None
    failed = Signal(str)

    def __init__(self, target, parent=None) -> None:
        super().__init__(parent)
        self._target = target

    def run(self) -> None:
        from saffron import libvirt
        from saffron.ssh_tunnel import SshTunnelError

        try:
            graphics = libvirt.wait_for_graphics(self._target.libvirt_uri, self._target.domain, wait=self._target.wait)
            spec, tunnel = libvirt.build_spec(self._target.libvirt_uri, graphics, ca_file=self._target.ca_file)
        except (libvirt.LibvirtError, SshTunnelError, OSError, ValueError) as e:
            self.failed.emit(str(e))
            return
        self.resolved.emit(spec, tunnel)


class ViewerWindow(QMainWindow):
    def __init__(self, title: str, fullscreen: bool = False) -> None:
        super().__init__()
        self._base_title = title
        self._start_fullscreen = fullscreen
        self._display = None
        self._tunnel = None
        self._resolver = None
        self._sized_to_guest = False
        self.exit_code = 0
        self.setWindowTitle(f"{title} - Saffron")
        self._status = QLabel("Connecting…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(self._status)
        self.resize(1024, 768)
        self._build_menus()

    # --- menus ------------------------------------------------------------

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view = bar.addMenu("&View")
        self._fullscreen_action = QAction("&Full Screen", self, checkable=True)
        self._fullscreen_action.setShortcut(QKeySequence(FULLSCREEN_SHORTCUT))
        self._fullscreen_action.toggled.connect(self._set_fullscreen)
        view.addAction(self._fullscreen_action)
        fit = QAction("&Resize to Guest", self)
        fit.triggered.connect(self._size_to_guest)
        view.addAction(fit)

        self._send_menu = bar.addMenu("&Send Key")
        for label, keys in SEND_KEYS:
            action = QAction(label, self)
            action.triggered.connect(lambda _=False, k=keys: self._send_combo(k))
            self._send_menu.addAction(action)
        self._send_menu.setEnabled(False)

        help_menu = bar.addMenu("&Help")
        about = QAction("&About Saffron", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(
            lambda: QMessageBox.about(self, "About Saffron", f"Saffron {__version__}\nA SPICE viewer built on IT Toolbox's SPICE client.")
        )
        help_menu.addAction(about)

    # --- connection lifecycle ---------------------------------------------

    def resolve_libvirt(self, target) -> None:
        self._status.setText(f"Waiting for {target.domain} to start…" if target.wait else f"Looking up {target.domain}…")
        self._resolver = LibvirtResolver(target, self)
        self._resolver.resolved.connect(self._on_resolved)
        self._resolver.failed.connect(self._fail)
        self._resolver.start()

    def _on_resolved(self, spec: ConnectionSpec, tunnel) -> None:
        self._tunnel = tunnel
        self.open_spec(spec)

    def open_spec(self, spec: ConnectionSpec) -> None:
        from saffron.widget import SpiceWidget

        if spec.title:
            self._base_title = spec.title
            self.setWindowTitle(f"{spec.title} - Saffron")
        self._display = SpiceWidget(spec)
        self._display.connected.connect(self._on_connected)
        self._display.resolution_changed.connect(self._on_resolution)
        self._display.failed.connect(self._fail)
        self._display.finished.connect(self._on_finished)
        self.setCentralWidget(self._display)
        self._display.setFocus()
        if spec.fullscreen or self._start_fullscreen:
            self._fullscreen_action.setChecked(True)

    def _on_connected(self) -> None:
        self._send_menu.setEnabled(True)

    def _on_resolution(self, width: int, height: int) -> None:
        if not self._sized_to_guest and not self.isFullScreen():
            self._sized_to_guest = True
            self._size_to_guest()

    def _size_to_guest(self) -> None:
        """Size the window so the guest shows 1:1, capped to the screen."""
        if self._display is None or self.isFullScreen():
            return
        guest = self._display.sizeHint()
        chrome_h = self.height() - self.centralWidget().height()
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        self.resize(min(guest.width(), screen.width()), min(guest.height() + chrome_h, screen.height()))

    def _set_fullscreen(self, on: bool) -> None:
        if on:
            self.showFullScreen()
        else:
            self.showNormal()

    def _send_combo(self, keys) -> None:
        if self._display is not None:
            self._display.send_key_combo(keys)
            self._display.setFocus()

    def _fail(self, message: str) -> None:
        self.exit_code = 1
        show_error(self, f"Couldn't connect to {self._base_title}:\n\n{message}")
        self.close()

    def _on_finished(self) -> None:
        # The guest went away (shut down, or the server closed the session):
        # like remote-viewer, close instead of leaving a dead window open.
        if self.exit_code == 0:
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._display is not None:
            self._display.close_session()
        if self._tunnel is not None:
            self._tunnel.stop()
            self._tunnel = None
        super().closeEvent(event)
