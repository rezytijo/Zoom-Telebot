#!/usr/bin/env bash
# Package the agent into a single zip artifact.
# Usage: ./package_agent.sh -o zoom-agent.zip

set -euo pipefail

OUT=zoom-agent.zip
INCLUDE_README=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--out) OUT="$2"; shift 2;;
    --no-readme) INCLUDE_README=false; shift 1;;
    *) echo "Unknown arg $1"; exit 1;;
  esac
done

ROOT_DIR=$(dirname "$0")
TMPDIR=$(mktemp -d)

cleanup(){ rm -rf "$TMPDIR"; }
trap cleanup EXIT

mkdir -p "$TMPDIR/agent"
cp -r "$ROOT_DIR/"* "$TMPDIR/agent/"

# minimal requirements
cat > "$TMPDIR/agent/agent_requirements.txt" <<'REQ'
aiohttp
pyautogui
REQ

# helper run scripts
cat > "$TMPDIR/run_agent.sh" <<'SH'
#!/usr/bin/env bash
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r agent/agent_requirements.txt
python3 agent/agent_server.py "$@"
SH
chmod +x "$TMPDIR/run_agent.sh"

cat > "$TMPDIR/run_agent.bat" <<'BAT'
@echo off
if not exist venv (python -m venv venv)
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r agent\agent_requirements.txt
python agent\agent_server.py %*
BAT

if [ "$INCLUDE_README" = true ] && [ -f "$ROOT_DIR/README_AGENT.md" ]; then
  cp "$ROOT_DIR/README_AGENT.md" "$TMPDIR/agent/"
fi

pushd "$TMPDIR" >/dev/null
zip -r "$OUT" ./*
popd >/dev/null

mv "$TMPDIR/$OUT" .
echo "Created package: $OUT"
