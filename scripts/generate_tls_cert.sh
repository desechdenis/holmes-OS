#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/config/tls"
HOST_NAME="$(hostname -s 2>/dev/null || hostname)"
LAN_IP="${1:-$(ifconfig 2>/dev/null | awk '/inet 192\.168\./{print $2; exit}')}"

if [ -z "$LAN_IP" ]; then
  echo "Usage: $0 192.168.0.x" >&2
  exit 1
fi

mkdir -p "$OUT"
CONF="$(mktemp)"
trap 'rm -f "$CONF"' EXIT
sed -e "s/__HOST__/$HOST_NAME/g" -e "s/__IP__/$LAN_IP/g" \
  "$ROOT/config/tls-openssl.cnf" > "$CONF"

openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 365 \
  -keyout "$OUT/holmes.key" -out "$OUT/holmes.crt" -config "$CONF"
chmod 600 "$OUT/holmes.key"
chmod 644 "$OUT/holmes.crt"

echo "HTTPS Holmes : https://$LAN_IP:8000"
echo "Certificat à approuver sur les clients : $OUT/holmes.crt"
