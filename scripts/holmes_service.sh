#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.holmes-os.runtime"
DOMAIN="gui/$(id -u)"
PLIST="${HOLMES_SERVICE_PLIST:-$HOME/Library/LaunchAgents/$LABEL.plist}"
LOG_DIR="${HOLMES_SERVICE_LOG_DIR:-$HOME/Library/Logs/Holmes OS}"

is_loaded() {
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

render_plist() {
  mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"
  python3 - "$PLIST" "$ROOT" "$LOG_DIR" "$PATH" <<'PY'
import plistlib
import sys
from pathlib import Path

target, root, log_dir, path = sys.argv[1:]
payload = {
    "Label": "com.holmes-os.runtime",
    "ProgramArguments": [str(Path(root) / "jarvis"), "run"],
    "WorkingDirectory": root,
    "EnvironmentVariables": {
        "PATH": path,
        "PYTHONUNBUFFERED": "1",
    },
    "RunAtLoad": True,
    "KeepAlive": {"SuccessfulExit": False},
    "ProcessType": "Interactive",
    "StandardOutPath": str(Path(log_dir) / "runtime.log"),
    "StandardErrorPath": str(Path(log_dir) / "runtime-error.log"),
}
with Path(target).open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY
}

start_service() {
  if [ ! -f "$PLIST" ]; then
    echo "Service non installé. Lance : ./jarvis service-install" >&2
    exit 1
  fi
  if is_loaded; then
    launchctl kickstart -k "$DOMAIN/$LABEL"
  else
    launchctl bootstrap "$DOMAIN" "$PLIST"
  fi
  echo "Holmes démarré comme service macOS."
}

stop_service() {
  if is_loaded; then
    launchctl bootout "$DOMAIN/$LABEL"
    echo "Holmes arrêté."
  else
    echo "Holmes est déjà arrêté."
  fi
}

case "${1:-status}" in
  install)
    if is_loaded; then
      launchctl bootout "$DOMAIN/$LABEL"
    fi
    render_plist
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "Service Holmes installé et démarré : $PLIST"
    ;;
  uninstall)
    stop_service
    if [ -f "$PLIST" ]; then
      DISABLED="$PLIST.disabled.$(date +%Y%m%d-%H%M%S)"
      mv "$PLIST" "$DISABLED"
      echo "Configuration désactivée : $DISABLED"
    fi
    ;;
  start) start_service ;;
  stop) stop_service ;;
  restart)
    stop_service
    start_service
    ;;
  status)
    if is_loaded; then
      launchctl print "$DOMAIN/$LABEL" | sed -n '1,35p'
    else
      echo "Holmes est arrêté ou le service n'est pas installé."
      exit 1
    fi
    ;;
  logs)
    mkdir -p "$LOG_DIR"
    touch "$LOG_DIR/runtime.log" "$LOG_DIR/runtime-error.log"
    tail -n 100 -F "$LOG_DIR/runtime.log" "$LOG_DIR/runtime-error.log"
    ;;
  *)
    echo "Usage : $0 {install|uninstall|start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
