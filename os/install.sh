#!/usr/bin/env bash
# Install EIT onto a Debian/Ubuntu dual-NIC box.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=${PREFIX:-/opt/eit}

if [[ ${EUID} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

install -d "$PREFIX"
install -d /etc/eit/profiles
install -d /etc/systemd/system
install -d /etc/sysctl.d
install -d /etc/systemd/network
install -d /etc/udev/rules.d

python3 -m pip install --upgrade --break-system-packages "$ROOT" || \
  python3 -m pip install --upgrade "$ROOT"

install -m 0644 "$ROOT/os/config.json" /etc/eit/config.json
install -m 0644 "$ROOT/os/sysctl.d/99-eit.conf" /etc/sysctl.d/99-eit.conf
install -m 0644 "$ROOT/os/systemd/eitd.service" /etc/systemd/system/eitd.service
install -m 0644 "$ROOT/os/systemd-networkd/"*.netdev /etc/systemd/network/ || true
install -m 0644 "$ROOT/os/systemd-networkd/"*.network /etc/systemd/network/
install -m 0644 "$ROOT/os/udev/99-eit-nics.rules" /etc/udev/rules.d/99-eit-nics.rules
install -m 0755 "$ROOT/os/scripts/bringup.sh" /usr/local/sbin/eit-bringup

# Seed profiles; do not overwrite operator-edited copies.
for f in "$ROOT"/src/eit/builtin_profiles/*.json; do
  base=$(basename "$f")
  if [[ ! -e /etc/eit/profiles/$base ]]; then
    install -m 0644 "$f" "/etc/eit/profiles/$base"
  fi
done

sysctl --system >/dev/null || true
systemctl daemon-reload
systemctl enable eitd.service

echo "Installed. Next:"
echo "  1. Set MAC-based names in /etc/udev/rules.d/99-eit-nics.rules"
echo "  2. Edit /etc/eit/config.json (lan/wan/listen)"
echo "  3. eit-bringup <lan> <wan>   # or reboot with systemd-networkd"
echo "  4. systemctl start eitd"
echo "  5. eit status"
