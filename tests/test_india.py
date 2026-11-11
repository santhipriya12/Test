"""India / NSE / Groww behaviour of the trader skills. Offline: no network.

    python3 -m unittest discover -s tests
"""

import datetime
import json
import os
import re
import tempfile
import unittest

from _load import SKILLS, load

entry = load("trader-entry", "entry")
exitp = load("trader-exit", "exit")
risk = load("trader-risk", "check")
broker = load("trader-broker", "ticket")
budget = load("trader-budget", "size")
scan = load("trader-scanner", "scan")
news = load("trader-news", "news")
facts = load("trader-analyst", "facts")
deals = load("trader-deals", "deals")
tm = load("trader-timemachine", "timemachine")
alerts = load("trader-alerts", "alerts")

IST = datetime.timedelta(hours=5, minutes=30)


def utc(s):
    """'2026-11-12 09:55' IST -> naive UTC."""
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M") - IST


class Clock(unittest.TestCase):
    def test_ist_round_trip_all_scripts(self):
        u = datetime.datetime(2026, 11, 12, 4, 25)
        for mod in (entry, exitp, risk, broker, budget, scan, tm, alerts):
            self.assertEqual(mod.to_ist(u), datetime.datetime(2026, 11, 12, 9, 55), mod.__name__)
            self.assertEqual(mod.ist_to_utc(datetime.datetime(2026, 11, 12, 9, 55)), u, mod.__name__)

    def test_no_daylight_saving(self):
        for month in (1, 4, 7, 10):
            u = datetime.datetime(2026, month, 15, 0, 0)
            self.assertEqual(entry.to_ist(u) - u, IST)

    def test_parse_now_is_ist(self):
        self.assertEqual(entry.parse_now("2026-11-12 09:55"), datetime.datetime(2026, 11, 12, 4, 25))
        self.assertEqual(risk.parse_now("2026-11-12 09:55"), datetime.datetime(2026, 11, 12, 4, 25))

    def test_nse_session_and_holidays(self):
        self.assertEqual(entry.session(datetime.date(2026, 11, 12)),
                         (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertIsNone(entry.session(datetime.date(2026, 11, 24)))     # Guru Nanak Jayanti
        self.assertIsNone(entry.session(datetime.date(2026, 11, 14)))     # Saturday
        ok, why = risk.trading_day(datetime.date(2026, 1, 26))
        self.assertFalse(ok)
        self.assertIn("Republic Day", why)
        self.assertEqual(entry.NSE_EARLY_CLOSE, {})

    def test_user_holidays_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "holidays.json")
            with open(p, "w") as fh:
                json.dump({"2027-01-26": "Republic Day", "bad": "x"}, fh)
            entry._merge_user_holidays(p)
            self.assertIn("2027-01-26", entry.NSE_HOLIDAYS)
            self.assertNotIn("bad", entry.NSE_HOLIDAYS)
            self.assertIn(2027, entry.CALENDAR_YEARS_SET)
            del entry.NSE_HOLIDAYS["2027-01-26"]

    def test_timemachine_session_is_75_bars(self):
        self.assertEqual(tm.SESSION_BARS, 75)
        self.assertEqual(tm.OPEN_MIN, 9 * 60 + 15)
        self.assertEqual(tm.CLOSE_MIN, 15 * 60 + 30)


class Symbols(unittest.TestCase):
    def test_yahoo_symbol(self):
        for mod in (entry, news, tm, exitp, alerts):
            self.assertEqual(mod.yahoo_symbol("reliance"), "RELIANCE.NS")
            self.assertEqual(mod.yahoo_symbol("M&M"), "M&M.NS")
            self.assertEqual(mod.yahoo_symbol("500325.BO"), "500325.BO")
            self.assertEqual(mod.yahoo_symbol("^NSEI"), "^NSEI")

    def test_urls_are_quoted(self):
        self.assertIn("/M%26M.NS?", entry.chart_path("M&M", "1d", "5m"))
        self.assertIn("/M%26M.NS?", tm.chart_url("M&M"))
        self.assertIn("/BAJAJ-AUTO.NS?", alerts.yahoo_url("BAJAJ-AUTO"))
        self.assertEqual(scan.to_yahoo("M&M"), "M%26M.NS")

    def test_risk_ticker_rule(self):
        for ok in ("RELIANCE", "M&M", "BAJAJ-AUTO", "RELIANCE.NS", "500325.BO"):
            self.assertTrue(risk.TICKER.match(ok), ok)
        self.assertFalse(risk.TICKER.match("BTC/USD"))
        self.assertTrue(risk.OCC.match("NIFTY26NOV24000CE"))
        self.assertTrue(risk.OCC.match("RELIANCE26NOVFUT"))
        self.assertFalse(risk.OCC.match("RELIANCE"))


class Universe(unittest.TestCase):
    CSV = ("SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
           "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
           "M&M,Mahindra & Mahindra Limited,EQ,17-NOV-1995,5,1,INE101A01026,5\n"
           "XYZBE,Xyz Limited,BE,01-JAN-2020,10,1,INE000000000,10\n"
           "SMEONE,Sme One Limited,SM,01-JAN-2021,10,1,INE000000001,10\n")

    def test_keeps_eq_series_only(self):
        kept, counts, _ = scan.build_universe({scan.NSE_FILE: self.CSV})
        self.assertEqual([k for k, _ in kept], ["M&M", "RELIANCE"])
        self.assertEqual(counts["rows"], 4)
        self.assertEqual(counts["series BE (no intraday)"], 1)

    def test_rejects_other_files(self):
        with self.assertRaises(scan.ScanError):
            scan.parse_equity_list("Symbol|Security Name\nAAPL|Apple\n")


class Ticks(unittest.TestCase):
    def test_tick_table(self):
        D = exitp.Decimal
        self.assertEqual(exitp.tick_for(D("120")), D("0.01"))
        self.assertEqual(exitp.tick_for(D("800")), D("0.05"))
        self.assertEqual(exitp.tick_for(D("1364.18")), D("0.10"))
        self.assertEqual(exitp.tick_for(D("7000")), D("0.50"))
        self.assertEqual(exitp.tick_for(D("15000")), D("1.00"))
        self.assertEqual(exitp.tick_for(D("30000")), D("5.00"))

    def test_plan_snaps_to_tick(self):
        p = exitp.compute(1364.18, "or_mid", None, "r", exitp.Decimal("2"), or_high=1362.18, or_low=1354.47)
        self.assertEqual(p["stop"], exitp.Decimal("1358.30"))      # 1358.325 floored to 0.10
        self.assertEqual(p["target"], exitp.Decimal("1375.90"))    # 1375.94 rounded to 0.10
        p = exitp.compute(812.33, "pct", exitp.Decimal("1"), "r", exitp.Decimal("2"))
        self.assertEqual(p["stop"] % exitp.Decimal("0.05"), 0)
        self.assertEqual(p["target"] % exitp.Decimal("0.05"), 0)

    def test_override(self):
        exitp.TICK_OVERRIDE[0] = exitp.Decimal("0.05")
        try:
            self.assertEqual(exitp.tick_for(exitp.Decimal("1364")), exitp.Decimal("0.05"))
        finally:
            exitp.TICK_OVERRIDE[0] = None

    def test_rupee_prefixes(self):
        self.assertEqual(exitp.D("Rs 1,364.18"), exitp.Decimal("1364.18"))
        self.assertEqual(exitp.D("₹1364.18"), exitp.Decimal("1364.18"))
        self.assertEqual(exitp.parse_stop("price:Rs 1358.3"), ("price", exitp.Decimal("1358.3")))


def bracket(**kw):
    o = {"symbol": "RELIANCE", "exchange": "NSE", "side": "buy", "qty": "73", "type": "market",
         "time_in_force": "day", "product": "MIS", "order_class": "bracket",
         "take_profit_limit_price": "1375.90", "stop_loss_stop_price": "1358.30",
         "plan": {"entry": 1364.18, "stop": 1358.3, "target": 1375.9, "risk_per_share": 5.88,
                  "max_loss": 429.24, "setup": "orb", "flat_by": "15:00"}}
    o.update(kw)
    return o


class Risk(unittest.TestCase):
    def run_check(self, orders, now, cfg=None):
        c = dict(risk.DEFAULTS, budget=200000)
        c.update(cfg or {})
        res = risk.check(orders, c, portfolio=None, prices={}, state={"orders": []}, now=utc(now))
        return res

    def verdict(self, res, i=0):
        r = res["results"][i]
        return r["verdict"], " ".join(r["reasons"])

    def test_defaults_are_rupees_and_ist(self):
        self.assertEqual(risk.DEFAULTS["max_loss_per_trade_inr"], 1000)
        self.assertEqual(risk.DEFAULTS["no_entries_before"], "09:30")
        self.assertEqual(risk.DEFAULTS["no_entries_after"], "14:30")
        self.assertNotIn("max_loss_per_trade_usd", risk.DEFAULTS)

    def test_pass_in_window(self):
        v, why = self.verdict(self.run_check([bracket()], "2026-11-12 09:57"))
        self.assertEqual(v, "PASS", why)

    def test_window_and_holiday(self):
        self.assertIn("window", self.verdict(self.run_check([bracket()], "2026-11-12 09:20"))[1])
        self.assertIn("window", self.verdict(self.run_check([bracket()], "2026-11-12 14:45"))[1])
        v, why = self.verdict(self.run_check([bracket()], "2026-11-24 10:00"))
        self.assertEqual(v, "BLOCK")
        self.assertIn("NSE holiday", why)

    def test_no_early_close_shift(self):
        # 14:15 is inside the default window on a normal NSE day (no 3-hour early-close shift)
        v, why = self.verdict(self.run_check([bracket()], "2026-11-12 14:15"))
        self.assertEqual(v, "PASS", why)

    def test_india_order_format(self):
        o = bracket()
        del o["qty"]
        o["notional"] = "5000"
        self.assertIn("whole shares", self.verdict(self.run_check([o], "2026-11-12 10:00"))[1])
        self.assertIn("whole number", self.verdict(self.run_check([bracket(qty="7.5")], "2026-11-12 10:00"))[1])
        self.assertIn("product", self.verdict(self.run_check([bracket(product="NRML")], "2026-11-12 10:00"))[1])
        self.assertIn("validity", self.verdict(self.run_check([bracket(time_in_force="gtc")], "2026-11-12 10:00"))[1])
        self.assertIn("F&O", self.verdict(self.run_check([bracket(symbol="NIFTY26NOV24000CE")], "2026-11-12 10:00"))[1])

    def test_loss_limit_in_rupees(self):
        v, why = self.verdict(self.run_check([bracket(qty="200")], "2026-11-12 10:00",
                                             {"max_order_inr": 10 ** 7, "max_position_pct": 100}))
        self.assertEqual(v, "BLOCK")
        self.assertIn("Rs 1,000", why)


class Broker(unittest.TestCase):
    def test_fingerprint_matches_risk(self):
        o = bracket()
        self.assertEqual(broker.fingerprint(o), risk.fingerprint(o))
        self.assertEqual(set(broker.ORDER_FIELDS), set(risk.ORDER_FIELDS))

    def test_groww_steps(self):
        live = "\n".join(broker.groww_steps(bracket(), paper=False))
        self.assertIn("Exchange NSE, Intraday (MIS), Qty 73, Market", live)
        self.assertIn("SL-M", live)
        self.assertIn("trigger price 1358.30", live)
        self.assertIn("CANCEL the SL-M first", live)
        self.assertNotIn("PRACTICE", live)
        paper = "\n".join(broker.groww_steps(bracket(), paper=True))
        self.assertIn("do NOT enter this in Groww", paper)

    def test_plain_ticket(self):
        self.assertTrue(broker.plain(bracket()).startswith("BUY 73 RELIANCE on NSE, Intraday (MIS), market"))
        self.assertIn("Rs 429.24", broker.plain(bracket()))

    def test_yes_rules_unchanged(self):
        self.assertTrue(broker.parse_yes("yes", bracket())[0])
        self.assertFalse(broker.parse_yes("sure", bracket())[0])
        self.assertFalse(broker.parse_yes("yes to all", bracket())[0])
        self.assertFalse(broker.parse_yes("yes 80 shares", bracket())[0])

    def test_ist_stamp(self):
        self.assertEqual(broker.ist_iso(datetime.datetime(2026, 11, 12, 4, 25)), "2026-11-12T09:55:00+05:30")


class News(unittest.TestCase):
    def test_nse_time(self):
        self.assertEqual(news.parse_nse_time("10-Nov-2026 18:23:11"),
                         datetime.datetime(2026, 11, 10, 12, 53, 11, tzinfo=datetime.timezone.utc))
        self.assertIsNone(news.parse_nse_time("soon"))

    def test_announcements(self):
        data = json.dumps([
            {"desc": "Outcome of Board Meeting", "an_dt": "10-Nov-2026 18:23:11", "seq_id": "1",
             "sm_name": "Reliance Industries Limited", "attchmntFile": "https://example.com/r.pdf",
             "attchmntText": "financial results for the quarter ended September 30, 2026"},
            {"desc": "Updates", "an_dt": "09-Nov-2026 10:01:00", "seq_id": "2", "attchmntText": "Analyst meet"},
            {"foo": "bar"}]).encode()
        items = news.parse_nse_announcements(data, "RELIANCE")
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["important"])
        self.assertFalse(items[1]["important"])
        tagged = news.tag(items, {"RELIANCE": None})
        self.assertIn("earnings", tagged[0]["tags"])

    def test_block_page(self):
        with self.assertRaises(news.NewsError):
            news.parse_nse_announcements(b"<html>Access Denied</html>", "RELIANCE")


class Analyst(unittest.TestCase):
    DOC = {"resCmpData": [
        {"re_to_dt": "30-SEP-2026", "re_net_sale": "2,50,000", "re_pro_loss_aft_tax": "18000", "re_dil_eps": "13.3"},
        {"re_to_dt": "30-JUN-2026", "re_net_sale": "240000", "re_pro_loss_aft_tax": "17000", "re_dil_eps": "12.6"},
        {"re_to_dt": "31-MAR-2026", "re_net_sale": "245000", "re_pro_loss_aft_tax": "19000", "re_dil_eps": "14"},
        {"re_to_dt": "31-DEC-2025", "re_net_sale": "235000", "re_pro_loss_aft_tax": "17500", "re_dil_eps": "12.9"},
        {"re_to_dt": "30-SEP-2025", "re_net_sale": "220000", "re_pro_loss_aft_tax": "(1600)", "re_dil_eps": "11.8"}]}

    def test_fields_and_growth(self):
        res = facts.analyse(self.DOC)
        f = res["fields"]
        self.assertEqual((f["period"], f["revenue"], f["net_profit"], f["eps"]),
                         ("re_to_dt", "re_net_sale", "re_pro_loss_aft_tax", "re_dil_eps"))
        q = res["quarters"][0]
        self.assertEqual(q["label"], "Q2 FY27")
        self.assertEqual(q["revenue"], 250000.0)        # Indian digit grouping read right
        self.assertEqual(q["revenue_yoy"], 13.6)
        self.assertEqual(res["quarters"][-1]["net_profit"], -1600.0)   # (1600) is a loss
        self.assertEqual(res["ttm"]["revenue"], 970000.0)

    def test_fy_labels(self):
        self.assertEqual(facts.fy_quarter(datetime.date(2026, 6, 30)), "Q1 FY27")
        self.assertEqual(facts.fy_quarter(datetime.date(2026, 12, 31)), "Q3 FY27")
        self.assertEqual(facts.fy_quarter(datetime.date(2027, 3, 31)), "Q4 FY27")

    def test_unknown_shape(self):
        with self.assertRaises(facts.FactsError):
            facts.analyse({"data": [{"a": 1}]})


class Deals(unittest.TestCase):
    BULK = ("Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n"
            '11-NOV-2026,ZYX,Zyx Ltd,ALPHA FUND LP,BUY,"5,40,000",212.35,-\n'
            "11-NOV-2026,ZYX,Zyx Ltd,BETA CAPITAL,SELL,300000,211.90,-\n")

    def test_parse_and_totals(self):
        d = deals.parse_deals(self.BULK, "bulk")
        self.assertEqual(len(d), 2)
        self.assertEqual(d[0]["qty"], 540000)
        self.assertEqual(d[0]["value_cr"], 11.47)
        self.assertEqual(d[0]["date"], "2026-11-11")
        t = deals.by_symbol(d)[0]
        self.assertEqual((t["buy_cr"], t["sell_cr"], t["net_cr"]), (11.47, 6.36, 5.11))

    def test_filters(self):
        d = deals.parse_deals(self.BULK, "bulk")
        self.assertEqual(len(deals.select(d, clients=["alpha"])), 1)
        self.assertEqual(len(deals.select(d, min_cr=10)), 1)
        self.assertEqual(len(deals.select(d, symbols=["TCS"])), 0)

    def test_empty_and_block_page(self):
        self.assertEqual(deals.parse_deals("Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,"
                                           "Trade Price / Wght. Avg. Price\n", "block"), [])
        with self.assertRaises(deals.DealsError):
            deals.parse_deals("<html>denied</html>", "bulk")


class EntryTrigger(unittest.TestCase):
    def chart(self):
        """RELIANCE on 2026-11-12, 5-minute bars from 9:15 IST; the 9:50 bar closes above the range."""
        start = int((datetime.datetime(2026, 11, 12, 9, 15) - IST - datetime.datetime(1970, 1, 1)).total_seconds())
        closes = [1360, 1358, 1361, 1361.5, 1361.2, 1361.68, 1361.0, 1364.18, 1365, 1366]
        highs = [1362.18, 1360, 1362, 1362, 1362, 1362, 1362, 1364.5, 1366, 1367]
        lows = [1354.47, 1356, 1358, 1360, 1360, 1360, 1360, 1361, 1363, 1364]
        n = len(closes)
        doc = {"chart": {"result": [{"meta": {"symbol": "RELIANCE.NS", "previousClose": 1350},
                                     "timestamp": [start + 300 * i for i in range(n)],
                                     "indicators": {"quote": [{"open": closes, "high": highs, "low": lows,
                                                               "close": closes, "volume": [1000] * n}]}}]}}
        return entry.parse_chart(json.dumps(doc), "RELIANCE")

    def test_opening_range_breakout(self):
        res = entry.evaluate(self.chart(), utc("2026-11-12 10:00"))
        self.assertEqual(res["status"], "triggered", res.get("reason"))
        self.assertEqual(res["trigger"]["time"], "9:55 AM")
        self.assertEqual(res["trigger"]["price"], 1364.18)
        self.assertEqual(res["opening_range"]["high"], 1362.18)

    def test_before_open_and_holiday(self):
        res = entry.evaluate(self.chart(), utc("2026-11-12 09:00"))
        self.assertEqual(res["status"], "waiting")
        self.assertEqual(res["phase"], "pre-open")


class Repo(unittest.TestCase):
    NAMES = ["trader-alerts", "trader-analyst", "trader-broker", "trader-budget", "trader-deals", "trader-entry",
             "trader-exit", "trader-news", "trader-risk", "trader-scanner", "trader-timemachine"]

    def test_eleven_skills(self):
        found = sorted(d for d in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))
        self.assertEqual(found, self.NAMES)
        for n in found:
            with open(os.path.join(SKILLS, n, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertTrue(text.startswith("---\nname: %s\n" % n), n)
            self.assertIn("not financial advice", " ".join(text.lower().split()), n)

    def test_no_us_leftovers(self):
        bad = re.compile(r"\bNYSE\b|New York|Alpaca|place_stock_order|SEC EDGAR|\bTSLA\b|_usd\b|Pelosi|\$\d")
        for base, _, files in os.walk(SKILLS):
            for f in files:
                if f.endswith((".py", ".md", ".json")):
                    with open(os.path.join(base, f), encoding="utf-8") as fh:
                        for i, line in enumerate(fh, 1):
                            self.assertIsNone(bad.search(line), "%s:%d: %s" % (f, i, line.strip()))


if __name__ == "__main__":
    unittest.main()
