import os
import stat
import textwrap

import pytest

from saffron import libvirt
from saffron.libvirt import SpiceGraphics, build_spec, parse_spice_graphics, wait_for_graphics

RUNNING = """<domain type='kvm'><name>web01</name><devices>
  <graphics type='vnc' port='5901'/>
  <graphics type='spice' port='5900' tlsPort='5902' autoport='yes' listen='127.0.0.1' passwd='pw'>
    <listen type='address' address='127.0.0.1'/>
  </graphics></devices></domain>"""
STOPPED = """<domain><devices><graphics type='spice' autoport='yes'>
  <listen type='address'/></graphics></devices></domain>"""
NO_SPICE = "<domain><devices><graphics type='vnc' port='5901'/></devices></domain>"


def test_parse_running():
    g = parse_spice_graphics(RUNNING)
    assert g == SpiceGraphics(port=5900, tls_port=5902, listen="127.0.0.1", password="pw")


def test_parse_stopped_and_missing():
    g = parse_spice_graphics(STOPPED)
    assert (g.port, g.tls_port) == (None, None)
    assert parse_spice_graphics(NO_SPICE) is None


def test_parse_listen_from_child_element():
    xml = "<domain><devices><graphics type='spice' port='5900'><listen type='address' address='0.0.0.0'/></graphics></devices></domain>"
    assert parse_spice_graphics(xml).listen == "0.0.0.0"


def test_local_uri_connects_directly():
    spec, tunnel = build_spec("qemu:///system", SpiceGraphics(5900, None, "0.0.0.0", "pw"))
    assert tunnel is None
    assert (spec.host, spec.port, spec.password) == ("127.0.0.1", 5900, "pw")


def test_tcp_uri_uses_uri_host_when_listening_everywhere():
    spec, _ = build_spec("qemu+tcp://kvm1/system", SpiceGraphics(5900, None, "0.0.0.0", ""))
    assert (spec.host, spec.port) == ("kvm1", 5900)


def test_tcp_uri_refuses_localhost_only_listener():
    with pytest.raises(libvirt.LibvirtError, match="qemu\\+ssh"):
        build_spec("qemu+tcp://kvm1/system", SpiceGraphics(5900, None, "127.0.0.1", ""))


def test_tls_only_needs_ca(tmp_path):
    with pytest.raises(libvirt.LibvirtError, match="spice-ca-file"):
        build_spec("qemu:///system", SpiceGraphics(None, 5902, "127.0.0.1", ""))
    ca = tmp_path / "ca.pem"
    ca.write_text("PEM")
    spec, _ = build_spec("qemu:///system", SpiceGraphics(None, 5902, "127.0.0.1", ""), ca_file=str(ca))
    assert (spec.port, spec.tls_port, spec.ca_pem) == (None, 5902, "PEM")


def test_ssh_uri_opens_tunnel(monkeypatch):
    started = {}

    def fake_start(self, ready_timeout=10):
        started["args"] = (self._target, self._ssh_port, self._dest_host, self._dest_port)
        return 40000

    monkeypatch.setattr(libvirt.SshTunnel, "start", fake_start)
    spec, tunnel = build_spec("qemu+ssh://root@kvm1:2222/system", SpiceGraphics(5900, None, "127.0.0.1", ""))
    assert started["args"] == ("root@kvm1", 2222, "127.0.0.1", 5900)
    assert (spec.host, spec.port) == ("127.0.0.1", 40000)
    assert tunnel is not None


@pytest.fixture
def fake_virsh(tmp_path, monkeypatch):
    """A `virsh` on PATH that reports the domain stopped for the first N
    dumpxml calls, then running."""
    state = tmp_path / "calls"
    state.write_text("0")
    script = tmp_path / "virsh"

    def install(stopped_calls: int, missing: bool = False):
        (tmp_path / "running.xml").write_text(RUNNING)
        (tmp_path / "stopped.xml").write_text(STOPPED)
        script.write_text(textwrap.dedent(f"""\
            #!/bin/sh
            {'echo "error: failed to get domain" >&2; exit 1' if missing else ''}
            n=$(cat {state}); echo $((n+1)) > {state}
            if [ "$n" -lt {stopped_calls} ]; then cat {tmp_path}/stopped.xml; else cat {tmp_path}/running.xml; fi
            """))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
        return state

    return install


def test_wait_polls_until_running(fake_virsh):
    calls = fake_virsh(stopped_calls=2)
    g = wait_for_graphics("qemu:///system", "web01", wait=True, poll=0.01)
    assert g.port == 5900
    assert int(calls.read_text()) == 3


def test_no_wait_fails_fast_when_stopped(fake_virsh):
    fake_virsh(stopped_calls=5)
    with pytest.raises(libvirt.LibvirtError, match="not running"):
        wait_for_graphics("qemu:///system", "web01", wait=False)


def test_missing_domain_without_wait(fake_virsh):
    fake_virsh(stopped_calls=0, missing=True)
    with pytest.raises(libvirt.LibvirtError, match="failed to get domain"):
        wait_for_graphics("qemu:///system", "web01", wait=False)
