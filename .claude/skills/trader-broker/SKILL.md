---
name: trader-broker
description: >-
  Order Executor for Groww. Turns an approved order into a plain Groww order
  ticket (NSE, Intraday / MIS, quantity, market or limit, plus the SL-M
  stop-loss and the target) and the exact steps to enter it in the Groww
  app. Practice (paper) mode by default, never without your yes, and Claude
  never places the order itself: you enter it in Groww. Records your yes
  word for word, the Groww order id and the fill, builds the sell ticket
  that closes a day trade by your flat-by time (before Groww's intraday
  auto square-off), and logs each trade's max loss so trader-risk can hold
  the daily limit. Use when the user says "place the order", "buy it",
  "execute", "send it to Groww", "close my position", "square off",
  "flatten", "get me out", "record my fill", or after /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Executor is the last step before a real order, so it is the
strictest. An order reaches the market only after three separate gates,
every time, for every order:

1. **trader-risk passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user enters it in the Groww app themselves.** Claude has no Groww
   connection and never asks for one: no login, no PIN, no OTP, no API key.

Two yeses from the user (one in the chat, one in their own Groww app), one
PASS from the rules. No yes, no order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id 2611110012345 --filled-qty 8 --filled-price 1364.20
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 8 --price 1375.90
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 8
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets with the Groww
steps, checks that a reply is a real yes for that order, builds the flatten
ticket, and keeps the log in `trader/state/broker.json`.
`--now "2026-11-12 10:15"` pins the clock (India time, IST).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `fill` and by `result --filled-qty` |
| `trader/plan.json` | the flat-by time for `flatten` |

## Practice first

`"paper": true` in `trader/config.json` (the default) means practice: the
ticket says **do not enter this in Groww**, and the trade is recorded with
`--broker-id PAPER` and a fill at the live price (from `/trader-alerts`
quotes). Groww has no paper-trading account, so practice lives in these
files. Going live is the user's own change to their own config. Never switch
it for them.

## The Groww order, in Groww's terms

trader-budget writes an intraday bracket: buy N shares, a stop-loss and a
target. In the Groww app that is:

1. **The entry.** Stocks > search the symbol > Buy. Exchange **NSE**,
   **Intraday** (MIS), quantity N, **Market** (or **Limit** at the ticket's
   price).
2. **The stop, straight after the entry fills.** Sell N, Intraday, order type
   **SL-M** (stop-loss market), trigger price = the ticket's stop. This is the
   order that actually protects the trade.
3. **The target.** `/trader-alerts` rings when the price reaches it. Then
   **cancel the SL-M first**, and only then sell N at market or at a limit at
   the target. Never leave the SL-M and a target sell both open on the same
   shares: if both filled, an intraday account would be left short.
4. If Groww's order screen offers a stop-loss and a target on the order
   itself (one cancels the other), the user can set both there instead of
   steps 2 and 3. Groww's screens change: if a word on the ticket does not
   match the app, ask the user what they see rather than guessing.

NSE rejects order prices that are not on the stock's tick (trader-exit
already rounds the stop and the target to it).

**Groww squares off open intraday positions itself** shortly before the
close, with a charge. `flat_by` (default 15:00 IST) gets the user out on
their own terms before that; the exact auto square-off time is in the
Groww app.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT
   READY or BLOCKED goes back to `/trader-risk`.
2. Show ONE ticket and ask: "Approve this order? Reply yes or no." One order
   per question. Never offer "yes to all".
3. Run `ticket.py approve --index N --reply "<the user's reply, word for word>"`.
   If it prints "Not recorded", the reply was not an explicit yes for this
   order (for example "sure", "yes to all", or a yes that names a different
   stock or amount). Ask again. Never turn a reply into a yes yourself.
4. After "Recorded your yes", it prints the Groww steps. Give them to the
   user. The user enters the order in Groww (or, in practice mode, does not).
5. Record what happened when the user reports back: `ticket.py result --index N
   --status placed --broker-id <Groww order id> --filled-qty Q --filled-price P`,
   or `--status denied` (they changed their mind), or `--status failed` with
   `--note` (Groww rejected it: say why, e.g. insufficient margin, price
   outside the circuit). A failed order is not retried without a new check and
   a new yes. The log keeps the entry's max loss for trader-risk's daily limit.

## Steps: while it is open, and out by the close

- trader-alerts watches the stop, the target and the flat-by time
  (`alerts.py add --from-plan`). The SL-M in Groww does the stopping.
- When the SL-M or the target sell fills, record it:
  `ticket.py fill --symbol RELIANCE --side sell --qty 8 --price 1358.30`.
- By `flat_by` (15:00 IST), anything still open gets closed:
  1. Ask the user how many shares Groww shows (Positions > Intraday).
  2. `ticket.py flatten --symbol RELIANCE --qty 8` writes a market sell for
     those shares to `trader/orders.json`.
  3. `/trader-risk`. A sell that only closes what the user holds is never
     blocked by the daily limits or the entry window.
  4. `ticket.py show`, then the user's yes for that one order, as above.
  5. In Groww: cancel the open SL-M first, then sell. Then `result`.

## Example

```
ORDER 1 of 1, PRACTICE (paper), Groww
  BUY 8 RELIANCE on NSE, Intraday (MIS), market, validity DAY
  stop-loss 1358.30
  take-profit 1375.90
  max loss about Rs 47.04 if the stop fills at 1358.30 (it can fill worse in a fast market)
  why: opening-range breakout on RELIANCE: 8 shares, bound by your ... (8 x 5.88 = Rs 47.04 at the stop)
  READY: trader-risk PASS, waiting for your yes
  Reply "yes" to approve this one order, or "no" to skip it.
```

The user replies "yes". Claude records it and gives the Groww steps: in
practice mode the trade is recorded as a paper fill; live, the user taps
Buy in Groww, then sets the SL-M, and reports the order id and fill price.

## What it never does

- Never places, modifies or cancels an order itself, and never logs in to Groww.
- Never asks for, reads, stores or repeats a Groww password, PIN, OTP or API key.
- Never treats two orders as approved on one yes.
- Never runs orders from a scheduled or background task: nobody is there to say yes.
- Never switches `"paper"` to live. The user does that themselves.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
