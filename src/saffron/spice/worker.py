"""Qt-signal wrapper around runner.SpiceSessionRunner -- the runner's
callbacks fire on its GLib loop thread, so each .emit() crosses back to the
Qt thread via a queued signal emission. Input methods are the runner's own
(already safe to call from the Qt thread via GLib.idle_add).
Carried over from IT Toolbox's core/spice/spice_session_worker.py.
"""

from saffron.spec import ConnectionSpec
from saffron.spice.runner import SpiceSessionRunner
from saffron.spice.signals import SpiceSessionSignals

__all__ = ["SpiceSessionSignals", "SpiceSessionWorker"]


class SpiceSessionWorker(SpiceSessionRunner):
    def __init__(self, spec: ConnectionSpec) -> None:
        self.signals = SpiceSessionSignals()
        super().__init__(
            spec,
            on_frame=self.signals.frame_ready.emit,
            on_connected=self.signals.connected.emit,
            on_agent_connected=self.signals.agent_connected.emit,
            on_error=self.signals.error.emit,
            on_disconnected=self.signals.disconnected.emit,
        )
