"""End-to-end tests against a real QEMU SPICE server: plain, and a
Proxmox-style TLS + CA + host-subject + HTTP CONNECT proxy + ticket .vv.

Opt-in (SAFFRON_LIVE=1) and need qemu-system-x86_64 with SPICE, openssl
and spice-glib's GObject-Introspection typelib. CI's Linux job runs them.
"""

import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SAFFRON_LIVE") != "1" or not shutil.which("qemu-system-x86_64"),
    reason="set SAFFRON_LIVE=1 with qemu-system-x86_64 installed",
)

SUBJECT = "/O=Proxmox Virtual Environment/OU=PVE Cluster Node/CN=pve.test"
HOST_SUBJECT = "O=Proxmox Virtual Environment,OU=PVE Cluster Node,CN=pve.test"
TICKET = "s3cret-ticket"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} never opened")


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    d = tmp_path_factory.mktemp("pki")
    run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)  # noqa: E731
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca-key.pem",
        "-out", "ca-cert.pem", "-days", "2", "-subj", "/CN=Saffron Test CA")
    run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server-key.pem",
        "-out", "server.csr", "-subj", SUBJECT)
    run("openssl", "x509", "-req", "-in", "server.csr", "-CA", "ca-cert.pem", "-CAkey", "ca-key.pem",
        "-CAcreateserial", "-out", "server-cert.pem", "-days", "2")
    return d


@pytest.fixture(scope="module")
def qemu(pki):
    plain, tls = _free_port(), _free_port()
    proc = subprocess.Popen([
        "qemu-system-x86_64", "-machine", "pc", "-m", "64", "-display", "none", "-vga", "qxl",
        "-object", f"secret,id=sp0,data={TICKET}",
        "-spice", f"port={plain},tls-port={tls},x509-dir={pki},password-secret=sp0",
    ])
    _wait_port(plain)
    _wait_port(tls)
    yield plain, tls
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def connect_proxy():
    """Stands in for Proxmox's spiceproxy: any CONNECT target host is
    mapped to 127.0.0.1, like the pvespiceproxy:... ticket host names."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    seen = []

    def pipe(a, b):
        try:
            while data := a.recv(65536):
                b.sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle(c):
        req = b""
        while b"\r\n\r\n" not in req:
            req += c.recv(4096)
        hostport = req.split(b"\r\n")[0].split()[1].decode()
        seen.append(hostport)
        up = socket.create_connection(("127.0.0.1", int(hostport.rsplit(":", 1)[1])))
        c.sendall(b"HTTP/1.0 200 Connection established\r\n\r\n")
        threading.Thread(target=pipe, args=(c, up), daemon=True).start()
        pipe(up, c)

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(c,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}", seen
    srv.close()


def _capture(spec, timeout=15):
    """Connect through the real runner and return the first frame's size, or raise with the error."""
    from saffron.spice.runner import SpiceSessionRunner

    result, done = {}, threading.Event()

    def on_frame(pixels, top, height, w, h, stride):
        result["size"] = (w, h)
        done.set()

    def on_error(msg):
        result["error"] = msg
        done.set()

    runner = SpiceSessionRunner(spec, on_frame=on_frame, on_error=on_error)
    runner.start()
    try:
        assert done.wait(timeout), "no frame or error in time"
    finally:
        runner.stop()
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["size"]


def _vv(pki, tls_port, proxy, password=TICKET):
    ca = (pki / "ca-cert.pem").read_text().strip().replace("\n", "\\n")
    return (
        "[virt-viewer]\ntype=spice\nhost=pvespiceproxy:abcd:100:pve::beef\n"
        f"tls-port={tls_port}\npassword={password}\nca={ca}\nhost-subject={HOST_SUBJECT}\n"
        f"proxy={proxy}\nsecure-channels=main;inputs;cursor;display\ndelete-this-file=1\n"
    )


def test_plain_connection(qemu):
    from saffron.spec import ConnectionSpec

    w, h = _capture(ConnectionSpec(host="127.0.0.1", port=qemu[0], password=TICKET))
    assert w > 0 and h > 0


def test_proxmox_style_vv_over_tls_and_proxy(qemu, pki, connect_proxy, tmp_path):
    from saffron import vv_file

    proxy, seen = connect_proxy
    path = tmp_path / "pve.vv"
    path.write_text(_vv(pki, qemu[1], proxy))
    w, h = _capture(vv_file.load(str(path)))
    assert w > 0 and h > 0
    assert not path.exists()  # delete-this-file honoured
    assert any(s.startswith("pvespiceproxy:abcd:100:pve::beef:") for s in seen)


def test_wrong_ticket_is_reported(qemu, pki, connect_proxy, tmp_path):
    from saffron import vv_file

    path = tmp_path / "bad.vv"
    path.write_text(_vv(pki, qemu[1], connect_proxy[0], password="expired"))
    with pytest.raises(RuntimeError, match="Authentication failed"):
        _capture(vv_file.load(str(path)))
