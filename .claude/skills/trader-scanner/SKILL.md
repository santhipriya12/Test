---
name: trader-scanner
description: >-
  Chart Scanner for NSE. Scans thousands of Indian stock charts for setups:
  opening-range breakouts, flags, oversold bounces. Builds the list of NSE
  stocks you can trade intraday (EQ series) from NSE's own equity list, runs
  a pre-market scan of daily closes (20-day closing-high breakout, bull flag,
  reclaimed the 20-day average, oversold, oversold bounce) and an intraday
  opening-range breakout scan on 5-minute bars from 9:15 IST, then writes
  trader/watchlist.json for trader-news and trader-entry. Free Yahoo data
  (.NS symbols), bar by bar. Use when the user says "scan the market", "find
  me setups", "what is breaking out", "opening range breakouts", "scan for
  bull flags", "oversold stocks", "pre-market scan", "build my watchlist",
  "what should I look at today", or at the start of a trading day before
  /trader-news.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads thousands of
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. SEBI's own studies found that most
individual intraday traders in India lose money; the scanner does not change
that. It only saves you from flipping through 2,000 charts by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                              # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                                 # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS,INFY     # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                                   # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:00                        # cut the clock at 10:00 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

Flags: `--min-price 50` (rupees) and `--min-volume` (daily 500,000 shares,
orb 0), `--or-minutes 15`, `--max-confirm 200` (orb stage 2),
`--now "2026-11-12 10:00"` (India time, IST) to pin the clock,
`--offline PATH` to read saved files, `--no-write`, `--show N`, `--json`.
Exit code 0 when the scan found something, 1 when it found nothing or could
not run (the reason is one plain line).

Symbols are NSE symbols (RELIANCE, M&M, BAJAJ-AUTO). The tool adds `.NS` for
Yahoo; a symbol ending in `.BO` is read from BSE instead.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-news and trader-entry read `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 14:30) |
| `trader/holidays.json` | optional: extra NSE holidays, `{"2027-01-26": "Republic Day"}` |

## The universe

`universe` downloads NSE's list of listed equities, `EQUITY_L.csv`, from
`nsearchives.nseindia.com/content/equities/` (archives.nseindia.com as a
fallback) and keeps the **EQ series** only: the stocks that can be bought and
sold the same day. BE and BZ (trade-for-trade, delivery only), SME and
anything else are out, because they cannot be traded intraday. That is about
2,000 stocks.

NSE sometimes refuses scripts. If `universe` cannot download the file, the
user downloads EQUITY_L.csv in a browser (nseindia.com > Market Data >
Securities available for trading) and runs
`scan.py universe --offline EQUITY_L.csv`.

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so 2,000
symbols take about 100 requests (a minute or so with the polite pause).
Liquidity comes from the spark meta: last price at least `--min-price` and
last session's volume at least `--min-volume`. Run it before 9:15 or after
15:30 IST: during the session the volume is the day's so far, and today's
daily bar is left out until the close.

The setups are computed from daily closes only (spark has no highs or lows):

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

Hits are listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

NSE's normal market opens at 9:15 IST (after the 9:00 to 9:08 pre-open
auction). The opening range is the first `--or-minutes` (15) of the session:
the 9:15, 9:20 and 9:25 five-minute bars. A hit is the first completed
5-minute bar to CLOSE above the range high, at that bar's close time.

1. Stage 1, every symbol: spark closes of today's 5-minute bars, 20 a
   request. A chart goes on only if a completed bar after the range closed at
   or above the highest close of the range. That is a necessary condition, so
   no breakout is lost.
2. Stage 2, each candidate: the v8 chart with real highs and lows, one
   request each. Range high = the highest high of the range bars, range low =
   the lowest low. Stage 2 checks at most `--max-confirm` (200) candidates,
   the most traded first, and prints PARTIAL with the count it skipped.
   `--max-confirm 0` checks them all.

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there; a missing bar means a circuit freeze or a thin stock. A stock locked
at its upper or lower circuit stops trading: its chart can look like a
breakout that nobody can buy. Null closes are dropped, a bar off the
5-minute grid (the live tick) is dropped, and a bar counts only once it is
complete. Before 9:35 AM, on a weekend or NSE holiday, after the close, or
after `no_entries_after` it prints one plain line and writes nothing.

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag (Indian
  quotes on Yahoo can be delayed). Bars are 5-minute bars, never tick by
  tick. query2 first, query1 on a 429 or 5xx, one retry after a 5-second
  wait on a 429.
- Partial results are said as partial: "Fetched 1,950 of 2,010 charts (60
  failed or had no data)". Never round a partial scan up to "the whole market".
- NSE holidays for 2026 are built in (from an open-source list: confirm them
  on NSE's holiday page). Add later years, or fix a day, in
  `trader/holidays.json`. Outside the known years the tools say so.

## Steps

1. Once a week or so: `scan.py universe`.
2. Before the open: `scan.py daily`. Tell the user the counts (fetched,
   liquid, scanned, hits) and the top few by setup.
3. After 9:35 AM IST (10:00 is a common time): `scan.py orb`. Tell the user
   how many usable charts broke their range and when, and that a later hit is
   closer to the price now.
4. The user picks one chart. Hand it on: `/trader-news SYMBOL` (what is moving
   it), then `/trader-entry SYMBOL` (the entry bar by bar). Never pick for them.

## Example (illustrative)

```
python3 scan.py orb --at 10:00
Opening-range breakout scan, Thu 2026-11-12 10:00 AM IST: 15-minute range (9:15 to 9:30 AM), 5-minute bars, Yahoo.
...
   9:55 AM  RELIANCE   Rs 1,364.18  range 1,354.47 to 1,362.18  +0.15% over
```

RELIANCE's range is the 9:15 to 9:25 bars, high 1,362.18, low 1,354.47; the
9:50 bar closed at 1,364.18, above the high, at 9:55 AM. The user picks it
and Claude hands it to `/trader-news RELIANCE`, then `/trader-entry RELIANCE`.

## Rules

- Say what was scanned: how many symbols, how many charts came back, how many
  were usable, and the time of the data.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
