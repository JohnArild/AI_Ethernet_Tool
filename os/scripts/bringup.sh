#!/usr/bin/env bash
# Configure a transparent two-port bridge for the EIT data path.
# Usage: bringup.sh <lan-if> <wan-if> [bridge]
set -euo pipefail

LAN=${1:?lan interface required}
WAN=${2:?wan interface required}
BR=${3:-br-eit}

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing $1"; }

need ip
need ethtool
need tc

for dev in "$LAN" "$WAN"; do
  ip link show "$dev" >/dev/null || die "interface $dev not found"
done

if ! ip link show "$BR" >/dev/null 2>&1; then
  ip link add name "$BR" type bridge stp_state 0 vlan_filtering 0
fi

ip addr flush dev "$LAN" || true
ip addr flush dev "$WAN" || true
ip addr flush dev "$BR" || true

ip link set "$LAN" down
ip link set "$WAN" down
ip link set "$LAN" master "$BR"
ip link set "$WAN" master "$BR"

# Forward 802.1D reserved multicasts (LLDP, LACP, 802.1X). Default mask is 0.
if [[ -w /sys/class/net/$BR/bridge/group_fwd_mask ]]; then
  echo 0xffff > "/sys/class/net/$BR/bridge/group_fwd_mask"
fi
if [[ -w /sys/class/net/$BR/bridge/stp_state ]]; then
  echo 0 > "/sys/class/net/$BR/bridge/stp_state"
fi

for key in bridge-nf-call-iptables bridge-nf-call-ip6tables bridge-nf-call-arptables; do
  if [[ -w /proc/sys/net/bridge/$key ]]; then
    echo 0 > "/proc/sys/net/bridge/$key"
  fi
done

ip link set "$BR" up
ip link set "$LAN" up
ip link set "$WAN" up

# Disable offloads and EEE so netem sees real packets.
for dev in "$LAN" "$WAN"; do
  ethtool -K "$dev" tso off gso off gro off lro off rx off tx off sg off ufo off >/dev/null 2>&1 || true
  ethtool --set-eee "$dev" eee off >/dev/null 2>&1 || true
  ethtool -A "$dev" rx off tx off >/dev/null 2>&1 || true
done

echo "bridge $BR: $LAN <-> $WAN"
ip -br link show "$LAN" "$WAN" "$BR"
