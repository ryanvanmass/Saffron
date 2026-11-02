"""SSH local-port-forward to reach a libvirt VM's SPICE port over qemu+ssh://.

libvirt binds a VM's SPICE server to 127.0.0.1 on the host by default.
virt-viewer reaches it by tunnelling through the same SSH connection virsh
uses; Saffron connects to the SPICE port itself, so it opens that tunnel
here. Adapted from IT Toolbox's core/ssh_tunnel.py + core/qemu_tunnel.py
(key/agent auth only: virt-connect already requires passwordless SSH).
"""

import socket
import subprocess
import time
from urllib.parse import urlsplit

READY_POLL_INTERVAL_SEC = 0.1


class SshTunnelError(Exception):
    pass


def is_local_uri(uri: str) -> bool:
    """True for a local libvirt URI ("qemu:///system", "qemu:///session"),
    where the SPICE port is directly reachable without a tunnel."""
    parsed = urlsplit(uri)
    return parsed.scheme == "qemu" and not parsed.hostname


def parse_ssh_target(uri: str) -> tuple[str, int | None]:
    """"qemu+ssh://alice@lab:2222/system" -> ("alice@lab", 2222)."""
    parsed = urlsplit(uri)
    if parsed.scheme != "qemu+ssh":
        raise SshTunnelError(f"not an SSH-transport libvirt URI: {uri!r}")
    if not parsed.hostname:
        raise SshTunnelError(f"no host in libvirt URI: {uri!r}")
    target = f"{parsed.username}@{parsed.hostname}" if parsed.username else parsed.hostname
    return target, parsed.port


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _can_connect(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


class SshTunnel:
    """`ssh -N -L local:dest_host:dest_port target`, held open as a subprocess."""

    def __init__(self, target: str, dest_host: str, dest_port: int, *, ssh_port: int | None = None) -> None:
        self._target = target
        self._ssh_port = ssh_port
        self._dest_host = dest_host
        self._dest_port = dest_port
        self._process: subprocess.Popen[str] | None = None
        self.port: int | None = None

    @classmethod
    def for_libvirt_uri(cls, uri: str, remote_port: int, dest_host: str = "127.0.0.1") -> "SshTunnel":
        target, ssh_port = parse_ssh_target(uri)
        return cls(target, dest_host, remote_port, ssh_port=ssh_port)

    def start(self, ready_timeout: float = 10) -> int:
        """Spawn ssh and block until the local port accepts connections."""
        self.port = _free_local_port()
        cmd = [
            "ssh", "-N",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "BatchMode=yes",  # never hang on a password prompt nobody can see
            "-L", f"{self.port}:{self._dest_host}:{self._dest_port}",
        ]
        if self._ssh_port:
            cmd += ["-p", str(self._ssh_port)]
        cmd.append(self._target)
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
        except FileNotFoundError as e:
            raise SshTunnelError("ssh not found: install an OpenSSH client") from e

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                raise SshTunnelError(f"ssh tunnel to {self._target} exited: {stderr.strip()}")
            if _can_connect(self.port):
                return self.port
            time.sleep(READY_POLL_INTERVAL_SEC)
        self.stop()
        raise SshTunnelError(f"timed out waiting for ssh tunnel to {self._target}")

    def stop(self, timeout: float = 5) -> None:
        """Safe to call more than once, or after a failed start()."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None
