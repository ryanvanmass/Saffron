"""Command-line target parsing, kept Qt- and gi-free so it's easy to test.

Accepts what remote-viewer/virt-viewer accept, so Saffron can stand in for
them: a .vv file, a spice:// URI, or `--connect LIBVIRT_URI DOMAIN`.
"""

import argparse
import sys
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from saffron import __version__
from saffron.spec import ConnectionSpec


@dataclass
class Target:
    """Exactly one of `spec` (ready to connect) or `libvirt_uri`+`domain`."""

    spec: ConnectionSpec | None = None
    libvirt_uri: str | None = None
    domain: str | None = None
    wait: bool = False
    ca_file: str | None = None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="saffron",
        description="SPICE viewer. Drop-in for remote-viewer/virt-viewer's common options.",
    )
    p.add_argument("target", nargs="?", help="a .vv connection file, a spice://host:port URI, or a domain with --connect")
    p.add_argument("-c", "--connect", metavar="URI", help="libvirt URI, e.g. qemu+ssh://user@host/system")
    p.add_argument("-w", "--wait", action="store_true", help="wait for the domain to start")
    p.add_argument("-f", "--full-screen", action="store_true", help="open in full screen")
    p.add_argument("-t", "--title", help="window title")
    p.add_argument("--spice-ca-file", metavar="FILE", help="CA certificate for TLS SPICE connections")
    p.add_argument("-V", "--version", action="version", version=f"saffron {__version__}")
    return p


def parse_spice_uri(uri: str) -> ConnectionSpec:
    """spice://host:port[?tls-port=N&password=X] (remote-viewer's URI form)."""
    parsed = urlsplit(uri)
    if parsed.scheme not in ("spice", "spice+tls"):
        raise ValueError(f"not a spice:// URI: {uri!r}")
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    tls_port = query.get("tls-port")
    port = parsed.port
    if parsed.scheme == "spice+tls":
        tls_port, port = (tls_port or port), None
    spec = ConnectionSpec(
        host=parsed.hostname or "",
        port=port if port is None else int(port),
        tls_port=int(tls_port) if tls_port else None,
        password=query.get("password", ""),
    )
    spec.validate()
    return spec


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, Target]:
    """Raises ValueError for unusable input. Unknown virt-viewer options are
    ignored with a warning rather than rejected, so callers that pass extras
    (--zoom, --hotkeys, --debug...) still work."""
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print(f"saffron: ignoring unsupported option(s): {' '.join(unknown)}", file=sys.stderr)

    if args.connect:
        if not args.target:
            raise ValueError("--connect needs a domain name, ID or UUID")
        target = Target(libvirt_uri=args.connect, domain=args.target, wait=args.wait, ca_file=args.spice_ca_file)
    elif not args.target:
        raise ValueError("nothing to connect to: give a .vv file, a spice:// URI, or --connect URI DOMAIN")
    elif "://" in args.target:
        spec = parse_spice_uri(args.target)
        if args.spice_ca_file:
            with open(args.spice_ca_file, encoding="utf-8") as f:
                spec.ca_pem = f.read()
        target = Target(spec=spec)
    else:
        from saffron import vv_file

        target = Target(spec=vv_file.load(args.target))

    if target.spec is not None:
        if args.full_screen:
            target.spec.fullscreen = True
        if args.title:
            target.spec.title = args.title
    return args, target
