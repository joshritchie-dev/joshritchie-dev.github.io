"""Fetch U.S. economic indicators from BLS and FRED and write data/economy.json.

Runs once a day from .github/workflows/economy.yml. Keys come from environment
variables (GitHub secrets), never from this file:
  BLS_API_KEY   optional; without it the script uses the BLS v1 API (25 queries/day)
  FRED_API_KEY  needed for the FRED metrics; without it those metrics are skipped

If a source fails, the previous value for each affected metric is kept and marked
stale, so one bad morning never blanks the dashboard.
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "economy.json"
BLS_URL = os.environ.get("BLS_URL", "https://api.bls.gov/publicAPI/{ver}/timeseries/data/")
FRED_URL = os.environ.get("FRED_URL", "https://api.stlouisfed.org/fred/series/observations")
HISTORY_POINTS = 36          # points kept per metric for the charts
TIMEOUT = 30

# --- what to show ---------------------------------------------------------
# kind: how the raw series becomes the displayed number
#   level   the value as published
#   yoy     percent change from 12 months earlier (monthly series)
#   diff    change from the previous month (payrolls, in thousands)
BLS_METRICS = [
    dict(id="cpi", label="Inflation (CPI)", series="CUUR0000SA0", kind="yoy", unit="%",
         noun="Consumer prices", what="were up {v} from a year earlier",
         source="BLS, Consumer Price Index", url="https://www.bls.gov/cpi/"),
    dict(id="core_cpi", label="Core inflation", series="CUUR0000SA0L1E", kind="yoy", unit="%",
         noun="Prices excluding food and energy", what="were up {v} from a year earlier",
         source="BLS, Consumer Price Index", url="https://www.bls.gov/cpi/"),
    dict(id="unemployment", label="Unemployment rate", series="LNS14000000", kind="level", unit="%",
         noun="The unemployment rate", what="was {v}",
         source="BLS, Current Population Survey", url="https://www.bls.gov/cps/"),
    dict(id="payrolls", label="Jobs added", series="CES0000000001", kind="diff", unit="k",
         noun="Employers", what="added {v} jobs",
         source="BLS, Current Employment Statistics", url="https://www.bls.gov/ces/"),
    dict(id="wages", label="Wage growth", series="CES0500000003", kind="yoy", unit="%",
         noun="Average hourly pay", what="was up {v} from a year earlier",
         source="BLS, Current Employment Statistics", url="https://www.bls.gov/ces/"),
    dict(id="openings", label="Job openings", series="JTS000000000000000JOL", kind="level", unit="m",
         noun="Job openings", what="stood at {v}",
         source="BLS, JOLTS", url="https://www.bls.gov/jlt/"),
]
FRED_METRICS = [
    dict(id="fed_funds", label="Fed funds rate", series="DFEDTARU", lower="DFEDTARL", kind="level", unit="range",
         freq="daily", noun="The Federal Reserve's target rate", what="is {v}",
         source="Federal Reserve, via FRED", url="https://fred.stlouisfed.org/series/DFEDTARU"),
    dict(id="treasury_10y", label="10-year Treasury", series="DGS10", kind="level", unit="%",
         freq="daily", noun="The 10-year Treasury yield", what="was {v}",
         source="U.S. Treasury, via FRED", url="https://fred.stlouisfed.org/series/DGS10"),
    dict(id="mortgage_30y", label="30-year mortgage", series="MORTGAGE30US", kind="level", unit="%",
         freq="weekly", noun="The average 30-year mortgage rate", what="was {v}",
         source="Freddie Mac, via FRED", url="https://fred.stlouisfed.org/series/MORTGAGE30US"),
    dict(id="gdp", label="GDP growth", series="A191RL1Q225SBEA", kind="level", unit="%",
         freq="quarterly", noun="The economy", what="grew at a {v} annual rate",
         source="BEA, via FRED", url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA"),
]


# --- helpers --------------------------------------------------------------
def redact(msg):
    """Remove API keys from error text: request URLs carry the key, and errors are saved publicly."""
    msg = re.sub(r"(api_key|registrationkey)=[^&\s'\")]+", r"\1=***", str(msg))
    for k in (os.environ.get("BLS_API_KEY", "").strip(), os.environ.get("FRED_API_KEY", "").strip()):
        if k:
            msg = msg.replace(k, "***")
    return msg


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None          # BLS uses "-" and FRED uses "." for missing values


def fmt(value, unit, signed=False, dp=1):
    if value is None:
        return "n/a"
    if unit == "%":
        return f"{value:+.{dp}f}%" if signed else f"{value:.{dp}f}%"
    if unit == "k":
        return f"{value:+,.0f}k" if signed else f"{value:,.0f}k"
    if unit == "m":
        return f"{value:+.2f}m" if signed else f"{value:.2f}m"
    return f"{value:.2f}"


def precision(unit, freq):
    """Decimal places people normally quote: 3.1% for monthly stats, 4.12% for market rates."""
    if unit == "k":
        return 0
    if unit == "m" or freq in ("daily", "weekly"):
        return 2
    return 1


def month_label(date):
    return dt.date.fromisoformat(date).strftime("%B %Y")


def period_label(date, freq):
    d = dt.date.fromisoformat(date)
    if freq == "quarterly":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    if freq in ("daily", "weekly"):
        return d.strftime("%b %-d, %Y")
    return d.strftime("%B %Y")


# --- BLS ------------------------------------------------------------------
def fetch_bls():
    key = os.environ.get("BLS_API_KEY", "").strip()
    year = dt.date.today().year
    body = {"seriesid": [m["series"] for m in BLS_METRICS],
            "startyear": str(year - 5), "endyear": str(year)}
    if key:
        body["registrationkey"] = key
    url = BLS_URL.format(ver="v2" if key else "v1")
    r = requests.post(url, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError("BLS: " + ("; ".join(data.get("message", [])) or str(data.get("status"))))
    out = {}
    for s in data["Results"]["series"]:
        pts = []
        for row in s["data"]:
            p = row["period"]
            if not p.startswith("M") or p == "M13":   # skip annual averages
                continue
            v = num(row["value"])
            if v is not None:
                pts.append((f"{row['year']}-{p[1:]}-01", v))
        out[s["seriesID"]] = sorted(pts)
    return out


def transform(pts, kind):
    """Turn raw monthly points into the displayed series."""
    if kind == "level":
        return pts
    by_date = dict(pts)
    res = []
    for date, v in pts:
        d = dt.date.fromisoformat(date)
        if kind == "yoy":
            prev = by_date.get(f"{d.year - 1}-{d.month:02d}-01")
            if prev:
                res.append((date, round((v / prev - 1) * 100, 2)))
        elif kind == "diff":
            pm = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1).isoformat()
            if pm in by_date:
                res.append((date, round(v - by_date[pm], 1)))
    return res


# --- FRED -----------------------------------------------------------------
def fetch_fred_series(series_id, key, start):
    r = requests.get(FRED_URL, params={"series_id": series_id, "api_key": key, "file_type": "json",
                                       "observation_start": start}, timeout=TIMEOUT)
    r.raise_for_status()
    pts = [(o["date"], num(o["value"])) for o in r.json().get("observations", [])]
    return [(d, v) for d, v in pts if v is not None]


def thin(pts, freq):
    """Keep charts readable: one point per month for daily/weekly series."""
    if freq not in ("daily", "weekly"):
        return pts
    last = {}
    for d, v in pts:
        last[d[:7]] = (d, v)
    res = [last[k] for k in sorted(last)]
    if pts and res[-1] != pts[-1]:
        res[-1] = pts[-1]
    return res


# --- metric assembly --------------------------------------------------------
def build_metric(m, series, freq="monthly", display=None):
    if not series:
        return None
    unit = "%" if m["unit"] == "range" else m["unit"]
    dp = precision(unit, freq)
    hist = series[-HISTORY_POINTS:]
    date, value = series[-1]
    prev = series[-2] if len(series) > 1 else None
    v_txt = display or fmt(value, unit, signed=m["kind"] == "diff", dp=dp)

    what = m["what"]
    if m["kind"] == "yoy" and value < 0:
        what, v_say = what.replace("up", "down"), fmt(abs(value), unit, dp=dp)
    elif m["kind"] == "diff":
        what = "added {v} jobs" if value >= 0 else "cut {v} jobs"
        v_say = fmt(abs(value), unit, dp=dp)
    else:
        v_say = v_txt
    sentence = f"{m['noun']} {what.format(v=v_say)}"
    sentence += f" in {period_label(date, freq)}" if freq in ("monthly", "quarterly") else f" as of {period_label(date, freq)}"

    change = None
    if prev is not None:
        change = round(value - prev[1], 4)
        if m["kind"] == "diff":
            p = prev[1]
            sentence += (f", after {fmt(p, unit, dp=dp)} the month before." if p >= 0
                         else f", after a loss of {fmt(abs(p), unit, dp=dp)} the month before.")
        else:
            r = lambda v: round(v, dp)
            prev_txt = fmt(prev[1], unit, dp=dp)
            if r(value) == r(prev[1]):
                sentence += f", unchanged from {period_label(prev[0], freq)}."
            else:
                rising = r(value) > r(prev[1])
                streak = 1
                for i in range(len(series) - 2, 0, -1):
                    a, b = r(series[i][1]), r(series[i - 1][1])
                    if a == b or (a > b) != rising:
                        break
                    streak += 1
                sentence += f", {'up' if rising else 'down'} from {prev_txt}"
                if streak >= 3 and freq != "daily":
                    word = {"monthly": "months", "weekly": "weeks", "quarterly": "quarters"}[freq]
                    sentence += f" ({streak} {word} in a row)"
                sentence += "."
    else:
        sentence += "."
    return {
        "id": m["id"], "label": m["label"], "unit": m["unit"], "kind": m["kind"], "decimals": dp,
        "value": value, "display": v_txt, "date": date, "period": period_label(date, freq),
        "change": change, "summary": sentence, "source": m["source"], "source_url": m["url"],
        "history": [[d, v] for d, v in hist], "stale": False,
    }


def main():
    previous = {}
    if OUT.exists():
        try:
            previous = {m["id"]: m for m in json.loads(OUT.read_text())["metrics"]}
        except (ValueError, KeyError):
            previous = {}
    metrics, errors = {}, []

    try:
        raw = fetch_bls()
        for m in BLS_METRICS:
            series = transform(raw.get(m["series"], []), m["kind"])
            if m["unit"] == "m":
                series = [(d, round(v / 1000, 3)) for d, v in series]   # thousands -> millions
            res = build_metric(m, series)
            if res:
                metrics[m["id"]] = res
            else:
                errors.append(f"BLS returned no data for {m['series']}")
    except Exception as exc:  # keep going with FRED
        errors.append(f"BLS request failed: {exc}")

    fred_key = os.environ.get("FRED_API_KEY", "").strip()
    if not fred_key:
        errors.append("FRED_API_KEY not set; FRED metrics skipped")
    else:
        today = dt.date.today()
        for m in FRED_METRICS:
            try:
                start = (today - dt.timedelta(days=365 * (9 if m["freq"] == "quarterly" else 3))).isoformat()
                series = fetch_fred_series(m["series"], fred_key, start)
                display = None
                if m.get("lower"):
                    lower = fetch_fred_series(m["lower"], fred_key, start)
                    if lower and series:
                        display = f"{lower[-1][1]:.2f}% to {series[-1][1]:.2f}%"
                res = build_metric(m, thin(series, m["freq"]), m["freq"], display)
                if res:
                    metrics[m["id"]] = res
                else:
                    errors.append(f"FRED returned no data for {m['series']}")
            except Exception as exc:
                errors.append(f"FRED {m['series']} failed: {exc}")

    order = [m["id"] for m in BLS_METRICS + FRED_METRICS]
    final = []
    for mid in order:
        if mid in metrics:
            final.append(metrics[mid])
        elif mid in previous:
            old = dict(previous[mid]); old["stale"] = True
            final.append(old)

    # yield-curve note: 10-year minus 2-year is a common recession signal
    if fred_key and "treasury_10y" in metrics:
        try:
            two = fetch_fred_series("DGS2", fred_key, (dt.date.today() - dt.timedelta(days=30)).isoformat())
            if two:
                spread = metrics["treasury_10y"]["value"] - two[-1][1]
                shape = "above" if spread >= 0 else "below"
                metrics["treasury_10y"]["summary"] += (
                    f" It sits {abs(spread):.2f} points {shape} the 2-year yield"
                    + (" (an inverted curve, often read as a recession warning)." if spread < 0 else ".")
                )
        except Exception as exc:
            errors.append(f"FRED DGS2 failed: {exc}")

    if not final:
        print("No data at all; leaving the existing file untouched.", file=sys.stderr)
        for e in errors:
            print("  " + redact(e), file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "metrics": final,
        "errors": [redact(e) for e in errors],
    }, indent=1))
    print(f"Wrote {len(final)} metrics to {OUT.relative_to(ROOT)}")
    for e in errors:
        print("  warning: " + redact(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
