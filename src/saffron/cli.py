"""Entry point: `saffron file.vv`, `saffron spice://host:port`,
`saffron --connect qemu+ssh://user@host/system [--wait] DOMAIN`.

On macOS, a .vv file double-clicked in Finder (or downloaded from the
Proxmox web UI and opened) doesn't arrive in argv: macOS starts the app
with no arguments and delivers the file as an "open document" event,
which Qt turns into QEvent.FileOpen. Saffron waits briefly for one when
it's started with nothing to open, and opens a new window for any that
arrive while it's running.
"""

import sys

from saffron.target import Target, parse_args

# How long to wait for macOS's open-document event when launched bare.
FILE_OPEN_WAIT_MS = 3000


def _open_target(target: Target, args, windows: list) -> None:
    from saffron.window import ViewerWindow

    if target.spec is not None:
        window = ViewerWindow(target.spec.title or target.spec.describe(), target.spec.fullscreen)
        window.show()
        window.open_spec(target.spec)
    else:
        window = ViewerWindow(target.domain, bool(args and args.full_screen))
        if args is not None and args.title:
            window.setWindowTitle(f"{args.title} - Saffron")
        window.show()
        window.resolve_libvirt(target)
    windows.append(window)


def _self_test() -> int:
    """`saffron --self-test`: prove the native stack loads (PySide6,
    PyGObject, spice-glib) without opening a window. Used by the macOS
    smoke test through the real app launcher."""
    import PySide6.QtWidgets  # noqa: F401 - proves Qt loads

    from saffron.spice.session import SpiceSession

    SpiceSession()
    print("saffron self-test: PySide6, PyGObject and spice-glib OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--self-test"]:
        return _self_test()
    try:
        args, target = parse_args(argv)
    except (ValueError, OSError) as e:  # includes vv_file.VvFileError
        if not (sys.platform == "darwin" and not argv):
            print(f"saffron: {e}", file=sys.stderr)
            return 2
        args, target = None, None  # launched from Finder: wait for a FileOpen event

    from PySide6.QtCore import QEvent, QObject, Qt, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from saffron.window import show_error

    if sys.platform == "darwin":
        # By default Qt on macOS reports Cmd as Ctrl and Ctrl as Meta. A VM
        # needs the physical Ctrl key to arrive as Ctrl (and Cmd as the
        # guest's Super/Windows key), so turn the swap off.
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Saffron")
    app.setApplicationDisplayName("Saffron")
    from pathlib import Path

    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(__file__).with_name("resources") / "saffron.svg")))
    windows: list = []

    def open_file(path: str) -> None:
        try:
            _, file_target = parse_args([path])
        except (ValueError, OSError) as e:
            show_error(None, f"Couldn't open {path}:\n\n{e}")
            return
        _open_target(file_target, None, windows)

    class FileOpenFilter(QObject):
        def eventFilter(self, obj, event):  # noqa: N802 - Qt override
            if event.type() == QEvent.Type.FileOpen:
                open_file(event.file())
                return True
            return False

    file_filter = FileOpenFilter()
    app.installEventFilter(file_filter)

    if target is not None:
        _open_target(target, args, windows)
    else:
        def give_up_waiting() -> None:
            if not windows:
                QMessageBox.information(
                    None, "Saffron",
                    "Open a .vv connection file with Saffron, or run it from virt-connect.",
                )
                app.quit()

        QTimer.singleShot(FILE_OPEN_WAIT_MS, give_up_waiting)

    app.exec()
    return max((w.exit_code for w in windows), default=0)
