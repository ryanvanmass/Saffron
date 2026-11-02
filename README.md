# Saffron

A small native SPICE viewer for KVM/libvirt and Proxmox VMs. It's built on
the SPICE client from [IT Toolbox](https://github.com/ryanvanmass/it-toolbox)
(spice-glib driven from Python, drawn with Qt) and stands in for
`remote-viewer`/`virt-viewer`, which are poorly maintained on macOS.
[virt-connect](https://github.com/ryanvanmass/virt-connect) uses it as its
viewer on the Mac.

## What it does

- Opens **`.vv` connection files**, like the ones the Proxmox web UI's
  SPICE button downloads. It handles TLS, the CA certificate, the
  certificate subject check, Proxmox's `spiceproxy` (an HTTP CONNECT
  proxy) and one-time tickets, and deletes the file after reading it when
  the file asks for that (`delete-this-file=1`). On macOS you can
  double-click a `.vv` file to open it in Saffron.
- Connects to **libvirt domains** the way `virt-viewer` does:
  `saffron --connect qemu+ssh://user@host/system --wait myvm`. It finds the
  VM's SPICE port with `virsh` and opens an SSH tunnel for `qemu+ssh://`
  URIs.
- Opens **`spice://host:port`** URIs.
- Sizes the window to the guest, asks the guest (through spice-vdagent) to
  follow window resizes, shares host-to-guest clipboard text, and has a
  **Send Key** menu (Ctrl+Alt+Del, Ctrl+Alt+F1–F12...). **Shift+F11**
  toggles full screen, as in virt-viewer.

The command line follows remote-viewer's, so a caller can swap the binary
name. Options Saffron doesn't support (`--zoom`, `--hotkeys`, ...) are
ignored with a warning, not rejected.

```
saffron FILE.vv
saffron spice://HOST:PORT[?tls-port=N&password=X]
saffron --connect LIBVIRT_URI [--wait] DOMAIN
        [--full-screen] [--title TITLE] [--spice-ca-file CA.pem]
```

## Install

### macOS

Download `Saffron-<version>-macos.dmg` from Releases and drag Saffron to
Applications. It's ad-hoc signed, so open it the first time with
right-click > Open. Saffron runs on Homebrew's SPICE and Qt packages,
which you install once:

```
brew install spice-gtk pygobject3 pyside
```

For `--connect` you also need `virsh` (`brew install libvirt`) and
key-based SSH to your libvirt hosts.

### Linux

```
sudo apt install python3-gi gir1.2-spiceclientglib-2.0     # Debian/Ubuntu
sudo dnf install python3-gobject spice-glib                 # Fedora
python3 -m venv --system-site-packages ~/.local/share/saffron-venv
~/.local/share/saffron-venv/bin/pip install git+https://github.com/ryanvanmass/Saffron
```

## How it's put together

| Module | What it is |
| --- | --- |
| `saffron/spice/` | The SPICE session, its GLib loop thread and the Qt signal bridge, carried over from IT Toolbox's `core/spice/`. Saffron adds TLS, CA, certificate-subject, proxy and secure-channel settings. |
| `saffron/widget.py` | IT Toolbox's `SpiceWidget`: draws only the changed rows, keeps the aspect ratio, maps input, resizes through the agent, and shares the clipboard. |
| `saffron/vv_file.py` | Reads `.vv` files. It's written from the documented format (remote-viewer(1)), not copied from virt-viewer, which is GPL. |
| `saffron/libvirt.py`, `ssh_tunnel.py` | Finds a domain's SPICE display with `virsh`, waits for it to start, and tunnels `qemu+ssh://`. |
| `saffron/window.py`, `cli.py` | The window, its menus, the command line, and macOS file-open events. |

On macOS, `Saffron.app` holds these sources and a launcher that finds a
Homebrew Python with PySide6 and spice-glib. Saffron keeps them as Homebrew
dependencies instead of bundling them (the same call IT Toolbox made for
FreeRDP), so GLib, GStreamer and OpenSSL get patched through Homebrew.

## Development

```
python3 -m venv --system-site-packages .venv   # needs python3-gi + spice-glib typelib
.venv/bin/pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

`SAFFRON_LIVE=1` also runs end-to-end tests against a real QEMU SPICE
server: a plain connection, and a Proxmox-style `.vv` over TLS through an
HTTP CONNECT proxy. They need `qemu-system-x86_64` with SPICE support and
`openssl`. CI runs them on Linux, and builds and smoke-tests the `.app` on
macOS. `packaging/macos/build.sh` builds the `.app` and `.dmg` locally.

`SAFFRON_NO_DIALOGS=1` prints errors to stderr instead of showing a
dialog, and `saffron --self-test` checks that the native stack loads.

## License

Apache-2.0, the same as IT Toolbox, which much of the SPICE code comes
from.
