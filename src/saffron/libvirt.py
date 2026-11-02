"""Find a libvirt domain's SPICE display via `virsh`, like
`remote-viewer --connect URI DOMAIN` / `virt-viewer --connect URI DOMAIN`.

Shells out to virsh (as virt-connect and IT Toolbox already do) instead of
linking libvirt, so the only native dependency stays spice-glib.
"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlsplit
import subprocess

from saffron.spec import ConnectionSpec
from saffron.ssh_tunnel import SshTunnel, is_local_uri

VIRSH_TIMEOUT = 15
_ANY_ADDRESS = {"", "0.0.0.0", "::", "[::]"}


class LibvirtError(Exception):
    pass


@dataclass
class SpiceGraphics:
    port: int | None
    tls_port: int | None
    listen: str
    password: str


def _virsh(uri: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["virsh", "-c", uri, *args], capture_output=True, text=True, timeout=VIRSH_TIMEOUT
        )
    except FileNotFoundError as e:
        raise LibvirtError("virsh is not installed or not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise LibvirtError(f"timed out talking to {uri}") from e
    if proc.returncode != 0:
        raise LibvirtError((proc.stderr or f"virsh {args[0]} failed").strip())
    return proc.stdout


def _port(value: str | None) -> int | None:
    if value is None or value in ("", "-1"):
        return None
    return int(value)


def parse_spice_graphics(xml_text: str) -> SpiceGraphics | None:
    """The domain's first SPICE <graphics>, or None if it has none.
    Ports are None until the VM is running (autoport assigns them at start)."""
    root = ET.fromstring(xml_text)  # noqa: S314 - libvirt's own output
    g = root.find("./devices/graphics[@type='spice']")
    if g is None:
        return None
    listen = g.get("listen")
    if listen is None:
        el = g.find("./listen[@type='address']")
        listen = el.get("address", "") if el is not None else ""
    return SpiceGraphics(
        port=_port(g.get("port")),
        tls_port=_port(g.get("tlsPort")),
        listen=listen or "",
        password=g.get("passwd", ""),
    )


def _dumpxml(uri: str, domain: str) -> str:
    # --security-info includes the SPICE password, when the caller is
    # allowed to see it; fall back to the plain dump when it isn't.
    try:
        return _virsh(uri, "dumpxml", "--security-info", domain)
    except LibvirtError:
        return _virsh(uri, "dumpxml", domain)


def wait_for_graphics(uri: str, domain: str, *, wait: bool, timeout: float | None = None,
                      poll: float = 1.0) -> SpiceGraphics:
    """Look up the domain's SPICE graphics. With wait=True (remote-viewer's
    --wait), keep polling until the domain exists and is running."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            graphics = parse_spice_graphics(_dumpxml(uri, domain))
            if graphics is None:
                raise LibvirtError(f"{domain} has no SPICE display configured")
            if graphics.port is not None or graphics.tls_port is not None:
                return graphics
            problem = LibvirtError(f"{domain} is not running")
        except LibvirtError as e:
            if "no SPICE display" in str(e):
                raise
            problem = e
        if not wait or (deadline is not None and time.monotonic() > deadline):
            raise problem
        time.sleep(poll)


def build_spec(uri: str, graphics: SpiceGraphics, *, ca_file: str | None = None
               ) -> tuple[ConnectionSpec, SshTunnel | None]:
    """Turn the domain's graphics into something to connect to, opening an
    SSH tunnel for qemu+ssh:// URIs. The caller stops the returned tunnel."""
    ca_pem = None
    if ca_file:
        with open(ca_file, encoding="utf-8") as f:
            ca_pem = f.read()
    use_tls = graphics.port is None
    if use_tls and ca_pem is None:
        raise LibvirtError(
            "this VM only offers a TLS SPICE port; pass --spice-ca-file with the host's SPICE CA certificate"
        )
    remote_port = graphics.tls_port if use_tls else graphics.port
    parsed = urlsplit(uri)

    tunnel = None
    if is_local_uri(uri):
        host = "127.0.0.1" if graphics.listen in _ANY_ADDRESS else graphics.listen
    elif parsed.scheme.endswith("+ssh"):
        dest = "127.0.0.1" if graphics.listen in _ANY_ADDRESS else graphics.listen
        tunnel = SshTunnel.for_libvirt_uri(uri, remote_port, dest_host=dest)
        remote_port = tunnel.start()
        host = "127.0.0.1"
    else:  # qemu+tcp://, qemu+tls://: SPICE must be listening on a reachable address
        host = parsed.hostname if graphics.listen in _ANY_ADDRESS else graphics.listen
        if graphics.listen.startswith("127.") or graphics.listen == "::1":
            raise LibvirtError(
                f"the VM's SPICE server only listens on {graphics.listen} on the host; use a qemu+ssh:// URI"
            )

    spec = ConnectionSpec(
        host=host,
        port=None if use_tls else remote_port,
        tls_port=remote_port if use_tls else None,
        password=graphics.password,
        ca_pem=ca_pem,
    )
    return spec, tunnel
