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

## Session token usage

Figures come from Grok Build’s session log (`turn_completed` usage records) for session `01a06ff9-0916-74f1-95fd-d1b83c5f24e4`. They cover **four finished prompts** and **38 model calls** on `grok-4.6`. They **do not** include the prompt that added this section and pushed it.

Input totals include prompt-cache reads. Uncached input is input minus cache reads. There was no compaction.

| | Tokens |
| --- | ---: |
| **Total** | **4,713,890** |
| Input | 4,653,814 |
| of which cache reads | 4,000,896 |
| uncached input | 652,918 |
| Output | 60,076 |
| of which reasoning | 47,912 |

Per finished prompt:

| Prompt | Input | Cache reads | Output | Reasoning | Model calls | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Plan and implementation | 2,694,597 | 2,199,424 | 54,431 | 43,609 | 25 | 2,749,028 |
| Write `AI.md` | 723,526 | 588,416 | 2,421 | 2,172 | 5 | 725,947 |
| Commit and push `AI.md` | 442,216 | 440,960 | 383 | 247 | 3 | 442,599 |
| “How many tokens did this session use?” | 793,475 | 772,096 | 2,841 | 1,884 | 5 | 796,316 |

When those four prompts had finished, the live context window was about **169k / 500k** (33%). That is how much was in memory, not how much the session used in total.

## What still needs a human

- Reviewing and owning the code before you trust it on a bench
- Choosing and cabling a board, including an out-of-band management NIC
- Measuring real pass-through throughput and delay
- Confirming the Linux tester actually flags each injected fault
