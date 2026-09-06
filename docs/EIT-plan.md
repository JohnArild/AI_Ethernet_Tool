# Error Injection Tool (EIT) — Plan

**Role:** Inline network fault injector between an Ethernet tester and a unit under test (UUT)  
**Software:** Board-agnostic Linux appliance (`eit` CLI + `eitd` HTTP daemon)  
**Hardware:** Any small dual-NIC Linux box. NanoPi R5C preferred; R3S still valid.

---

## Viability assessment

**Verdict: viable.** The four commanded faults (link down, slow path, packet loss, high latency) are standard Linux traffic-control and PHY operations. The tester is **software running on a Linux PC**, not a cable certifier or PHY BERT, so an L2/L3 impairment bridge is the right tool.

It is **not** a Layer-1 / analog box. It will not produce NEXT, return loss, TDR, PoE signatures, symbol errors, or Ethernet FCS/CRC errors. `netem corrupt` flips bits **before** the NIC writes the FCS, so the peer usually sees a valid frame with a bad IPv4/TCP checksum.

### Why this matches the tester

A Linux software tester looks at carrier, negotiated speed, throughput, loss, and RTT — exactly what `ethtool`, `tc netem`, and `tc tbf`/`netem rate` can change. The tester PC can also **drive** the EIT over HTTP, so test scripts can inject a fault, run the measurement, and clear.

### Hardware: not locked to the NanoPi R3S

The R3S (57×57 mm, dual 1G) is a valid base. Size still matters; budget allows a better board in the same pocket:

| Board | Size | NICs | Notes |
| --- | --- | --- | --- |
| **NanoPi R5C** | 58×58 mm | Dual 2.5G, same RTL8125 | **Preferred.** Same size as R3S, symmetric NICs, more RAM, extra USB for management. |
| NanoPi R3S | 57×57 mm | Dual 1G, asymmetric PHYs | Original idea; smallest; fine for 1 Gbit tests. |
| NanoPi R6C | 90×62 mm | 1G + 2.5G | More CPU if delay+shaping at high rate needs it. |
| x86 N100 dual-NIC | ~12 cm | Dual 2.5G Intel | Best netem accuracy; only if size can grow. |

The **software treats lan/wan as config**, not as a board name. Swap hardware without rewriting the fault engine.

### Hard no

- Cable/physical-layer tests (length, NEXT, FEXT, insertion loss, split pairs).
- True Ethernet FCS/CRC injection.
- PoE pass-through (none of these boards are midspans).
- IEEE 1588 / PTP accuracy.
- Guaranteed line-rate **with** heavy delay+loss until measured on the chosen board. Disable TSO/GSO/GRO or netem lies.

**Recommendation:** build the EIT as a transparent Linux bridge with out-of-band control. Prefer an R5C for a new purchase; keep the software portable.

---

## Goal

```text
[ Linux tester PC ] ---- [ EIT ] ---- [ UUT ]
        NIC               lan   wan
   USB Ethernet/UART --- management
```

Default state is **transparent pass-through**. On command, apply one or more faults, then return to pass-through.

### v1 fault set (must)

1. **Link down** — lan, wan, or both; optional flap.
2. **Slow down** — PHY speed 10/100/1000, and separately a throughput cap (e.g. 10 Mbit/s).
3. **Packet loss** — percent, optional correlation.
4. **Latency** — delay + optional jitter.

### v1 extras

- Duplication, reordering, payload corrupt (labelled honestly).
- Combined profiles (`bad-wan`: delay + loss + rate).
- Auto-clear timeout (default 60 s).
- User button / `ExecStop` emergency clear.

### Non-goals for v1

PHY analog faults, FCS injection, PoE, 10G, PTP, polished GUI.

---

## Key decisions

1. **Transparent L2 bridge, not a router.** No IP on the data ports. NAT would hide the UUT.
2. **Debian/Ubuntu, not OpenWrt.** OpenWrt defaults to routed LAN/WAN. Debian gives `ip`/`tc`/`ethtool` and systemd.
3. **Out-of-band management.** Link-down and 100% loss kill in-band SSH. USB Ethernet (`eit-mgmt`) plus UART.
4. **Linux `tc netem` + `ethtool`.** No custom kernel datapath. Disable TSO/GSO/GRO/EEE.
5. **Fail-safe pass-through.** Boot with no qdiscs. Daemon SIGTERM/`ExecStop` clears. Every apply has a duration.
6. **Forward 802.1D reserved multicasts** (`group_fwd_mask=0xffff`) so LLDP/LACP/802.1X pass.
7. **Board-agnostic Python control plane** (`eit` + `eitd`). Interface names live in `/etc/eit/config.json`.
8. **HTTP from the tester PC.** The tester is Linux; scripts can `POST /v1/faults` then run iperf/ping/custom tests.

---

## Architecture

### Data plane

- `eit-lan` and `eit-wan` enslaved to `br-eit`.
- STP off, VLAN filtering off (802.1Q passes as payload).
- No IPv4/IPv6 on the bridge or members.
- `br_netfilter` off.
- Offloads off.

**netem is egress-only.** Bidirectional faults attach netem on **both** physical ports:

```text
tester --> [lan RX] --> br-eit --> [wan TX + netem] --> UUT
tester <-- [lan TX + netem] <-- br-eit <-- [wan RX] <-- UUT
```

Link-state and PHY speed use `ip link` / `ethtool` so the **adjacent** device sees carrier or speed change.

Delay queues must be sized for the delay × bitrate. Default netem `limit` of 1000 packets will turn delay into loss at 1 Gbit; the engine sets `limit` from assumed link rate (see `build_netem_args`).

### Control plane

| Path | Use |
| --- | --- |
| `eit-mgmt` USB Ethernet, 192.168.50.1/24 | SSH, HTTP API |
| Debug UART | Recovery |
| `POST /v1/faults` from the tester PC | Automated test scripts |
| User button (optional) | Clear |

```text
GET  /v1/status
GET  /v1/profiles
POST /v1/faults     { "loss_pct": 5, "duration_s": 30, "direction": "both" }
POST /v1/faults     { "profile": "bad-wan" }
POST /v1/clear
POST /v1/prepare
```

CLI: `eit status | apply | clear | profiles | prepare`. Default talks to eitd; `--direct` calls ip/tc/ethtool locally.

### Repo layout

```text
docs/EIT-plan.md hardware.md operator.md
src/eit/          CLI, daemon, dataplane, builtin profiles
os/               systemd, networkd, udev, bringup, install
tests/            unit tests + optional netns live tests
```

---

## Fault catalog (v1)

| Fault | Mechanism | Tester should see | Limits |
| --- | --- | --- | --- |
| Link down | `ip link set … down` | Carrier loss on that hop | PHY retrain ~1 s, not millisecond-accurate |
| Link flap | Down/up loop | Intermittent carrier | Same |
| PHY 10/100 | `ethtool -s speed N autoneg off` | Speed change + throughput drop | Partner must accept forced mode |
| Rate limit | `netem rate` | Throughput cap, **link speed unchanged** | Approximate; not a traffic-shaper lab instrument |
| Loss | `netem loss P%` | Drops / retransmits | Statistical; send enough packets |
| Delay / jitter | `netem delay` | RTT ≈ 2× one-way if applied both ways | ~1 ms granularity on ARM |
| Duplicate / reorder / corrupt | netem | Dup ACKs / OOO / L3 checksum errors | Corrupt is **not** FCS |

Direction: `both` (default), `to_uut`, `to_tester`.

---

## Implementation (done in-tree vs on-box)

| Piece | Status |
| --- | --- |
| Fault engine, CLI, HTTP daemon, profiles | In this repo |
| Unit tests (command sequences, HTTP, profiles) | In this repo |
| Optional netns live tests | In this repo; need root |
| OS bring-up scripts / systemd | In this repo; apply on the board |
| Phase 0 bench measurement (iperf through the real NICs) | Needs hardware |

### On-box remaining work

1. Flash Debian on the chosen board (R5C recommended).
2. Fill udev MAC names; `eit-bringup`; disable offloads.
3. Measure pass-through: ≥900 Mbps on 1G, added RTT typically &lt; 1 ms.
4. Confirm OOB SSH while data ports are down.
5. Run operator B-series tests against the Linux tester software.

---

## Recommended tests

### A. EIT self-tests

| ID | Test | Pass |
| --- | --- | --- |
| A0 | Pass-through | iperf ≥ 900 Mbps on 1G; ping ~0.3–1 ms; 0% loss over many pings |
| A1 | OOB isolation | Data ports down; SSH on mgmt still works |
| A2 | Clear | Restores A0 |
| A3 | Crash safety | `systemctl stop eitd` / kill → pass-through |
| A4–A5 | Link down wan/lan | Far side carrier down |
| A6 | Flap | Carrier events on both ends |
| A7–A8 | PHY 100 / 10 | Reported speed and ~90 / ~9 Mbps |
| A9 | Rate 10 Mbit | iperf ≈ 10 Mbps; ethtool still 1G/2.5G |
| A10–A11 | Loss 1% / 10% | Right order of magnitude over ≥1000 packets |
| A12–A13 | Delay 50 / 100+jitter | RTT scales |
| A14 | Delay+loss | Both visible |
| A15 | Unidirectional delay | RTT ≈ one-way, not 2× |
| A16 | Duration expiry | Auto-clear |
| A17 | LLDP pass | tcpdump on far side |
| A18 | Offload sanity | Wrong numbers with TSO on; correct with offloads off |
| A19 | Soak | 30 min iperf pass-through |
| A20 | Reboot | Comes up pass-through |

Unit tests in `tests/` cover command generation and the HTTP API without hardware. `tests/test_netns.py` exercises real netem when run as root.

### B. Tests against the Linux tester (the point of the box)

Pass-through first so “all good” is known. Then inject. **The tester software must report the fault.**

| ID | EIT action | Tester should report |
| --- | --- | --- |
| B1 | Pass-through | Link up, expected speed, ~0 loss, normal RTT |
| B2 | `--link-down lan` | Local link down |
| B3 | `--link-down wan` | Local link may stay up; traffic fails |
| B4 | `--phy-speed 100` | Speed 100, throughput drop |
| B5 | `--rate 10mbit` | Throughput fail; **link still full speed** |
| B6 | Loss 0.1 / 1 / 5 / 10% | Loss in the right ballpark |
| B7 | Delay 20 / 50 / 100 / 200 ms | Latency scales |
| B8 | Jitter | PDV / jitter, not only average |
| B9 | `bad-wan` profile | Multiple alarms |
| B10 | `--loss-pct 100` | Total loss, **link still up** (vs B2) |
| B11 | Clear mid-test | Recovery |
| B12 | Flap | Link-flap events |

B2 vs B10 and B4 vs B5 tell you whether the tester distinguishes carrier from black-hole, and PHY speed from congestion.

Because the tester is Linux, a wrapper is enough:

```bash
eit apply --profile loss-5pct --duration 30
# run the tester's own measurement here
eit clear
```

### C. Calibration (once per board)

- Store pass-through added latency; subtract from delay tests.
- Minimum reliable delay step (~1 ms on ARM).
- Max delay at line rate before drops (queue limit).
- Confirm both PHYs accept forced 10/100.

---

## Concerns and risks

1. **Control-plane lockout** — impairing the only SSH path. USB Ethernet (or a second tester NIC) is required.
2. **netem is egress-only and does not stack** — combined delay+loss+rate is one qdisc; `apply` replaces the previous one.
3. **Hardware offload lies** — TSO/GRO must be off or “10% loss” applies to giant segments.
4. **Asymmetric NICs** on R3S/R6C — test both sides; R5C avoids this.
5. **Linux bridge drops link-local** unless `group_fwd_mask` is set.
6. **No PoE pass-through.**
7. **FCS vs payload corrupt** — do not claim CRC injection.
8. **Timing accuracy** — tens of milliseconds, not PTP.
9. **Link-down is slow** — “down for 10 ms” is not realistic.
10. **Stuck qdiscs** — kernel state survives a killed Python process; systemd `ExecStop` must clear.
11. **EEE / pause** — disable; they add latency and confuse testers.
12. **USB-C is power** on FriendlyElec boards — do not use it as the management NIC.

---

## Assumptions (updated)

- Tester is **software on a Linux computer** (packet/network metrics, not a cable certifier). Confirmed.
- 10/100/1000BASE-T, optionally 2.5G if the board has it.
- UUT/tester are not PoE-powered through this path.
- Size matters; board can be better than an R3S.
- v1 is a lab tool (CLI + HTTP), one tester–UUT pair.

---

## Success criteria

1. Inserting the EIT with no fault does not make a healthy tester fail.
2. Each of the four commanded faults is visible on a reference path (two PCs or netns) with numbers in the right ballpark.
3. The same four faults can be turned on and off while the tester is attached, without losing SSH/HTTP to the EIT.
4. Clear and reboot always return to pass-through.
5. Docs state honestly what the box cannot fake (L1, FCS, PoE, PTP).
