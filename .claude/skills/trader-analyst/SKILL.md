---
name: trader-analyst
description: >-
  The Earnings Analyst. Reads a company's quarterly results as filed with NSE
  (the results comparison NSE shows on the company page, plus the list of
  results filings with their XBRL / PDF links) and sums up what changed:
  revenue, net profit, net margin and diluted EPS, quarter by quarter, each
  against the same quarter a year earlier and the quarter before, with the
  last four quarters. Labels quarters the Indian way (Q2 FY27). Reads an
  earnings call transcript or a results press release when you paste one.
  Use when the user says "how were Reliance's results", "analyze the
  results", "what changed this quarter", "is revenue growing", "check the
  quarterly results", "compare margins", "sum up the con-call", "when are
  results", or before trading a stock around its results.
argument-hint: "[NSE symbols]"
---

# trader-analyst

Results move Indian stocks more than anything else on the calendar, and the
press release puts the best number first. This skill reads the numbers the
company filed with NSE, lines them up quarter by quarter, and says plainly
what changed. For a day trader it answers two questions before a trade: what
did the last results say, and is the next board meeting inside this trade?

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" --help
```

## What it reads and writes

- Reads NSE's results comparison
  (`https://www.nseindia.com/api/results-comparision?symbol=SYMBOL`, NSE's own
  spelling) and the results filings list
  (`https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly&symbol=SYMBOL`).
  NSE wants a browser-like visit first; the tool does that. NSE sometimes
  refuses scripts (HTTP 401 / 403). Then the user opens that URL in a browser
  on nseindia.com, saves the JSON as `results-SYMBOL.json`, and you run the
  tool with `--offline` on it.
- NSE publishes no schema for these responses, so the tool finds each figure
  by its field name and prints the fields it used (`fields used: ...`). Read
  that line. If a field looks wrong (total income used as revenue, basic EPS
  used as diluted), say so in the summary.
- Amounts print as NSE reports them, usually **Rs lakh** (100 lakh = 1 crore).
  The tool cannot confirm the unit: check one figure against the filing's PDF
  before you quote crores.
- Writes `trader/metrics.json` with `--metrics`: one row per company (the
  latest quarter, growth, margin, the last four quarters).
- Con-calls: the tool does not fetch transcripts. If the user pastes one (or
  the results press release), read it and sum up what management said
  changed: guidance, margins, demand, anything they would not answer.
- The next results date is a "Board Meeting Intimation" in
  `/trader-news` (NSE announcements). Say where the date came from.

## The rules

- **Filed numbers first.** The table comes from NSE's results data. Use the
  press release and the con-call for context and say which number came from
  where.
- **Consolidated vs standalone.** Indian companies file both. Compare like
  with like and say which one the table is (the `basis` line). For groups
  like Reliance or Tata companies, consolidated is the one that matters.
- **Compare like with like.** Growth is against the same quarter a year
  earlier. Quarter-on-quarter is shown too, but many businesses are seasonal
  (festive-season quarters, monsoon-driven demand).
- **Indian quarters.** The financial year runs April to March: the quarter
  ending 30 September 2026 is Q2 FY27.
- **Flag one-offs.** Exceptional items, tax write-backs and other income can
  make net profit jump without the business changing. Say so when profit
  grows much faster than revenue.
- **Banks and NBFCs** report interest income, not sales: the revenue column
  for them is interest earned or total income, and margins read differently.

## Steps

1. Run it for the companies in question (or the stocks on
   `trader/watchlist.json`):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
   python3 "${CLAUDE_SKILL_DIR}/facts.py" TCS INFY HCLTECH --metrics trader/metrics.json
   python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE --offline results-RELIANCE.json
   ```

   `--quarters 8` shows two years, `--json` everything machine-readable.
2. Open the latest results filing (the link the tool lists) when the numbers
   need context, and read it.
3. Write the summary: one line on the quarter (revenue, profit, EPS, growth),
   one on margins, one on anything unusual (a one-off, a loss, a field that
   looked off), and the links. Plain words, real numbers, no adjectives the
   numbers do not support.
4. If the next board meeting for results falls inside the planned trade (an
   overnight hold, or results announced during market hours), say it before
   `/trader-exit` sets the stop: a stop does not protect against a gap.

## Example (illustrative numbers)

`facts.py RELIANCE`: Q2 FY27 (quarter ending 2026-09-30), revenue 2,50,000
(NSE's figure, Rs lakh), +13.6% against Q2 FY26; net profit 18,000 (+12.5%),
net margin 7.2%; diluted EPS 13.30 (+12.7%). The summary reads: "Revenue and
profit both grew about 13% on the year, margins steady at about 7%. The next
board meeting is not announced yet. A day trade that closes before 3:30 p.m.
is not exposed to it; anything held overnight would be."

## What it never does

- Never says a stock is cheap, expensive, a buy or a sell. It reports what the
  company filed.
- Never invents a number the filings do not have, or converts lakh to crore
  without checking the unit.
- Never hammers NSE: one company at a time, with pauses.

## Safety

Education and tooling, not financial advice. This skill only reads and
reports. Nothing in this pack places an order: the user enters orders in
Groww themselves, after `/trader-risk` passes and they type an explicit yes.
