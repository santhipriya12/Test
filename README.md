# Test
Test bed for test

## Day Trader skills, India edition (NSE + Groww)

`.claude/skills/` holds eleven Claude Code skills for intraday trading on NSE,
adapted from [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
(MIT, license in `.claude/skills/DAY-TRADER-LICENSE`).

| command | job |
| --- | --- |
| `/trader-scanner` | scans NSE's EQ-series stocks for opening-range breakouts, flags and oversold bounces |
| `/trader-news` | Yahoo headlines plus NSE corporate announcements for your stocks |
| `/trader-entry` | watches a setup bar by bar from 9:15 IST and calls the entry |
| `/trader-exit` | sets the stop and target, rounded to NSE's tick size; flat by 15:00 IST |
| `/trader-timemachine` | replays the rest of the session 10,000 times from the last 60 days (75 bars a day) |
| `/trader-risk` | checks every order against your limits in rupees, the IST entry window and NSE holidays |
| `/trader-budget` | sizes the trade in whole shares to your rupee budget and max loss |
| `/trader-broker` | turns an approved order into a Groww ticket (Intraday/MIS, SL-M stop) that **you** enter in the Groww app |
| `/trader-alerts` | price, stop, target and time alerts on the NSE clock |
| `/trader-analyst` | quarterly results from NSE (Q2 FY27 style), growth and margins |
| `/trader-deals` | NSE bulk and block deals: who bought and sold, in Rs crore |

### Setup

1. Copy `.claude/skills/trader-budget/config.example.json` to `trader/config.json`
   in your project and set your budget and limits (all amounts in rupees).
   `"paper": true` (practice mode) is the default.
2. Optional: `trader/holidays.json` with extra or corrected NSE holidays,
   `{"2027-01-26": "Republic Day"}`. The 2026 list is built in, from an
   open-source NSE library; check it against NSE's own holiday page.
3. Python 3.8+, nothing to install.

### What to know

- **No order is ever placed by Claude.** The broker skill only prints a Groww
  ticket after the risk check passes and you type "yes"; you enter it in Groww
  yourself. Never give Claude your Groww password, PIN, OTP or API key.
- **NSE often blocks scripts.** The universe, news, results and deals tools
  read nseindia.com. When NSE refuses (HTTP 401/403), download the file in a
  browser and pass it with `--offline`; each tool says how.
- **Unverified pieces.** These could not be checked against live sites while
  converting: NSE's results JSON field names (the analyst prints the fields it
  used so you can check), the NSE announcements fields, Groww's exact screen
  names, Groww's intraday auto square-off time (flat-by defaults to 15:00 to
  stay clear of it), and the built-in 2026 holiday list.
- Prices come from Yahoo Finance (`.NS` symbols): free, unofficial and delayed.

### Tests

```bash
python3 -m unittest discover -s tests
```

Education and tooling, not financial advice. SEBI's studies found that most
individual intraday traders in India lose money.
