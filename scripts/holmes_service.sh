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

assert_service_root_accessible() {
  if [ "$(uname -s)" != "Darwin" ]; then
    return
  fi

  case "$ROOT/" in
    "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*)
      cat >&2 <<EOF
Impossible d'installer Holmes comme LaunchAgent depuis :
  $ROOT

macOS protège Documents, Desktop et Downloads. Un LaunchAgent peut donc être
chargé par launchd tout en échouant ensuite avec « Operation not permitted ».

Déplace le dépôt vers un emplacement non protégé, par exemple :
  $HOME/holmes-OS
puis relance depuis ce nouvel emplacement :
  ./jarvis service-install
EOF
      exit 1
      ;;
  esac
}

render_plist() {
  mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"
  python3 - "$PLIST" "$ROOT" "$LOG_DIR" "$PATH" <<'PY'
import plistlib
import sys
from pathlib import Path

target, root, log_dir, path = sys.argv[1:]
root_path = Path(root)
venv_bin = str(root_path / ".venv" / "bin")
path_entries = [venv_bin]
for entry in path.split(":"):
    # Un dépôt déplacé laisse souvent l'ancien venv en tête du PATH du shell.
    if entry.endswith("/holmes-OS/.venv/bin") and entry != venv_bin:
        continue
    # Ne jamais figer dans launchd les runtimes temporaires de Codex : ils sont
    # supprimés hors session et rendraient le service non reproductible.
    if "/.codex/tmp/" in entry or "/.cache/codex-runtimes/" in entry:
        continue
    if entry and entry not in path_entries:
        path_entries.append(entry)
payload = {
    "Label": "com.holmes-os.runtime",
    "ProgramArguments": [str(Path(root) / "jarvis"), "run"],
    "WorkingDirectory": root,
    "EnvironmentVariables": {
        "PATH": ":".join(path_entries),
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
    # Après un bootout, launchd peut garder le job quelques centaines de ms
    # dans l'état de transition et répondre EIO. On attend sa disparition et
    # on retente proprement au lieu de laisser Holmes arrêté.
    for _attempt in {1..20}; do
      if launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null; then
        echo "Holmes démarré comme service macOS."
        return
      fi
      sleep 0.1
    done
    echo "Impossible de charger le service Holmes après plusieurs tentatives." >&2
    exit 1
  fi
  echo "Holmes démarré comme service macOS."
}

stop_service() {
  if is_loaded; then
    launchctl bootout "$DOMAIN/$LABEL"
    for _attempt in {1..20}; do
      is_loaded || break
      sleep 0.1
    done
    echo "Holmes arrêté."
  else
    echo "Holmes est déjà arrêté."
  fi
}

case "${1:-status}" in
  install)
    assert_service_root_accessible
    if is_loaded; then
      launchctl bootout "$DOMAIN/$LABEL"
      for _attempt in {1..20}; do
        is_loaded || break
        sleep 0.1
      done
    fi
    render_plist
    start_service >/dev/null
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
      STATUS="$(launchctl print "$DOMAIN/$LABEL")"
      printf '%s\n' "$STATUS" | sed -n '1,35p'
      if ! printf '%s\n' "$STATUS" | grep -q $'\tstate = running'; then
        echo >&2
        echo "ATTENTION : le service est chargé mais Holmes ne tourne pas." >&2
        echo "Consulte : ./jarvis service-logs" >&2
        exit 1
      fi
    else
      if [ -f "$PLIST" ]; then
        echo "Holmes est installé mais arrêté. Lance : ./jarvis service-start"
      else
        echo "Holmes est arrêté ou le service n'est pas installé."
      fi
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
