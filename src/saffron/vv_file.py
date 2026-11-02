"""Reader for virt-viewer connection files (.vv), as written by Proxmox VE,
oVirt and others for `remote-viewer file.vv`.

Format reference: virt-viewer's man page (remote-viewer(1), "CONNECTION
FILE"). It's an INI file with a [virt-viewer] section. Only the keys that
matter for a SPICE connection are read; everything else is ignored, as
remote-viewer does for keys it doesn't know. This is a fresh
implementation of the documented format, not code from virt-viewer.
"""

import configparser
import os

from saffron.spec import ConnectionSpec

SECTION = "virt-viewer"


class VvFileError(ValueError):
    pass


def _int(value: str | None, key: str) -> int | None:
    if value is None or value.strip() in ("", "-1"):
        return None
    try:
        return int(value)
    except ValueError as e:
        raise VvFileError(f"{key} is not a number: {value!r}") from e


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def parse(text: str) -> tuple[ConnectionSpec, bool]:
    """Parse .vv contents. Returns (spec, delete_this_file)."""
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read_string(text)
    except configparser.Error as e:
        raise VvFileError(f"not a valid connection file: {e}") from e
    if not parser.has_section(SECTION):
        raise VvFileError(f"no [{SECTION}] section")
    s = parser[SECTION]

    kind = s.get("type", "spice").strip().lower()
    if kind != "spice":
        raise VvFileError(f"unsupported connection type {kind!r} (Saffron only speaks SPICE)")

    ca = s.get("ca")
    if ca:
        # The certificate is stored on one line with literal "\n" escapes.
        ca = ca.replace("\\n", "\n").strip() + "\n"

    channels = [c.strip() for c in (s.get("secure-channels") or "").split(";") if c.strip()]

    spec = ConnectionSpec(
        host=(s.get("host") or "").strip(),
        port=_int(s.get("port"), "port"),
        tls_port=_int(s.get("tls-port"), "tls-port"),
        password=s.get("password") or "",
        ca_pem=ca or None,
        host_subject=(s.get("host-subject") or "").strip() or None,
        proxy=(s.get("proxy") or "").strip() or None,
        secure_channels=channels,
        title=s.get("title"),
        fullscreen=_bool(s.get("fullscreen")),
        release_cursor=s.get("release-cursor"),
        toggle_fullscreen=s.get("toggle-fullscreen"),
    )
    try:
        spec.validate()
    except ValueError as e:
        raise VvFileError(str(e)) from e
    return spec, _bool(s.get("delete-this-file"))


def load(path: str) -> ConnectionSpec:
    """Read a .vv file, honouring delete-this-file=1 (Proxmox sets it, since
    the file holds a one-time ticket) by removing it once it's been read."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise VvFileError(f"can't read {path}: {e.strerror}") from e
    spec, delete = parse(text)
    if delete:
        try:
            os.unlink(path)
        except OSError:
            pass
    return spec
