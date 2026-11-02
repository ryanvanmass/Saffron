#!/bin/bash
# Saffron.app's executable. Runs the bundled Python sources on a Homebrew
# Python that has PySide6 and PyGObject + spice-glib available:
#
#     brew install spice-gtk pygobject3 pyside
#
# These stay Homebrew runtime dependencies (the same call IT Toolbox made
# for FreeRDP) instead of being bundled: spice-glib drags in GLib,
# GStreamer, OpenSSL and friends, and Homebrew keeps them patched.
#
# `exec` keeps this the app's own process, so macOS delivers Finder's
# "open .vv file" events to the Qt app (see saffron/cli.py).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # Saffron.app/Contents

# A Finder-launched app gets launchd's bare PATH. Add Homebrew's so virsh,
# ssh and the Homebrew Python are found.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONPATH="$HERE/Resources/app${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

CHECK='import gi; gi.require_version("SpiceClientGLib", "2.0"); from gi.repository import SpiceClientGLib; import PySide6.QtWidgets'

# SAFFRON_PYTHON overrides the search (useful for a venv or a test build).
candidates=("${SAFFRON_PYTHON:-}")
for prefix in /opt/homebrew /usr/local; do
    for v in 3.15 3.14 3.13 3.12; do
        candidates+=("$prefix/opt/python@$v/bin/python$v")
    done
    candidates+=("$prefix/bin/python3")
done

for py in "${candidates[@]}"; do
    if [[ -n "$py" && -x "$py" ]] && "$py" -c "$CHECK" 2>/dev/null; then
        # SAFFRON_PRINT_PYTHON=1: report the interpreter instead of running
        # (CI runs the test suite on exactly the Python the app would use).
        if [[ "${SAFFRON_PRINT_PYTHON:-}" == 1 ]]; then echo "$py"; exit 0; fi
        exec "$py" -m saffron "$@"
    fi
done

msg="Saffron needs Homebrew's SPICE and Qt packages. In Terminal, run:

brew install spice-gtk pygobject3 pyside"
echo "$msg" >&2
/usr/bin/osascript -e "display alert \"Saffron can't start\" message \"$msg\" as critical" >/dev/null 2>&1 || true
exit 1
