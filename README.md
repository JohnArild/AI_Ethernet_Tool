# Error Injection Tool (EIT)

Inline Ethernet fault injector. Sits between a **Linux software network tester** and a unit under test, and on command takes the link down, slows the path, drops packets, or adds latency.

The software is **board-agnostic**: any Linux box with two data NICs (plus a third interface or UART for control) will do. Size is the hardware constraint; see [docs/hardware.md](docs/hardware.md).

```text
[ Linux tester PC ] ---- [ EIT dual-NIC Linux box ] ---- [ UUT ]
        NIC                    lan            wan
        USB/UART/3rd NIC ---- management
```

Default state is transparent pass-through.

## Quick start (development)

```bash
PYTHONPATH=src python3 -m eit --help
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
```

Talk to a running daemon:

```bash
eit apply --profile loss-1pct --duration 30
eit apply --delay-ms 100 --jitter-ms 20 --loss-pct 1
eit apply --link-down wan
eit apply --phy-speed 100
eit apply --rate 10mbit
eit status
eit clear
```

`--direct` applies `ip`/`tc`/`ethtool` on the local host (needs root). Without it, the CLI talks to `eitd` at `http://127.0.0.1:8080`.

## Appliance install

On the dual-NIC Debian/Ubuntu box:

```bash
sudo ./os/install.sh
# set MAC names in /etc/udev/rules.d/99-eit-nics.rules
sudo eit-bringup eit-lan eit-wan
sudo systemctl start eitd
eit status
```

## Docs

- [Plan (viability, architecture, tests, concerns)](docs/EIT-plan.md)
- [Hardware choices](docs/hardware.md)
- [Operator cheat sheet](docs/operator.md)
- [How AI was used (model, harness, prompts)](AI.md)
