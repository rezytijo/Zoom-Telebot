#!/usr/bin/env bash
set -e

if ! pgrep -f '/usr/local/bin/zoom-remote-controller' >/dev/null; then
    /usr/local/bin/zoom-remote-controller &
fi

exec /dockerstartup/custom_startup.kasm.sh "$@"
