#!/usr/bin/env python3
"""Bulk and block deals tracker for trader-deals (NSE). Standard library only.

NSE publishes every day's bulk deals (one client trading more than 0.5% of a
company's shares in a day) and block deals (a single trade of Rs 10 crore or
more in the block window) with the client's name. This tool reads the day's
lists, alerts once per new deal, adds up the rupees per stock, and flags
deals in the stocks you watch, plan or hold.

    python3 deals.py                              # today's bulk + block deals, new ones only
    python3 deals.py --all                        # every deal on the lists, seen or not
    python3 deals.py --symbol RELIANCE TCS        # only these stocks
    python3 deals.py --client "MORGAN STANLEY" "LIC"   # only these buyers / sellers (any part of the name)
    python3 deals.py --min-cr 25                  # only deals worth Rs 25 crore or more
    python3 deals.py --offline DIR                # DIR/bulk.csv and DIR/block.csv instead of NSE

Sources (NSE's daily archive files; no key):
  https://nsearchives.nseindia.com/content/equities/bulk.csv
  https://nsearchives.nseindia.com/content/equities/block.csv
  (archives.nseindia.com as a fallback). Columns, trimmed: Date, Symbol,
  Security Name, Client Name, Buy/Sell, Quantity Traded,
  Trade Price / Wght. Avg. Price, and for bulk deals Remarks. The files hold
  the latest trading day; NSE posts them after the market closes. NSE
  sometimes refuses scripts: then download the two files in a browser
  (nseindia.com > Market Data > Large Deals) and use --offline.

Your stocks: trader/watchlist.json hits, trader/plan.json's symbol and
trader/portfolio.json positions are flagged with *. State: trader/state/deals.json
remembers the deals already shown (60 days), so each one alerts once.

A deal is public after the fact: it tells you who traded, not what happens
next. Exit code 0 when there is something new, 1 when not, 2 on an error.
"""

import argparse
import csv
import datetime as _dt
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

FILES = ("bulk", "block")
HOSTS = ("https://nsearchives.nseindia.com", "https://archives.nseindia.com")
PATH = "/content/equities/%s.csv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
CRORE = 1e7
KEEP_DAYS = 60


class DealsError(Exception):
    pass


# ---------------------------------------------------------------- fetching

def fetch(kind, offline=None, pause=0.5):
    """The text of bulk.csv or block.csv."""
    if offline:
        for name in (kind + ".csv", kind + ".csv.gz"):
            path = os.path.join(offline, name)
            if os.path.isfile(path):
                opener = gzip.open if path.endswith(".gz") else open
                with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        raise DealsError("offline: no %s.csv in %s" % (kind, offline))
    last = "no answer"
    for i, host in enumerate(HOSTS):
        if i:
            time.sleep(pause)
        req = urllib.request.Request(host + PATH % kind, headers={
            "User-Agent": UA, "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = "HTTP %d from %s" % (e.code, host.split("//")[1])
        except (urllib.error.URLError, OSError) as e:
            last = "could not reach %s: %s" % (host.split("//")[1], getattr(e, "reason", e))
    raise DealsError("%s.csv: %s. Download it from nseindia.com (Market Data > Large Deals) and use "
                     "--offline DIR" % (kind, last))


# ---------------------------------------------------------------- parsing

def _col(hdr, *pats):
    for p in pats:
        rx = re.compile(p, re.I)
        for i, h in enumerate(hdr):
            if rx.search(h):
                return i
    return None


def _num(s):
    s = str(s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _date(s):
    s = str(s or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_deals(text, kind):
    """bulk.csv / block.csv -> deals. A file with only a header (no deals that day) -> []."""
    text = (text or "").lstrip("﻿")
    if text.lstrip().startswith("<"):
        raise DealsError("%s.csv: NSE answered with a web page, not the CSV (it may have refused the script)"
                         % kind)
    rows = [r for r in csv.reader(io.StringIO(text)) if r and any(c.strip() for c in r)]
    if not rows:
        return []
    hdr = [h.strip() for h in rows[0]]
    ix = {
        "date": _col(hdr, r"^date"),
        "symbol": _col(hdr, r"^symbol"),
        "name": _col(hdr, r"security|company"),
        "client": _col(hdr, r"client"),
        "side": _col(hdr, r"buy\s*/\s*sell|^side|buy.?sell"),
        "qty": _col(hdr, r"quantity|qty"),
        "price": _col(hdr, r"price"),
        "remarks": _col(hdr, r"remark"),
    }
    missing = [k for k in ("symbol", "client", "side", "qty", "price") if ix[k] is None]
    if missing:
        raise DealsError("%s.csv has no %s column (header: %s)" % (kind, ", ".join(missing), ", ".join(hdr)))
    out = []
    for r in rows[1:]:
        def g(k):
            i = ix[k]
            return r[i].strip() if i is not None and i < len(r) else ""
        qty, price = _num(g("qty")), _num(g("price"))
        if not g("symbol") or qty is None or price is None:
            continue
        side = g("side").upper()
        side = "BUY" if side.startswith("B") else "SELL" if side.startswith("S") else side
        d = _date(g("date"))
        deal = {"kind": kind, "date": d.isoformat() if d else g("date"), "symbol": g("symbol").upper(),
                "name": " ".join(g("name").split()), "client": " ".join(g("client").split()),
                "side": side, "qty": int(qty) if qty == int(qty) else qty, "price": price,
                "value_cr": round(qty * price / CRORE, 2), "remarks": g("remarks")}
        deal["id"] = hashlib.sha1(("%s|%s|%s|%s|%s|%s|%s" % (
            kind, deal["date"], deal["symbol"], deal["client"], side, qty, price)).encode("utf-8")).hexdigest()[:16]
        out.append(deal)
    return out


# ---------------------------------------------------------------- your stocks, state

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def your_symbols(watchlist="trader/watchlist.json", plan="trader/plan.json", portfolio="trader/portfolio.json"):
    out = set()
    for h in (load_json(watchlist) or {}).get("hits", []):
        s = h.get("symbol") or h.get("ticker")
        if s:
            out.add(s.upper().replace(".NS", ""))
    p = (load_json(plan) or {}).get("symbol")
    if p:
        out.add(p.upper().replace(".NS", ""))
    for pos in (load_json(portfolio) or {}).get("positions", []):
        s = pos.get("ticker") or pos.get("symbol")
        if s:
            out.add(s.upper().replace(".NS", ""))
    return out


def select(deals, symbols=None, clients=None, min_cr=0.0):
    out = []
    syms = {s.upper().replace(".NS", "") for s in symbols or []}
    cls = [c.upper() for c in clients or []]
    for d in deals:
        if syms and d["symbol"] not in syms:
            continue
        if cls and not any(c in d["client"].upper() for c in cls):
            continue
        if d["value_cr"] < min_cr:
            continue
        out.append(d)
    out.sort(key=lambda d: (-d["value_cr"], d["symbol"]))
    return out


def by_symbol(deals):
    """{symbol: {"buy_cr", "sell_cr", "net_cr", "deals"}}"""
    agg = {}
    for d in deals:
        a = agg.setdefault(d["symbol"], {"symbol": d["symbol"], "name": d["name"], "buy_cr": 0.0,
                                         "sell_cr": 0.0, "deals": 0})
        a["buy_cr" if d["side"] == "BUY" else "sell_cr"] += d["value_cr"]
        a["deals"] += 1
    for a in agg.values():
        a["buy_cr"], a["sell_cr"] = round(a["buy_cr"], 2), round(a["sell_cr"], 2)
        a["net_cr"] = round(a["buy_cr"] - a["sell_cr"], 2)
    return sorted(agg.values(), key=lambda a: -(a["buy_cr"] + a["sell_cr"]))


def prune(state, today):
    seen = state.setdefault("seen", {})
    cutoff = (today - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    for k in [k for k, v in seen.items() if v < cutoff]:
        del seen[k]
    return seen


# ---------------------------------------------------------------- output

def render(shown, mine, totals, errors, new_count, all_mode):
    lines = []
    dates = sorted({d["date"] for d in shown})
    head = "NSE bulk and block deals%s: %d %s" % (
        (" for " + ", ".join(dates)) if dates else "", len(shown), "deals" if all_mode else "new deals")
    lines.append(head)
    if not shown:
        lines.append("  nothing new since the last check" if not all_mode else "  no deals matched")
    for d in shown:
        flag = "*" if d["symbol"] in mine else " "
        lines.append("%s %-5s %-12s %-4s %12s @ %10s = Rs %8.2f cr  %s" % (
            flag, d["kind"], d["symbol"], d["side"], "{:,}".format(d["qty"]), "{:,.2f}".format(d["price"]),
            d["value_cr"], d["client"]))
    if totals:
        lines.append("")
        lines.append("By stock (Rs crore): bought / sold / net")
        for a in totals[:15]:
            lines.append("  %s %-12s %9.2f / %9.2f / %+9.2f  (%d deal%s)" % (
                "*" if a["symbol"] in mine else " ", a["symbol"], a["buy_cr"], a["sell_cr"], a["net_cr"],
                a["deals"], "" if a["deals"] == 1 else "s"))
    if any(d["symbol"] in mine for d in shown):
        lines.append("* = a stock on your watchlist, plan or portfolio.")
    for e in errors:
        lines.append("note: " + e)
    lines.append("Deals are public after the fact: who traded, not what comes next. Not financial advice.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", nargs="*", help="only these NSE symbols")
    ap.add_argument("--client", nargs="*", help="only clients whose name contains one of these")
    ap.add_argument("--min-cr", type=float, default=0.0, help="only deals worth at least this many Rs crore")
    ap.add_argument("--kind", choices=["bulk", "block", "both"], default="both")
    ap.add_argument("--all", action="store_true", help="show deals already seen too")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--state", default="trader/state/deals.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--today", help="YYYY-MM-DD, for the state's pruning (default: today)")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    kinds = FILES if a.kind == "both" else (a.kind,)
    deals, errors = [], []
    for k in kinds:
        try:
            deals += parse_deals(fetch(k, a.offline), k)
        except DealsError as e:
            errors.append(str(e))
    if not deals and errors and len(errors) == len(kinds):
        for e in errors:
            print("deals: " + e, file=sys.stderr)
        return 2
    today = _dt.date.fromisoformat(a.today) if a.today else _dt.date.today()
    state = load_json(a.state) or {}
    seen = prune(state, today)
    matched = select(deals, a.symbol, a.client, a.min_cr)
    new = [d for d in matched if d["id"] not in seen]
    shown = matched if a.all else new
    mine = your_symbols(a.watchlist, a.plan, a.portfolio)
    totals = by_symbol(shown)
    if a.json:
        print(json.dumps({"deals": [dict(d, yours=d["symbol"] in mine, new=d["id"] not in seen) for d in shown],
                          "by_symbol": totals, "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, mine, totals, errors, len(new), a.all))
    if not a.dry_run:
        for d in matched:
            seen.setdefault(d["id"], today.isoformat())
        folder = os.path.dirname(a.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(a.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if new else 1


if __name__ == "__main__":
    sys.exit(main())
