---
name: trader-deals
description: >-
  Bulk & Block Deals Tracker. Reads NSE's daily bulk deals (one client
  trading more than 0.5% of a company's shares in a day) and block deals
  (single trades of Rs 10 crore or more), with the buyer's or seller's name,
  alerts once per new deal, adds up the rupees bought and sold per stock,
  and flags deals in stocks you watch, plan or hold. Filters by stock, by
  client (a fund, an FII, LIC, a promoter) and by size in crore. Use when the
  user says "bulk deals", "block deals", "who bought RELIANCE today", "big
  investor trades", "what are the funds buying", "track this investor",
  "smart money", "large deals", or "alert me on big deals".
argument-hint: "[--symbol SYM] [--client NAME] [--min-cr N]"
---

# trader-deals

Every trading day NSE publishes two lists after the close:

- **Bulk deals**: any client whose trades in one stock add up to more than
  0.5% of the company's listed shares that day, with the client's name.
- **Block deals**: single trades of at least Rs 10 crore done in the block
  deal windows, usually funds and promoters moving big blocks.

This skill reads both lists, shows only what is new since the last check,
adds up the rupees per stock, and flags anything in the user's own stocks.
It is fast. It is not early: the lists are posted after the trades, and by
the next morning everyone has them. There is no inside information here,
only public disclosures read quickly. Say that every time.

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py" --help
```

## What it reads and writes

- Reads `https://nsearchives.nseindia.com/content/equities/bulk.csv` and
  `.../block.csv` (archives.nseindia.com as a fallback): Date, Symbol,
  Security Name, Client Name, Buy/Sell, Quantity Traded, Trade Price / Wght.
  Avg. Price (and Remarks for bulk deals). They hold the latest trading day.
- Writes `trader/state/deals.json`: the deals already shown (kept 60 days),
  so each one alerts once.
- Reads `trader/watchlist.json`, `trader/plan.json` and
  `trader/portfolio.json` to flag your stocks with `*`.

NSE sometimes refuses scripts. Then the tool says so: the user downloads the
two CSVs from nseindia.com (Market Data > Large Deals) into a folder and
runs it with `--offline FOLDER`.

## The rules

- **Quote the list, not a tracker.** Every row comes from NSE's file, with the
  client name exactly as NSE prints it. Sites that "decode" client names into
  famous investors can be wrong. NSE's name wins.
- **Price x quantity is the value.** Values are in Rs crore (1 crore = 10
  million). A bulk deal's price is often a weighted average over the day.
- **Both sides.** A bulk buy by one fund can be matched by a bulk sell by
  another the same day. Show the net per stock, not just the buys.
- **Small caps move on these.** A bulk deal in a thinly traded stock matters
  more than a block deal in a Nifty 50 name. Say how big the deal is against
  the stock's usual daily turnover when you know it (the scanner's volume).
- **Not a signal on its own.** A fund buying is one fact. It does not say the
  price will rise, and funds sell on later days too.

## Steps

1. Today's deals, new ones only:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/deals.py"
   ```

2. Narrow it down when the user asks about a stock or an investor:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/deals.py" --all --symbol RELIANCE
   python3 "${CLAUDE_SKILL_DIR}/deals.py" --all --client "MORGAN STANLEY" "SOCIETE GENERALE"
   python3 "${CLAUDE_SKILL_DIR}/deals.py" --min-cr 50
   ```

3. Write it up: the biggest deals first (stock, buyer or seller, quantity,
   price, Rs crore), the net per stock, and a line for each deal in the
   user's own stocks. Plain words, NSE's names, no guesses about motives.
4. Watching: for a daily check, run it after 6 p.m. IST (the lists are
   posted after the close). A deal that touches a planned trade goes to
   `/trader-news` for context before anything else.

## Example

```
NSE bulk and block deals for 2026-11-11: 3 new deals
* block RELIANCE     BUY     1,000,000 @   1,364.20 = Rs   136.42 cr  GAMMA MF
  bulk  ZYXSMALL     BUY       540,000 @     212.35 = Rs    11.47 cr  ALPHA FUND LP
  bulk  ZYXSMALL     SELL      300,000 @     211.90 = Rs     6.36 cr  BETA CAPITAL
```

(Illustrative names and numbers, not real deals.) The summary says: a
Rs 136 crore block buy in RELIANCE, a stock on the user's plan; in ZYXSMALL
one client bought Rs 11.5 crore while another sold Rs 6.4 crore, net
Rs 5.1 crore bought. Public, after the fact, and not a reason to trade by
itself.

## What it never does

- Never says or implies a client has inside information, or that copying a
  fund beats the market. No return claims.
- Never renames a client to a famous investor NSE's list does not name.
- Never places an order.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Practice (paper) mode by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order. Claude never places one: the user enters every order in the Groww
  app themselves, and trader-broker only shows that order as ready when trader-risk passed that exact
  order today AND the user typed an explicit yes for that one order in the chat.
- No options, futures, margin, short selling or leverage unless the config allows it and the user confirms.
- Never ask for, read or store a Groww password, PIN, OTP or API key.
- Bulk and block deals are PUBLIC disclosures, posted after the trade. This skill reads them; it
  has no inside information, and it says so.
