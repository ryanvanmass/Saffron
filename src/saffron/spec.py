"""What Saffron needs to open one SPICE connection, however it was described
(a .vv file, a libvirt domain, or plain host/port arguments)."""

from dataclasses import dataclass, field


@dataclass
class ConnectionSpec:
    host: str
    port: int | None = None  # plaintext port
    tls_port: int | None = None
    password: str = ""
    ca_pem: str | None = None  # CA certificate(s), PEM text, for TLS
    host_subject: str | None = None  # expected server cert subject, e.g. "OU=PVE Cluster Node,O=Proxmox Virtual Environment,CN=pve"
    proxy: str | None = None  # HTTP CONNECT proxy, e.g. "http://pve.example:3128" (Proxmox spiceproxy)
    secure_channels: list[str] = field(default_factory=list)  # channels that must use TLS, e.g. ["main", "inputs"]
    title: str | None = None
    fullscreen: bool = False
    # Keys virt-viewer would bind; recorded for the window's menu labels.
    release_cursor: str | None = None
    toggle_fullscreen: str | None = None

    def validate(self) -> None:
        if not self.host:
            raise ValueError("no SPICE host given")
        if self.port is None and self.tls_port is None:
            raise ValueError("no SPICE port or tls-port given")

    def describe(self) -> str:
        port = self.tls_port if self.port is None else self.port
        return f"{self.host}:{port}"
