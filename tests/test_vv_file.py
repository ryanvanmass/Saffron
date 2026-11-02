import os

import pytest

from saffron import vv_file

PROXMOX_VV = r"""[virt-viewer]
type=spice
host=pvespiceproxy:6543abcd:100:pve::deadbeef
tls-port=61000
password=one-time-ticket%with%percents
ca=-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\n-----END CERTIFICATE-----\n
host-subject=OU=PVE Cluster Node,O=Proxmox Virtual Environment,CN=pve.example
proxy=http://pve.example:3128
secure-attention=Ctrl+Alt+Ins
release-cursor=Ctrl+Alt+R
toggle-fullscreen=Shift+F11
delete-this-file=1
title=VM 100 - web01
"""


def test_parses_proxmox_file():
    spec, delete = vv_file.parse(PROXMOX_VV)
    assert delete is True
    assert spec.host == "pvespiceproxy:6543abcd:100:pve::deadbeef"
    assert spec.port is None
    assert spec.tls_port == 61000
    assert spec.password == "one-time-ticket%with%percents"  # no INI interpolation
    assert spec.ca_pem == "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\n-----END CERTIFICATE-----\n"
    assert spec.host_subject == "OU=PVE Cluster Node,O=Proxmox Virtual Environment,CN=pve.example"
    assert spec.proxy == "http://pve.example:3128"
    assert spec.title == "VM 100 - web01"
    assert spec.toggle_fullscreen == "Shift+F11"


def test_plain_file_and_secure_channels():
    spec, delete = vv_file.parse(
        "[virt-viewer]\nhost=10.0.0.5\nport=5900\nfullscreen=1\nsecure-channels=main;inputs\n"
    )
    assert (spec.host, spec.port, spec.tls_port, delete) == ("10.0.0.5", 5900, None, False)
    assert spec.fullscreen is True
    assert spec.secure_channels == ["main", "inputs"]


@pytest.mark.parametrize(
    "text, message",
    [
        ("[other]\nhost=a\n", r"no \[virt-viewer\] section"),
        ("[virt-viewer]\ntype=vnc\nhost=a\nport=5900\n", "unsupported connection type"),
        ("[virt-viewer]\nhost=a\n", "no SPICE port"),
        ("[virt-viewer]\nport=5900\n", "no SPICE host"),
        ("[virt-viewer]\nhost=a\nport=abc\n", "not a number"),
        ("not an ini file", "not a valid connection file"),
    ],
)
def test_rejects_bad_files(text, message):
    with pytest.raises(vv_file.VvFileError, match=message):
        vv_file.parse(text)


def test_load_honours_delete_this_file(tmp_path):
    path = tmp_path / "ticket.vv"
    path.write_text(PROXMOX_VV)
    spec = vv_file.load(str(path))
    assert spec.tls_port == 61000
    assert not path.exists()


def test_load_keeps_file_without_delete_flag(tmp_path):
    path = tmp_path / "keep.vv"
    path.write_text("[virt-viewer]\nhost=h\nport=5900\n")
    vv_file.load(str(path))
    assert path.exists()


def test_load_missing_file(tmp_path):
    with pytest.raises(vv_file.VvFileError, match="can't read"):
        vv_file.load(os.fspath(tmp_path / "nope.vv"))
