---
name: trader-exit
description: >-
  Exit Planner. Sets your stop and your target before you enter, so you know
  when to get out. Reads the entry from trader-entry (or a price you give),
  puts the stop at the opening-range midpoint by default (or the range low,
  your price, a percent, or a multiple of the ATR), rounds it down to NSE's
  tick size, and sets the target at 2R (or 1R, or your price). Refuses a stop at or
  above the entry, a target at or below it, or a stop too tight to survive the
  spread, and says why. Writes trader/plan.json for the Time Machine, the
  Budget Manager and Price Alerts. Long side only. Use when the user says
  "where's my stop", "set my stop and target", "plan the exit", "when do I get
  out", "stop loss", "what's my R", "risk reward", or right after
  /trader-entry triggers, before /trader-timemachine.
argument-hint: "[--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]"
---

# trader-exit

The Exit Planner decides how a trade ends before it starts. The stop is where
the setup has failed. The target is where you take what you came for. Both
are set BEFORE the entry, written down and handed on, so nobody has to decide
anything in the middle of a fast move. A stop is a plan, not a guarantee: a
gap or a fast market can fill past it. Most individual intraday traders in
India lose money, and a neat plan does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                          # trader/entry.json: midpoint stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:1.5           # needs the session's bars (Yahoo or --offline)
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 1364.18 --or-high 1362.18 --or-low 1354.47
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                          # the current trader/plan.json
```

Other flags: `--flat-by 15:00`, `--json`, `--now "2026-11-12 10:00"` (India
time, IST), `--entry PRICE` with a waiting entry.json to plan ahead, `--setup
level`, `--offline FILE` (a saved Yahoo chart JSON for an ATR stop).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the trigger from trader-entry: symbol, entry price, time, bar, opening range |
| `trader/config.json` | `flat_by` (15:00), `min_reward_risk` (1.0: a note here, trader-risk enforces it) and `tick_size` (optional override) |
| Yahoo chart API | only for an `atr:K` stop: the session's bars up to the entry bar, free and unofficial |
| `trader/plan.json` | with `--write`: entry, stop and its rule, target and its R, risk a share, reward:risk, flat by. trader-timemachine, trader-budget and trader-alerts read it |

## Stops and targets

| stop | where it goes |
| --- | --- |
| `or-mid` | the opening-range midpoint (the default for an opening-range breakout) |
| `or-low` | the opening-range low: wider, so fewer shares for the same max loss |
| `price:X` | your price |
| `pct:X` | X percent under the entry |
| `atr:K` | K times the 14-bar ATR under the entry, on the session's bars up to the entry bar. With fewer than 14 bars by then it averages all of them and says so |

A level setup has no opening range to lean on, so it needs a stop you name.

- **Rounding to NSE's tick.** NSE rejects an order price that is not a
  multiple of the stock's tick size, so the stop rounds AWAY from the entry
  to the tick (down, for a long) and the target rounds half up to it. Ticks
  by price (NSE, 2025): under Rs 250 Rs 0.01; Rs 250 to 1,000 Rs 0.05;
  Rs 1,000 to 5,000 Rs 0.10; Rs 5,000 to 10,000 Rs 0.50; Rs 10,000 to
  20,000 Rs 1; above that Rs 5. `"tick_size": 0.05` in the config forces one
  tick (if NSE or Groww shows a different one for a stock, use theirs).
  Risk = entry minus stop. Target = entry + R x risk. `2R` by default; `1R`, `1.5R` or `price:X` also work.
- **Refused, with the reason.** A stop at or above the entry. A target at or
  below it. A risk under 0.05% of the price: too tight to survive the
  spread, normal wiggle would stop you out. An entry.json that has not
  triggered (unless you give `--entry`). A short: this pack plans longs only.
- **Flat by.** 15:00 IST by default (or `flat_by` in the config). Out by
  then, win or lose, no overnight hold, and before Groww's own intraday (MIS)
  auto square-off near the close, which comes with a charge. An entry at or
  after the flat-by time is refused.

## Steps

1. Run it right after `/trader-entry` triggers. Before that, `--entry PRICE`
   plans ahead at the level you expect.
2. Use the default stop for an opening-range breakout unless the user names
   another. A level setup needs one: ask.
3. Run `exit.py plan --write`. Read back the entry, the stop and its rule,
   the target and its rule, the risk a share, reward:risk and flat by.
4. If it refuses, say the reason and the fix (a wider stop, a farther
   target). Never loosen anything on your own.
5. Say once that the stop is a plan, not a guarantee.
6. Hand off to `/trader-timemachine` to replay the plan, then `/trader-budget`
   to size it to the max loss per trade. Offer `/trader-alerts` for the stop,
   the target and the flat-by time. Claude can keep `entry.py watch` running
   in the background or on a `/loop` until a setup triggers, then come here.

## Example (illustrative)

RELIANCE, Thursday 2026-11-12. The entry is 1,364.18 at 9:55 AM (the 9:50
bar) and the opening range is 1,354.47 to 1,362.18. `exit.py plan --write`:

```
Exit plan: RELIANCE long, Thu 2026-11-12, opening-range breakout on 5-minute bars
  Entry         Rs 1,364.18
  Stop          Rs 1,358.30  opening-range midpoint: (Rs 1,362.18 + Rs 1,354.47) / 2 = Rs 1358.325, rounded down to the Rs 0.1 tick
  Target        Rs 1,375.90  2R (two times the risk)
  Risk a share  Rs 5.88 (0.43% of the entry)
  Reward:risk   1.99
  Flat by       15:00 IST, win or lose: no overnight hold
```

The target 1,364.18 + 2 x 5.88 = 1,375.94 rounds to the Rs 0.10 tick:
1,375.90. trader-budget then sizes it to the max loss per trade.

## Rules

- The stop and the target are set before the entry, never after.
- Never move a stop further from the entry once the trade is on.
- Plain numbers only: entry, stop, target, risk a share, reward:risk. It
  never prints a P&L or a return.
- Nothing here promises winning trades or money. A 1R target is not a
  prediction that the price gets there.
- Long side only. This pack plans longs only.

## What it never does

It never places an order, never sizes a position, never widens a stop to
make a plan pass, and never calls a stop a guarantee.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
