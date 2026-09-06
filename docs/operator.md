# EIT operator sheet

## Hookup

1. Power the EIT.
2. Tester NIC → EIT **lan**. UUT → EIT **wan**.
3. Management: SSH or HTTP to `192.168.50.1` (USB Ethernet) or localhost on the box.
4. Confirm pass-through **before** blaming the tester: `eit status` should show `pass-through`, both links up.

## Commands

From the tester PC (HTTP to eitd) or on the box:

```bash
# Baseline — tester should be green
eit clear
eit status

# The four required faults
eit apply --link-down lan --duration 20          # tester-facing carrier down
eit apply --link-down wan --duration 20          # far-end / UUT-facing down
eit apply --phy-speed 100 --duration 30          # slow the PHY
eit apply --rate 10mbit --duration 30            # slow goodput, link still 1G/2.5G
eit apply --loss-pct 5 --duration 30
eit apply --delay-ms 100 --duration 30

# Combined
eit apply --delay-ms 200 --jitter-ms 50 --loss-pct 2 --rate 2mbit
eit apply --profile bad-wan

# Always recover
eit clear
```

Duration default is 60 s. `0` means until `eit clear`. Forgotten faults auto-expire.

Named profiles: `eit profiles`.

## What the Linux tester should report

Run the tester’s own tests. The tester must be the thing that flags the error.

| EIT action | Tester should see | Different from |
| --- | --- | --- |
| clear / pass-through | Link up, ~0% loss, normal RTT, full throughput | — |
| `--link-down lan` | Local carrier down / “unplugged” | Packet loss with link still up |
| `--loss-pct 100` | Total loss, **link still up** | Link down |
| `--phy-speed 100` | Negotiated 100 Mbps | `--rate 10mbit` (speed still 1G) |
| `--rate 10mbit` | Throughput cap, link speed unchanged | PHY speed change |
| `--delay-ms 50` (both ways) | RTT ≈ 100 ms plus the tiny pass-through constant | Loss |
| `--jitter-ms` with delay | RTT variance | Constant delay |

If pass-through is already red, fix cables/bridge/offloads before injecting faults.

## Safety

- User button (if wired) and `eit clear` restore pass-through.
- `systemctl stop eitd` also clears (ExecStop).
- Reboot comes up with no qdiscs.
- Do not SSH over the data bridge; that path is what you impair.

## Honesty limits

`netem corrupt` is **payload** bit flips, not Ethernet FCS. This tool cannot fake cable certifier measurements (NEXT, TDR, insertion loss) or PoE.
