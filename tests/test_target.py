import pytest

from saffron.target import parse_args, parse_spice_uri


def test_connect_domain_wait():
    args, t = parse_args(["--connect", "qemu+ssh://root@kvm1/system", "--wait", "web01"])
    assert (t.libvirt_uri, t.domain, t.wait, t.spec) == ("qemu+ssh://root@kvm1/system", "web01", True, None)


def test_virt_viewer_style_short_flags():
    _, t = parse_args(["-c", "qemu:///system", "-w", "vm"])
    assert t.libvirt_uri == "qemu:///system" and t.wait


def test_connect_requires_domain():
    with pytest.raises(ValueError, match="needs a domain"):
        parse_args(["--connect", "qemu:///system"])


def test_nothing_to_connect_to():
    with pytest.raises(ValueError, match="nothing to connect to"):
        parse_args([])


def test_unknown_virt_viewer_options_are_ignored(capsys):
    _, t = parse_args(["--zoom=100", "--hotkeys=toggle-fullscreen=shift+f11", "spice://h:5900"])
    assert t.spec.port == 5900
    assert "ignoring unsupported option" in capsys.readouterr().err


def test_vv_file_with_overrides(tmp_path):
    path = tmp_path / "c.vv"
    path.write_text("[virt-viewer]\nhost=h\nport=5900\ntitle=from file\n")
    _, t = parse_args([str(path), "--full-screen", "--title", "override"])
    assert t.spec.fullscreen and t.spec.title == "override"


@pytest.mark.parametrize(
    "uri, host, port, tls_port, password",
    [
        ("spice://10.0.0.5:5900", "10.0.0.5", 5900, None, ""),
        ("spice://h:5900?tls-port=5901&password=pw", "h", 5900, 5901, "pw"),
        ("spice://h?tls-port=5901", "h", None, 5901, ""),
        ("spice+tls://h:5901", "h", None, 5901, ""),
    ],
)
def test_spice_uris(uri, host, port, tls_port, password):
    spec = parse_spice_uri(uri)
    assert (spec.host, spec.port, spec.tls_port, spec.password) == (host, port, tls_port, password)


def test_spice_uri_without_port():
    with pytest.raises(ValueError, match="no SPICE port"):
        parse_spice_uri("spice://h")
