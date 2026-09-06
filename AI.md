# How this repository was made

This project was designed and implemented with an AI coding assistant. This file records **which model**, **which harness**, and **which prompts** were used, so anyone reading the GitHub repo can see that clearly.

Nothing here is a claim that the code is correct, complete, or production-ready without human review. The on-hardware bring-up (flashing a board, measuring pass-through iperf, driving the real tester) had not been done when this file was written.

## Model

| | |
| --- | --- |
| Model | **Grok 4.6** |
| Vendor | xAI |
| Role | Design (viability + architecture plan) and implementation (Python appliance, OS configs, tests, docs) |

## Harness

| | |
| --- | --- |
| Tool | **Grok Build** |
| Kind | Interactive terminal UI (TUI) / CLI coding agent |
| Install | `https://x.ai/cli/install.sh` (`grok` command) |
| Session style | Human in the loop: prompts, plan approval, then implementation |

The first request ran in **plan mode**: the agent researched hardware and Linux fault-injection (`tc netem`, `ethtool`, bridging), wrote a plan, and waited for approval before editing the repo. After the plan was approved (with comments), the same session implemented the tree, ran unit tests, and iterated on failures.

The agent used local file/shell tools and public web lookups (NanoPi R3S/R5C/R6C specs, netem/bridge behaviour). It did not run the EIT on real dual-NIC hardware.

## Prompts

Prompts below are copied as sent, including typos.

### 1. Original request (plan)

> I need a device that can simulate different netwrok faults. I have a network tester that I need to verify that is able to detect errors. I'm thinking about using a NanoPi R3S as a base as it has two ethernet interfaces. I'm calling this new device an Error Injection Tool, EIT for short. The EIT will be connected between the ethernet tester and the unit under test. On command the EIT should be able to take down the link, slow down the connection, start loosing packages or give high letancy. Create a plan, save it as markdown file. If you have recommendations for test, include those. If you have concerns, include those too. Start by assessing the viability of this project before creating the plan.

### 2. Plan approval (scope changes)

The generated plan was approved with:

> Looks good. The tester is not low level, it is software based and running on a Linux computer. We are not locked into the NanoPi, higher end hardware is within budget, but size matters

That comment is why the software is board-agnostic, why a Linux HTTP/CLI control plane is first-class, and why the hardware note prefers a **NanoPi R5C** (same pocket size as the R3S, dual 2.5G) without dropping R3S support.

### 3. This file

> I am putting this up on github and I want to be transparent in how AI helped genereate this code. Can you make a markdown file where you add some information about the model I used, the harness and the prompt?

## What the model produced

- Viability write-up and architecture: [docs/EIT-plan.md](docs/EIT-plan.md)
- Hardware options: [docs/hardware.md](docs/hardware.md)
- Operator sheet: [docs/operator.md](docs/operator.md)
- Python package `eit` / `eitd` (`src/eit/`)
- systemd, networkd, udev, bring-up scripts (`os/`)
- Unit tests (`tests/`); live netns tests skip unless run as root

## Token cost

Plan and implementation on Grok 4.6, before this file was written:

| | Tokens |
| --- | ---: |
| **Total** | **2,749,028** |
| Input | 2,694,597 |
| Output | 54,431 |

## What still needs a human

- Reviewing and owning the code before you trust it on a bench
- Choosing and cabling a board, including an out-of-band management NIC
- Measuring real pass-through throughput and delay
- Confirming the Linux tester actually flags each injected fault
