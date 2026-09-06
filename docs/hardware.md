# EIT hardware

The control software does not care which board you use. Requirements:

1. Two independent Ethernet ports for the **data path** (tester ↔ UUT).
2. A **third control path** that still works when the data ports are down: USB Ethernet, USB serial, or a dedicated management NIC.
3. Mainline Linux with `ip`, `tc` (netem), and `ethtool`.
4. **Small** — this box sits on a tester bench, not in a rack.

PoE is not passed through on any of these boards. If the UUT is PoE-powered, inject PoE on the UUT side of the EIT.

## Size-first options

| Board | PCB / case | Data NICs | Why pick it |
| --- | --- | --- | --- |
| **NanoPi R5C** | 58×58 mm / 62.5×62.5×29 mm | Dual **2.5G** RTL8125BG (symmetric) | **Preferred.** Same pocket size as the R3S, matching NICs, 4 GB RAM option, two USB 3 ports for a management dongle. |
| NanoPi R3S / R3S-LTS | 57×57 mm / 61.5×61.5×25 mm | 1G GMAC+RTL8211F + 1G PCIe RTL8111H | Smallest. Asymmetric NICs; still fine for 1 Gbit software testers. |
| NanoPi R6C | 90×62 mm | 1G + 2.5G | More CPU (RK3588S) if netem+delay at high rate needs headroom. Larger. |
| x86 N100 dual-2.5G mini PC | ~110–130 mm | Dual 2.5G (Intel i225/i226 preferred) | Best netem accuracy and NIC symmetry. Only if the extra size is acceptable. |

Do not use a Raspberry Pi 5 as the data path: it has one onboard GbE and would put a USB Ethernet adapter in the impaired path.

## Recommended buy

If starting from scratch: **NanoPi R5C, 4 GB RAM, 32 GB eMMC, metal case**, USB-C 5 V/3 A PSU, USB-UART (1.5 Mbaud, 3.3 V), and a USB Gigabit or Fast Ethernet dongle for `eit-mgmt`.

The original R3S remains supported. Set interface names in `/etc/eit/config.json` after first boot; do not hard-code `eth0`/`eth1`.

## Control cabling from the tester PC

The tester is a Linux computer, so drive the EIT from there:

```text
Tester eth0  -------- EIT lan  (data)
Tester USB-Ethernet -- EIT USB-A  (mgmt, 192.168.50.1)
Tester USB-UART ----- EIT debug UART (recovery, 1500000 8N1 on FriendlyElec boards)
EIT wan ------------- UUT
```

If the tester PC already has two NICs, the second NIC can be the management link and you can skip the USB dongle.

## First boot checklist

1. Flash Debian (Trixie/Bookworm) or Ubuntu Server for the board. Avoid OpenWrt’s default LAN/WAN NAT.
2. `ip link` and `ethtool` both data ports; record MAC addresses and drivers.
3. Fill `/etc/udev/rules.d/99-eit-nics.rules` so names are `eit-lan`, `eit-wan`, `eit-mgmt`.
4. `eit-bringup eit-lan eit-wan` then `iperf3` through the box with **no** faults (≥900 Mbps on 1G, offloads off).
5. Pull both data links down and confirm SSH to the management address still works.
6. On a 2.5G board, set `"assumed_link_bps": 2500000000` in `/etc/eit/config.json` so delay queues are sized correctly.

UART on FriendlyElec NanoPi R-series is **1 500 000 baud**, not 115200.
