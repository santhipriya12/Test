---
name: trader-news
description: >-
  News Monitor for NSE stocks. Tracks breaking news on every stock you watch
  and flags what moves it: Yahoo Finance headlines per stock (.NS), each
  company's corporate announcements on NSE (financial results, board
  meetings, management changes, acquisitions, credit ratings, insolvency,
  clarifications on price moves) and how far each stock is from yesterday's
  close. Shows only what is new since the last check, newest first, in
  India time (IST), tags each item (earnings, analyst, deal, capital, halt,
  regulatory, macro...) and never repeats one. Use when the user says "any
  news on RELIANCE", "why is this moving", "what's the news on my
  watchlist", "morning briefing", "pre-market news", "monitor the news",
  "did anything break", "check the NSE announcements", or after
  /trader-scanner finds setups.
argument-hint: "[NSE symbols]"
---

# trader-news

A chart can look perfect and still be about to gap on results, a circuit or
a SEBI order. Before a setup becomes a trade, this skill reads the two feeds
that carry those first, for every stock on the watchlist, and tells you only
what is new. It also prints how far each stock has moved today, so a headline
and a move sit side by side.

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                              # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS --hours 12
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-nse --json
```

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-scanner) |
| `trader/plan.json` | the trade you are planning (trader-exit) |
| `trader/portfolio.json` | what you hold (trader-broker records fills there) |
| Yahoo Finance headline RSS | `https://feeds.finance.yahoo.com/rss/2.0/headline?s=RELIANCE.NS&region=IN&lang=en-IN` |
| Yahoo Finance chart endpoint | the last price against yesterday's close (unofficial, can lag) |
| NSE corporate announcements | `https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE`, after a browser-like visit to nseindia.com for its cookies |
| `trader/state/news.json` | what has been shown (kept 30 days) |

NSE sometimes refuses scripts (HTTP 401 or 403). Then the tool says so once,
skips the NSE part for that run and still shows headlines. The same
announcements are on nseindia.com (the company's page > Corporate
Information > Announcements). Yahoo's coverage of Indian stocks is thinner
than of US ones; an empty headline feed does not mean nothing happened.

## The rules

- **Headlines are leads, not facts.** Before telling the user something
  happened, open the story or the filing and read it. Quote the source and
  link it. Never summarise a paywalled story you could not read: say so.
- **Filings beat headlines.** If an NSE announcement and a headline disagree,
  the announcement is what the company told the exchange.
- **Say what it touches.** Every item lists the stocks it touches and its
  tags: earnings, analyst, legal, deal, capital, people, risk, halt,
  regulatory, macro. Announcements marked `!` have an important subject:
  financial results, board meeting outcomes or intimations (results dates),
  resignations and appointments, acquisitions and mergers, insolvency or
  default, credit ratings, buybacks, bonus or split, pledges, and NSE's
  "clarification" requests on unusual price or volume moves.
- **MOVING** marks a stock 3 % or more from yesterday's close (`--move-pct`).
  A move with no headline is worth saying out loud too. A stock near its
  price band (circuit) can stop trading: say so if the move is close to it.
- **No predictions.** Report what was published and how far the price is from
  yesterday's close. Never say what the stock will do next.

## Steps

1. Run the check: `python3 "${CLAUDE_SKILL_DIR}/news.py"`. Exit code 1 means
   nothing new. `--all` shows items already seen, `--json` gives everything
   machine readable, `--dry-run` leaves the state alone.
2. Read the items that matter: every `!` announcement, anything tagged
   earnings, halt, legal, regulatory or risk, and every MOVING stock first.
3. Write a short brief, per stock: what happened, the source and link, the
   move, and one line on why it matters to the setup (for example "the board
   meets on results tomorrow: an overnight gap can jump past any stop").
4. If a story changes the picture, say so before `/trader-entry` and
   `/trader-exit`: results inside the trade, a circuit, a block deal, a
   SEBI order. Never act on a headline alone.

During the session: `/loop 15m /trader-news`, or a scheduled task each
morning before 9:15 IST. Market-wide news (RBI policy, the Union Budget, FII
flows, global cues) moves everything: mention it when the headlines carry it.

## Example (illustrative)

Thursday 2026-11-12, RELIANCE broke its opening range at 9:55 AM IST. The
check shows an NSE announcement from the evening before, "Reliance Industries
Limited: Outcome of Board Meeting" (`!`, earnings) with the results PDF
link, and a headline about the results beating estimates. The brief: "Results
came out last evening; the move today is the market's reaction. No new
announcement this morning. RELIANCE is up 2.1% on yesterday's close."
When a stock has no news, say so rather than padding the brief.

## What it never does

- Never invents or embellishes a story, a quote or a number.
- Never trades on news, and never tells the user to buy or sell because of a
  headline.
- Never hammers a server: one request per feed per ticker, a pause between
  calls, and NSE is visited like a browser would, never in a tight loop.

## Safety

Education and tooling, not financial advice. This skill only reads and
reports. Nothing in this pack places an order: the user enters orders in
Groww themselves, after `/trader-risk` passes and they type an explicit yes.
