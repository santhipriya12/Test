---
name: trader-alerts
description: >-
  Price Alerts for NSE. Rings when a price, a stop or the opening bell hits.
  Turns the trade plan into three alerts in one go (the stop, the target and
  "flat by close" at your flat-by time), plus above / below / stop / target
  levels, percent moves from the previous close, any time of day, and NSE's
  9:15 opening bell, each ringing once so you are not spammed. Knows NSE
  hours (09:15 to 15:30 IST) and the 2026 NSE holidays (more in
  trader/holidays.json), works out India time itself, fetches free delayed
  quotes (Yahoo chart JSON, .NS symbols) one stock at a time, and writes
  trader/prices.json for sizing and the risk check. Use when the user says
  "alert me when", "tell me if RELIANCE hits", "watch my stop", "watch my
  trade", "remind me to square off by 3", "is the market open", "when does
  the market open", "get me a price", or right after /trader-exit writes a
  plan.
argument-hint: "[NSE symbol] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when a stop alert rings,
nothing is sold by this skill. The SL-M stop the user placed in Groww does
the stopping; the alerts tell the user what happened, when the target is
reached (time to cancel the SL-M and sell) and when it is time to be flat.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat by close from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1358.30
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 1375.90
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:00 --label "flat by close"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol INFY --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write         # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan symbols
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-11-12 15:00"` pins the clock (India time, IST); `--offline DIR`
reads saved quote files instead of the network.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest quotes, merged in, for trader-budget and trader-risk |
| `trader/portfolio.json` | the symbols held, for `quote --holdings` |
| `trader/holidays.json` | optional: extra NSE holidays, `{"2027-01-26": "Republic Day"}` |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the India clock (IST) passed `at` ("15:00") on a trading day | once per trading day |
| `opening_bell` | NSE is open | once per trading day |

A rule with `"date"` is watched on that India date only; `--from-plan` rules
carry the plan's date, so yesterday's stop never rings today.

## Quotes

- `yahoo`: `query2.finance.yahoo.com/v8/finance/chart/RELIANCE.NS` (an NSE
  symbol gets `.NS`; `.BO` reads BSE), an unofficial free JSON endpoint, one
  request per symbol, half a second apart. On a 429 it waits and tries once
  more; on a 429 or a 5xx after that it tries `query1`.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts
  and for checking a size, not for timing an order. The exchange's price is
  the one that fills; Groww's app shows the live one. Each price in
  `trader/prices.json` keeps its quote time, and trader-risk only uses one
  under 15 minutes old.
- If Yahoo is down, ask the user for the price Groww shows and write it into
  `trader/prices.json` as `{"as_of": "...Z", "prices": {"RELIANCE": 1366.40}}`.

## The NSE clock

Normal market 9:15 a.m. to 3:30 p.m. India time (IST, UTC+5:30, no daylight
saving), after the 9:00 to 9:08 pre-open auction. Closed on weekends and on
NSE trading holidays. The 2026 list is built in (from an open-source NSE
library, not read from nseindia.com: check it against NSE's own holiday
page); later years and any corrections go in `trader/holidays.json`. For a
year it does not know, the clock says the holiday list is unknown. NSE has
no regular half days; the Diwali Muhurat session is a separate evening
session these tools do not trade.

## Steps

1. Right after trader-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by time.
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. Each run fetches only the symbols in today's
   rules and rings each alert once. A check reads the latest delayed quote;
   it is not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang in one line each. A stop alert means the SL-M has
   probably filled: ask the user to check Groww and record the fill with
   trader-broker. A target alert means: cancel the SL-M in Groww first, then
   sell (trader-broker). "Flat by close" means close anything still open:
   trader-broker `flatten`, then trader-risk, then the user's yes. Never act
   for them.

## Example (illustrative)

RELIANCE on Thursday 2026-11-12: entry 1,364.18 at 9:55 AM, stop 1,358.30,
target 1,375.90, flat by 15:00. `add --from-plan` writes
`reliance-plan-stop`, `reliance-plan-target` and `reliance-flat-by` for that
day. A `check` at 10:30 with the quote between the stop and the target says
nothing hit. At 3:00 PM:

```
ALERT Flat by close: it is 15:00 IST (set for 15:00), the market closes at 15:30. If RELIANCE is still
open, close it: trader-broker flatten --symbol RELIANCE builds the sell ticket, then trader-risk and your yes.
```

It rings once. The next morning the plan's three alerts are no longer
watched; with `add --opening-bell`, the bell rings at 9:15.

## Rules

- An alert is a fact about a price or the clock. Say it as a fact.
- Never present a quote as live. Free quotes are delayed and unofficial.
- Confirm every new rule back to the user: ticker, type, level, day.

## What it never does

It never places, cancels or changes an order, never claims a quote is
live, and never predicts where a price is going.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
