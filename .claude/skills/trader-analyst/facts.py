#!/usr/bin/env python3
"""Earnings reader for trader-analyst (NSE). Standard library only.

Pulls a company's quarterly results as filed with NSE and lays out what
changed, quarter by quarter: revenue, net profit, net margin, diluted EPS,
and growth against the same quarter a year earlier and the quarter before.
It also lists the company's latest results filings on NSE (with the XBRL /
PDF links) so the summary can cite the filing itself.

    python3 facts.py RELIANCE
    python3 facts.py RELIANCE TCS --quarters 8
    python3 facts.py INFY --json
    python3 facts.py HDFCBANK ICICIBANK --metrics trader/metrics.json
    python3 facts.py RELIANCE --offline results-RELIANCE.json   # a response you saved in a browser

Sources (NSE's own website API; no key, but it wants a browser-like visit
first, and it sometimes refuses scripts with HTTP 401 / 403):
  https://www.nseindia.com/api/results-comparision?symbol=<SYMBOL>
      the quarterly results comparison NSE shows on the company's page
  https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly&symbol=<SYMBOL>
      the list of results filings (period, audited or not, consolidated or
      standalone, filing time, XBRL / PDF link)

How the numbers are read. NSE does not publish a schema for these responses,
so the tool finds each figure by its field name and PRINTS which field it
used, so you can check it against the filing:
  period end    a field like to_dt / toDate / qe_date / period ending
  revenue       net sales / revenue from operations / income from operations
                (total income, which includes other income, only as a last resort)
  net profit    profit (loss) after tax / net profit / PAT
  diluted EPS   a diluted EPS field, else basic EPS (and it says so)
Amounts are printed as NSE reports them. NSE's results tables are usually in
Rs lakh (1 lakh = 100,000; 100 lakh = 1 crore). The tool cannot confirm the
unit from the response: check one figure against the filing before quoting
crores.

When NSE refuses the script: open https://www.nseindia.com/api/results-comparision?symbol=<SYMBOL>
in a browser on nseindia.com (after loading any NSE page), save the JSON and
pass it with --offline FILE (or --offline DIR holding results-<SYMBOL>.json
and filings-<SYMBOL>.json).

--metrics FILE merges one row per symbol into a JSON file (latest quarter,
growth, margin, TTM when four quarters are there).

Numbers only: this tool never says whether a stock is a buy.
"""

import argparse
import datetime as _dt
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NSE_HOME = "https://www.nseindia.com/"
NSE_QUOTE = "https://www.nseindia.com/get-quotes/equity?symbol=%s"
RESULTS_URL = "https://www.nseindia.com/api/results-comparision?symbol=%s"
FILINGS_URL = ("https://www.nseindia.com/api/corporates-financial-results?index=equities"
               "&period=Quarterly&symbol=%s")
NSE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
PAUSE = 0.6

# field-name patterns, best first
PERIOD_KEYS = [r"^re_to_dt$", r"to_?dt$", r"^to_?date$", r"qe_?date", r"period_?end", r"^period$", r"quarter_?end",
               r"to_?date"]
REVENUE_KEYS = [r"net_?sale", r"revenue_?from_?op", r"income_?from_?op", r"^re_?revenue$", r"revenue",
                r"sales", r"total_?income"]
PROFIT_KEYS = [r"pro(fit)?_?loss_?aft(er)?_?tax", r"net_?pro(fit)?_?loss", r"net_?profit", r"profit_?after_?tax",
               r"(^|_)pat($|_)", r"pro_?loss_?for_?period", r"net_?income"]
DIL_EPS_KEYS = [r"dil\w*eps", r"eps\w*dil"]
BAS_EPS_KEYS = [r"bas\w*eps", r"eps\w*bas", r"(^|_)eps($|_)"]
CONSOL_KEYS = [r"consol", r"^re_?cons", r"type"]
NUMERIC = re.compile(r"^\s*\(?-?[\d,]*\.?\d+\)?\s*$")
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


class FactsError(Exception):
    pass


# ---------------------------------------------------------------- fetching

class Fetcher(object):
    def __init__(self, offline=None, pause=PAUSE):
        self.offline = offline
        self.pause = pause
        self._last = 0.0
        self._op = None

    def _wait(self):
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()

    def _opener(self, symbol):
        if self._op is None:
            import http.cookiejar
            jar = http.cookiejar.CookieJar()
            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            op.addheaders = [("User-Agent", NSE_UA), ("Accept-Language", "en-US,en;q=0.9")]
            for url in (NSE_HOME, NSE_QUOTE % urllib.parse.quote(symbol)):
                try:
                    self._wait()
                    op.open(url, timeout=30).read()
                except (urllib.error.URLError, OSError):
                    pass
            self._op = op
        return self._op

    def json(self, url, name, symbol):
        if self.offline:
            path = self.offline
            if os.path.isdir(path):
                path = os.path.join(path, name)
            elif not name.startswith("results-"):
                raise FactsError("offline: no file for %s" % name)
            if not os.path.isfile(path):
                raise FactsError("offline: no file %s" % path)
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                text = fh.read()
        else:
            op = self._opener(symbol)
            self._wait()
            req = urllib.request.Request(url, headers={
                "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest",
                "Referer": NSE_QUOTE % urllib.parse.quote(symbol), "Accept-Encoding": "gzip"})
            try:
                with op.open(req, timeout=30) as resp:
                    data = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        data = gzip.decompress(data)
                    text = data.decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                hint = (" NSE refused the script: save the JSON from a browser and use --offline"
                        if exc.code in (401, 403) else "")
                raise FactsError("HTTP %s for %s.%s" % (exc.code, url.split("?")[0], hint))
            except (urllib.error.URLError, OSError) as exc:
                raise FactsError("could not reach %s: %s" % (url.split("?")[0], getattr(exc, "reason", exc)))
        try:
            return json.loads(text)
        except ValueError:
            raise FactsError("%s is not JSON (NSE may have answered with a block page)" % name)


# ---------------------------------------------------------------- reading NSE's rows

def rows_of(doc):
    """The list of per-period dicts inside a response, wherever NSE put it."""
    if isinstance(doc, list):
        return [r for r in doc if isinstance(r, dict)]
    if isinstance(doc, dict):
        best = []
        for v in doc.values():
            if isinstance(v, list) and v and all(isinstance(r, dict) for r in v) and len(v) > len(best):
                best = v
        return best
    return []


def pick(keys, patterns, row=None, numeric=False):
    """The first key (by pattern order) that matches, and whose value looks right."""
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for k in keys:
            if rx.search(k):
                if row is not None and numeric and to_num(row.get(k)) is None:
                    continue
                return k
    return None


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not NUMERIC.match(s) or s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def to_date(v):
    s = str(v or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3})[A-Za-z]*[-/ ](\d{2,4})", s)
    if m:
        y = int(m.group(3))
        y += 2000 if y < 100 else 0
        mon = MONTHS.get(m.group(2).upper())
        if mon:
            try:
                return _dt.date(y, mon, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        try:
            return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def fy_quarter(d):
    """Indian financial year label for a quarter ending on d: Q2 FY27 for 30 Sep 2026."""
    fy = d.year + 1 if d.month >= 4 else d.year
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    return ("Q%d FY%02d" % (q, fy % 100)) if q else d.strftime("%b %Y")


def read_quarters(doc):
    """NSE results-comparision -> ([quarter dicts, newest first], fields used, notes)."""
    rows = rows_of(doc)
    if not rows:
        raise FactsError("no result rows in NSE's answer")
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    fields = {
        "period": pick(keys, PERIOD_KEYS),
        "revenue": pick(keys, REVENUE_KEYS, rows[0], numeric=True),
        "net_profit": pick(keys, PROFIT_KEYS, rows[0], numeric=True),
        "eps": pick(keys, DIL_EPS_KEYS, rows[0], numeric=True),
    }
    notes = []
    if not fields["eps"]:
        fields["eps"] = pick(keys, BAS_EPS_KEYS, rows[0], numeric=True)
        if fields["eps"]:
            notes.append("no diluted EPS field: EPS is basic EPS (%s)" % fields["eps"])
    elif not re.search(r"dil", fields["eps"], re.I):
        notes.append("EPS field %s may be basic EPS" % fields["eps"])
    if fields["revenue"] and re.search(r"total_?income", fields["revenue"], re.I):
        notes.append("revenue is total income (it includes other income): margins read a little high")
    if not fields["period"]:
        raise FactsError("could not find the period-end field among: %s" % ", ".join(keys[:30]))
    if not fields["revenue"] and not fields["net_profit"]:
        raise FactsError("could not find revenue or profit fields among: %s" % ", ".join(keys[:30]))
    consol = pick(keys, CONSOL_KEYS)
    out, seen = [], set()
    for r in rows:
        d = to_date(r.get(fields["period"]))
        if not d or d in seen:
            continue
        seen.add(d)
        q = {"period_end": d, "label": fy_quarter(d),
             "revenue": to_num(r.get(fields["revenue"])) if fields["revenue"] else None,
             "net_profit": to_num(r.get(fields["net_profit"])) if fields["net_profit"] else None,
             "eps": to_num(r.get(fields["eps"])) if fields["eps"] else None,
             "basis": str(r.get(consol) or "").strip() if consol else ""}
        if q["revenue"] and q["net_profit"] is not None:
            q["net_margin"] = round(q["net_profit"] / q["revenue"] * 100, 2)
        out.append(q)
    out.sort(key=lambda q: q["period_end"], reverse=True)
    if not out:
        raise FactsError("no row had a readable period end (field %s)" % fields["period"])
    return out, fields, notes


def pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100 * (1 if b > 0 else -1), 1)


def analyse(doc, quarters=6):
    qs, fields, notes = read_quarters(doc)
    by_end = {q["period_end"]: q for q in qs}
    for i, q in enumerate(qs):
        d = q["period_end"]
        try:
            ya = by_end.get(d.replace(year=d.year - 1))
        except ValueError:
            ya = None
        prev = qs[i + 1] if i + 1 < len(qs) else None
        for k in ("revenue", "net_profit", "eps"):
            q[k + "_yoy"] = pct(q[k], ya[k]) if ya else None
            q[k + "_qoq"] = pct(q[k], prev[k]) if prev else None
    ttm = None
    if len(qs) >= 4:
        four = qs[:4]
        span = (four[0]["period_end"] - four[3]["period_end"]).days
        if 250 <= span <= 300:
            ttm = {}
            for k in ("revenue", "net_profit", "eps"):
                vals = [q[k] for q in four]
                ttm[k] = round(sum(vals), 2) if all(v is not None for v in vals) else None
    if qs[0]["revenue"] is not None and qs[0]["net_profit"] is not None and qs[0]["net_profit"] < 0:
        notes.append("the latest quarter is a loss")
    return {"quarters": qs[:quarters], "fields": fields, "ttm": ttm, "notes": notes}


def read_filings(doc, limit=4):
    """NSE corporates-financial-results -> newest results filings, with links."""
    rows = rows_of(doc)
    out = []
    for r in rows:
        keys = list(r)
        link = next((r[k] for k in keys if re.search(r"xbrl|attach|pdf|file|link", k, re.I)
                     and str(r[k]).startswith("http")), None)
        to = to_date(r.get(pick(keys, PERIOD_KEYS) or "") or "")
        filed_k = pick(keys, [r"broad_?cast", r"filing_?date", r"submission", r"exchdisstime", r"creation"])
        out.append({"period_end": to, "filed": str(r.get(filed_k) or "").strip() if filed_k else "",
                    "audited": str(r.get(pick(keys, [r"audit"]) or "") or "").strip(),
                    "basis": str(r.get(pick(keys, [r"consol"]) or "") or "").strip(),
                    "link": link or ""})
    out.sort(key=lambda f: (f["period_end"] or _dt.date(1900, 1, 1)), reverse=True)
    return out[:limit]


# ---------------------------------------------------------------- output

def _n(x, d=2):
    if x is None:
        return "-"
    return "{:,.{d}f}".format(x, d=d)


def _p(x):
    return "-" if x is None else "%+.1f%%" % x


def render(sym, res, filings=None):
    f = res["fields"]
    lines = ["%s: quarterly results as filed with NSE (amounts as NSE reports them, usually Rs lakh)" % sym]
    lines.append("  fields used: period=%s revenue=%s net_profit=%s eps=%s" % (
        f["period"], f["revenue"] or "-", f["net_profit"] or "-", f["eps"] or "-"))
    lines.append("  %-9s %-10s %16s %8s %8s %16s %8s %7s %9s %8s" % (
        "quarter", "ends", "revenue", "yoy", "qoq", "net profit", "yoy", "margin", "EPS", "yoy"))
    for q in res["quarters"]:
        lines.append("  %-9s %-10s %16s %8s %8s %16s %8s %7s %9s %8s" % (
            q["label"], q["period_end"].isoformat(), _n(q["revenue"]), _p(q["revenue_yoy"]), _p(q["revenue_qoq"]),
            _n(q["net_profit"]), _p(q["net_profit_yoy"]),
            ("%.1f%%" % q["net_margin"]) if q.get("net_margin") is not None else "-",
            _n(q["eps"]), _p(q["eps_yoy"])))
    if res["ttm"]:
        t = res["ttm"]
        lines.append("  last four quarters: revenue %s, net profit %s, EPS %s" % (
            _n(t["revenue"]), _n(t["net_profit"]), _n(t["eps"])))
    basis = {q["basis"] for q in res["quarters"] if q["basis"]}
    if basis:
        lines.append("  basis: %s" % ", ".join(sorted(basis)))
    for n in res["notes"]:
        lines.append("  NOTE: " + n)
    if filings:
        lines.append("  latest results filings on NSE:")
        for fl in filings:
            lines.append("    period %s, filed %s%s%s  %s" % (
                fl["period_end"].isoformat() if fl["period_end"] else "?", fl["filed"] or "?",
                (", " + fl["audited"]) if fl["audited"] else "", (", " + fl["basis"]) if fl["basis"] else "",
                fl["link"]))
    lines.append("  Numbers only, not advice. Check one figure against the filing before quoting it.")
    return "\n".join(lines) + "\n"


def metrics_row(sym, res):
    q = res["quarters"][0]
    return {"ticker": sym, "quarter": q["label"], "period_end": q["period_end"].isoformat(),
            "revenue": q["revenue"], "revenue_yoy_pct": q["revenue_yoy"], "net_profit": q["net_profit"],
            "net_profit_yoy_pct": q["net_profit_yoy"], "net_margin_pct": q.get("net_margin"), "eps": q["eps"],
            "eps_yoy_pct": q["eps_yoy"], "ttm": res["ttm"], "unit": "as reported by NSE (usually Rs lakh)"}


def _json_ready(o):
    if isinstance(o, dict):
        return {k: _json_ready(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_json_ready(v) for v in o]
    if isinstance(o, _dt.date):
        return o.isoformat()
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tickers", nargs="*", help="NSE symbols, e.g. RELIANCE TCS")
    ap.add_argument("--quarters", type=int, default=6)
    ap.add_argument("--no-filings", action="store_true", help="skip the list of results filings")
    ap.add_argument("--metrics", metavar="FILE", help="merge a row per symbol into this JSON")
    ap.add_argument("--offline", metavar="PATH", help="a saved results JSON, or a folder of "
                    "results-<SYMBOL>.json / filings-<SYMBOL>.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.tickers:
        ap.print_help()
        return 2
    fetcher = Fetcher(offline=args.offline)
    results, rows, failed = [], [], 0
    for t in args.tickers:
        sym = t.upper().replace(".NS", "")
        if sym.endswith(".BO"):
            print("facts: %s is a BSE symbol; this tool reads NSE. Use the NSE symbol." % t, file=sys.stderr)
            failed += 1
            continue
        q = urllib.parse.quote(sym)
        try:
            res = analyse(fetcher.json(RESULTS_URL % q, "results-%s.json" % sym, sym), quarters=args.quarters)
        except FactsError as exc:
            print("facts: %s: %s" % (sym, exc), file=sys.stderr)
            failed += 1
            continue
        filings = None
        if not args.no_filings:
            try:
                filings = read_filings(fetcher.json(FILINGS_URL % q, "filings-%s.json" % sym, sym))
            except FactsError as exc:
                res["notes"].append("filings list unavailable: %s" % exc)
        results.append({"ticker": sym, "result": res, "filings": filings})
        rows.append(metrics_row(sym, res))
        if not args.json:
            sys.stdout.write(render(sym, res, filings))
            sys.stdout.write("\n")
    if args.json:
        print(json.dumps(_json_ready(results), indent=2))
    if args.metrics and rows:
        existing = {}
        if os.path.isfile(args.metrics):
            with open(args.metrics, encoding="utf-8") as fh:
                existing = {r["ticker"]: r for r in json.load(fh).get("companies", [])}
        for r in rows:
            existing[r["ticker"]] = r
        folder = os.path.dirname(args.metrics)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.metrics, "w", encoding="utf-8") as fh:
            json.dump({"as_of": _dt.date.today().isoformat(),
                       "companies": sorted(existing.values(), key=lambda r: r["ticker"])}, fh, indent=2)
            fh.write("\n")
        if not args.json:
            print("wrote %s (%d companies)" % (args.metrics, len(existing)))
    return 0 if results and not failed else (1 if results else 2)


if __name__ == "__main__":
    sys.exit(main())
