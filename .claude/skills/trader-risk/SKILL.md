---
name: trader-risk
description: >-
  Risk Manager. Checks every trade against your limits and stops anything
  over them, before it can reach Groww. For a day trade: a stop is
  required, the loss at the stop must fit your max loss per trade (measured
  from the higher of the plan's entry and a fresh price), reward:risk must
  meet your minimum, the day's total risk must fit your daily loss limit, no
  more than your trades per day, and no new entries outside your entry
  window or when the market is closed. It also keeps the basics: blocked
  symbols, order size, position cap, cash buffer, margin, short sales, F&O,
  malformed or bad bracket orders (whole shares, MIS / CNC, DAY / IOC),
  duplicates and a daily order limit. Getting out is never blocked by a day limit. Prints PASS or
  BLOCK with the reason and records the verdicts so trader-broker only shows
  an order that passed. Use when the user says "check my order", "is this
  safe", "risk check", "does this break my rules", "can I take this trade",
  "how much have I risked today", or before /trader-broker, always.
argument-hint: "[path to orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposal and the broker. Every order
written by trader-budget or trader-broker's flatten passes through it. A
BLOCK is final for that order: it does not go to the user for a yes, and it
does not go to Groww. Most individual intraday traders in India lose money. These limits
keep each loss and each day's losses small. They do not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                           # trader/ files; writes trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write                # look without recording
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-11-12 10:00"  # pin the clock (IST)
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget, or trader-broker's flatten) |
| `trader/config.json` | the limits (trader-budget ships `config.example.json`) |
| `trader/portfolio.json` | cash and holdings; if missing, a fresh account funded with the budget |
| `trader/prices.json` | a fresh price raises the entry it measures risk from; also values holdings |
| `trader/state/broker.json` | what was placed today: duplicates, trades per day, daily loss, day trades |
| `trader/state/risk.json` | the verdicts it writes, with a fingerprint of each exact order |

## Entries and exits

An **entry** opens or adds to a position: a buy, or a sell that would go
short. An **exit** only reduces what you already hold. Getting out must
always be possible, so an exit is checked for format, asset and short sales
only. Every other rule (day limits, entry window, loss, reward:risk, blocked
list, size, duplicates) turns into a warning for an exit, never a BLOCK.

## The checks

Orders are checked in file order, as if each passed order had filled, so a
batch that is fine order by order but breaks a limit together is caught.

| check | blocks when |
| --- | --- |
| format | no symbol, side not buy or sell, no whole-share `qty` (NSE has no rupee-amount or fractional orders), a limit order with no limit price, validity other than `day` / `ioc`, product other than `MIS` / `CNC`; a bracket that is not `day` or misses its stop-loss or take-profit |
| asset | an F&O contract (NIFTY26NOV24000CE, RELIANCE26NOVFUT) while `allow_options` is false; anything that is not an NSE / BSE stock symbol |
| short | a sell of more than you hold (`allow_short` false) |
| blocked | (entries) the ticker is on the `blocked` list |
| size | (entries) under `min_order_inr` or over `max_order_inr` |
| position | (entries) the stock would be over `max_position_pct` of the account |
| cash | (entries) the buy would leave less than the cash buffer, or need margin |
| stop | (entries) no stop while `require_stop` is true (a bracket `stop_loss_stop_price`, or the order's plan stop); a stop on the wrong side of the entry |
| loss | (entries) qty x (entry minus stop) over `max_loss_per_trade_inr` |
| reward:risk | (entries) (target minus entry) / (entry minus stop) under `min_reward_risk` |
| daily loss | (entries) the max losses at the stops of today's entries, plus this one, over `max_daily_loss_inr` |
| trades | (entries) `max_trades_per_day` entries already placed today |
| window | (entries) before `no_entries_before` or after `no_entries_after`, or the market is closed |
| pdt | (entries, only with `pdt_guard` true) a US rule; leave it off for NSE |
| duplicate | (entries) the same symbol and side twice in one batch, or already placed today |
| daily limit | (entries) `max_orders_per_day` orders already placed today |

How the numbers work:

- **The entry it measures from**: the limit price for a limit order. For a
  market order, the HIGHER of the plan's entry and a fresh price from
  `trader/prices.json` (under 15 minutes old). A plan written at 9:55 cannot
  understate the risk at 10:30 after the price ran up. An older price is not
  used, and it says so.
- **Daily loss** counts the full max loss of every entry placed today, win or
  lose, as trader-broker logged it. Three full-size trades at a Rs 1,000 max loss use up a Rs 3,000 day.
- **The window** is India time (IST, UTC+5:30), worked out in the tool, never
  from the computer's clock zone. Defaults: no entries before 09:30 (the
  opening range) or after 14:30 (time to work the trade before the intraday
  square-off). Outside 09:15 to 15:30, on weekends and on NSE holidays the
  market is closed. Set both `no_entries_*` to null to switch the window off.
- **Intraday margin.** Groww may let an MIS order use leverage. This check
  measures cash against the full order value: with `allow_margin` false,
  a buy bigger than your cash is blocked, leverage or not.
- **Circuits.** NSE stops a stock at its price band (upper / lower circuit).
  An entry near the band can fill badly or not at all, and a stop can be
  stuck behind a locked lower circuit. Say so when the quote is near a band.

Warnings do not block, but say them to the user: a LIVE account, a stop that lives only in the plan and
not at the broker, a price too old to use, a holiday list that does not cover today's year.

## Steps

1. If the price may have moved since the plan, refresh it first
   (trader-alerts: `alerts.py quote RELIANCE --write`).
2. Run `check.py`. Exit code 0 means every order passed, 1 means at least one
   was blocked.
3. Tell the user the result in plain words, order by order: the max loss at
   the stop, reward:risk, and how much of today's limits it uses. For a
   BLOCK, give the reason and the fix (fewer shares, a closer stop from
   trader-exit, wait for the window, or skip the trade). Never change a
   limit yourself.
4. If the order changes in any way, run the check again. trader-broker matches
   each order to its verdict by fingerprint, so an edited order is not ready
   until it passes again, and a verdict from yesterday does not count today.

## Example (illustrative prices, real output)

The RELIANCE bracket from trader-budget at 9:57 AM on Thursday 2026-11-12, on
a fresh Rs 2,00,000 paper account with the example config:

```
PASS  #1 buy RELIANCE 73 shares, entry
          entry 1364.18 (the plan's entry), stop 1358.30, target 1375.90: risk 5.88 a share
          max loss Rs 429.24 (limit Rs 1,000), reward:risk 1.99 (min 1)
          today before this: 0 of 3 trades, Rs 0 of Rs 3,000 daily loss

1 passed, 0 blocked at 2026-11-12 09:57 IST. Cash after the passed orders: Rs 100,414.86 (paper account).
```

The same order at 9:20 is blocked by the window (no new entries before
09:30), and on 2026-11-24 by the NSE holiday. The 15:00 sell that closes the
position passes even though it is after the 14:30 entry cutoff: it is an exit.

## Rules

- A PASS only means the order is allowed to be shown to the user. It is not a yes.
- Every number comes from the config, the order, the portfolio, the prices or the broker log.
- Free Yahoo prices are unofficial and can lag; the exchange's price is the one that fills, and a
  stop can fill worse than its price in a fast market.

## What it never does

It never places an order, never edits an order to make it pass, never
loosens a limit, never blocks a sell that only gets the user out, and never
treats a PASS as the user's yes.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
