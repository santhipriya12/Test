---
name: trader-budget
description: >-
  Budget Manager. Sizes every position to your budget and your max loss per
  trade, in rupees. Reads the trade plan from trader-exit (entry, stop,
  target), finds the whole shares that fit inside four limits (max loss per
  trade, position cap, max order, cash after your buffer), says which limit
  decided it, and writes ONE intraday bracket order (NSE, MIS: entry,
  stop-loss, target) to trader/orders.json for trader-risk and the Groww
  ticket. A stop too far away for your max loss is a plain refusal, not a
  smaller order. Nothing is placed. Use when the user says "how many
  shares", "size this trade", "how much should I buy", "I have Rs 2 lakh",
  "I only want to risk Rs 1,000 a trade", "set my rules", "keep 10% in
  cash", or after /trader-exit writes a plan.
argument-hint: "[budget in rupees]"
---

# trader-budget

The Budget Manager turns a plan ("buy RELIANCE at 1,364.18, stop 1,358.30")
into an exact order ("buy 73 shares"), inside rules the user sets once. The
stop decides the size: the further away the stop, the fewer shares. It
writes a proposal only. trader-risk checks it and trader-broker asks the
user yes or no. Most individual intraday traders in India lose money.
Sizing to a max loss keeps each loss small; it does not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                         # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                 # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write         # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 1364.00 --json  # a limit order at 1,364.00
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights TCS=40,INFY=60 --config split.json   # weights mode, below
```

`--now "2026-11-12 10:00"` pins the clock (India time, IST). A plan for
another day is refused: make a new one with trader-exit.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the rules (start from `config.example.json` in this folder) |
| `trader/plan.json` | the trade: entry, stop, target, setup, flat-by time (trader-exit writes it) |
| `trader/prices.json` | optional: a fresh price above the plan's entry means a bigger risk (trader-alerts writes it) |
| `trader/portfolio.json` | optional: its cash caps the size (trader-broker keeps it) |
| `trader/orders.json` | the one proposed bracket order it writes with `--write` |

## Step 1: set the rules once

If `trader/config.json` does not exist, copy `config.example.json` into
`trader/config.json` and ask the user for each value in plain words. All
amounts are rupees.

- **budget**: how much money this is for. Only money they can afford to lose.
- **cash_buffer_pct**: how much always stays in cash (default 10).
- **max_loss_per_trade_inr**: the most one trade may lose if the stop fills at the stop (default 1,000).
- **max_position_pct**, **max_order_inr**, **min_order_inr**: the biggest position (75% of the
  budget), the biggest order (Rs 1,00,000) and the smallest order (Rs 500).
- The day limits trader-risk enforces: **max_daily_loss_inr** (3,000), **max_trades_per_day** (3),
  **min_reward_risk** (1.0), **require_stop** (true), **no_entries_before** / **no_entries_after**
  ("09:30" / "14:30") and **flat_by** ("15:00"), all IST.
- **exchange** ("NSE") and **product** ("MIS", intraday; "CNC" is delivery).
- **blocked**: symbols they never want to trade.
- Keep **paper** true until they have watched it work in practice mode.

Groww may offer leverage on intraday (MIS) orders. This sizing does not use
it: the cash limit is the full order value. Leverage makes a bad day worse.

## Step 2: size the trade

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
```

It refuses, and writes no order, when: the size is zero shares, the order is
under the minimum, reward:risk is under `min_reward_risk`, the stop is not
below the entry, the target is not above it (the move already happened), the
plan is for another day, the symbol is blocked, or the plan is a short. Say
the reason to the user in one line.

## Step 3: show the user

Show the four limits, which one decided the size, the shares, the rupees
and the max loss at the stop. Say plainly that a stop is an order, not a
promise: in a fast market it can fill below the stop. Then hand over to
`/trader-risk`.

## Example (illustrative prices, real output)

RELIANCE on Thursday 2026-11-12. Opening-range breakout: entry 1,364.18 at
9:55 AM, stop 1,358.30 (the opening-range midpoint, on the tick), target
1,375.90 (2R). Risk 5.88 a share. The example config: Rs 2,00,000 budget,
10% cash buffer, Rs 1,000 max loss, Rs 1,00,000 max order.

| limit | the math | shares |
| --- | --- | --- |
| max loss | Rs 1,000 / 5.88 | 170 |
| position cap | 75% of Rs 2,00,000 = Rs 1,50,000 / 1,364.18 | 109 |
| max order | Rs 1,00,000 / 1,364.18 | **73 (decides it)** |
| cash | Rs 2,00,000 minus Rs 20,000 = Rs 1,80,000 / 1,364.18 | 131 |

73 shares = Rs 99,585.14. Max loss at the stop: 73 x 5.88 = Rs 429.24. It writes:

```json
{"symbol": "RELIANCE", "exchange": "NSE", "side": "buy", "qty": "73", "type": "market",
 "time_in_force": "day", "product": "MIS", "order_class": "bracket",
 "take_profit_limit_price": "1375.90", "stop_loss_stop_price": "1358.30",
 "why": "opening-range breakout on RELIANCE: 73 shares, bound by your max order (73 x 5.88 = Rs 429.24 at the stop)",
 "plan": {"entry": 1364.18, "stop": 1358.3, "target": 1375.9, "risk_per_share": 5.88, "max_loss": 429.24, ...}}
```

`why` and `plan` are notes for trader-risk and trader-broker; the Groww
ticket shows the rest. With the stop at 1,300.00 instead, one share would
risk 64.18: 15 shares for the Rs 1,000 max loss. A fresh quote above the
plan's entry in `trader/prices.json` raises the risk a share and can make
reward:risk fall under the minimum: then it refuses, because the move it was
waiting for has mostly happened.

## Weights mode

`--weights HDFCBANK=28,RELIANCE=24` or `--targets FILE` (`targets.example.json`
here) splits a budget across a list by weight, as delivery (CNC) buys: the
cash buffer comes off the top, weights are renormalised to 100, any stock
over `max_position_pct` is pinned at the cap and its excess shared out,
slices under the minimum order are dropped. NSE trades whole shares only, so
it needs prices (`--prices trader/prices.json`, from `alerts.py quote ... --write`).
These are plain buys with no stop: trader-risk blocks them while
`require_stop` is true. Use a separate config (`--config`) for a long-term split.

## Rules

- Proposals only. This skill never places anything.
- Never size money the user has not said is for this. Ask for the budget and the max loss.
- Every number comes from the config, the plan or the prices. Nothing is guessed.
- No projections: never say what a trade will make. A target is a plan, not a forecast.
- Free Yahoo prices are unofficial and can lag. The exchange's price is the one that fills.

## What it never does

It never places, approves or schedules an order, never raises a limit on its
own, never shrinks a stop to fit more shares, and never sizes options,
margin or short positions.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
