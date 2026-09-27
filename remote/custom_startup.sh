#!/usr/bin/env bash
set -e

# Zoom's single-instance lock is an XDG_RUNTIME_DIR socket. Without it the client
# logs "QStandardPaths: XDG_RUNTIME_DIR not set" and the deep-link hand-off
# between ZoomLauncher instances cannot complete, so a launch silently fails to
# join even though the client is up.
export XDG_RUNTIME_DIR="/tmp/runtime-kasm-user"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

if ! pgrep -f '/usr/local/bin/zoom-remote-controller' >/dev/null; then
    /usr/local/bin/zoom-remote-controller &
fi

exec /dockerstartup/custom_startup.kasm.sh "$@"
