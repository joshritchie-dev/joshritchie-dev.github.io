"""Fetch state-level housing data from FRED and write data/housing.json.

Runs weekly from .github/workflows/housing.yml. Uses the FRED_API_KEY secret.

Sources (all through FRED, the St. Louis Fed's data service):
  Realtor.com Housing Inventory Core Metrics (monthly, by state)
    MEDLISPRI<ST>   median listing price
    ACTLISCOU<ST>   active listing count
    MEDDAYONMAR<ST> median days on market
  FHFA All-Transactions House Price Index (quarterly, by state)
    <ST>STHPI

If a request fails, that series keeps its value from the previous run, so one
bad week never blanks a state on the map.
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "housing.json"
FRED_URL = os.environ.get("FRED_URL", "https://api.stlouisfed.org/fred/series/observations")
PAUSE = float(os.environ.get("FRED_PAUSE", "0.6"))   # FRED allows about 120 requests a minute
TIMEOUT = 30
MONTHS_KEPT = 61        # five years plus one month, so a 5-year change can be shown
QUARTERS_KEPT = 41      # ten years plus one quarter

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# key -> (series id pattern, frequency)
SERIES = {
    "price":    ("MEDLISPRI{st}", "M"),
    "listings": ("ACTLISCOU{st}", "M"),
    "dom":      ("MEDDAYONMAR{st}", "M"),
    "hpi":      ("{st}STHPI", "Q"),
}


def redact(msg, key=None):
    """Remove API keys from error text: request URLs carry the key, and errors are saved publicly."""
    msg = re.sub(r"(api_key|registrationkey)=[^&\s'\")]+", r"\1=***", str(msg))
    return msg.replace(key, "***") if key and len(key) >= 8 else msg


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None          # FRED marks missing values with "."


def fetch(series_id, key, start, session):
    """Return [(date, value), ...] oldest first. Retries briefly on rate limits and server errors."""
    for attempt in range(4):
        r = session.get(FRED_URL, params={"series_id": series_id, "api_key": key,
                                          "file_type": "json", "observation_start": start},
                        timeout=TIMEOUT)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(2 * (attempt + 1) + PAUSE)
            continue
        if r.status_code == 400 and "does not exist" in r.text:
            raise LookupError(f"{series_id} does not exist on FRED")
        r.raise_for_status()
        obs = r.json().get("observations", [])
        return [(o["date"], v) for o in obs if (v := num(o["value"])) is not None]
    raise RuntimeError(f"{series_id}: gave up after retries")


def pack(points, freq, keep):
    """Compact form for the page: first date, frequency, and a list of values."""
    points = points[-keep:]
    if not points:
        return None
    # fill any gap so the list lines up with consecutive periods
    step = 1 if freq == "M" else 3
    start = dt.date.fromisoformat(points[0][0])
    by_date = dict(points)
    values, d = [], start
    end = dt.date.fromisoformat(points[-1][0])
    while d <= end:
        v = by_date.get(d.isoformat())
        values.append(round(v, 2) if v is not None else None)
        m = d.month - 1 + step
        d = dt.date(d.year + m // 12, m % 12 + 1, 1)
    return {"start": start.isoformat(), "freq": freq, "v": values}


def change(series, periods_back, kind="pct"):
    """Change between the latest value and the one `periods_back` periods earlier."""
    if not series:
        return None
    v = series["v"]
    if len(v) <= periods_back or v[-1] is None or v[-1 - periods_back] in (None, 0):
        return None
    a, b = v[-1 - periods_back], v[-1]
    return round((b / a - 1) * 100, 1) if kind == "pct" else round(b - a, 1)


def metrics(s):
    """Headline numbers for one state (or the U.S.) from its packed series."""
    p, l, d, h = (s.get(k) for k in ("price", "listings", "dom", "hpi"))
    last = lambda x: x["v"][-1] if x and x["v"] and x["v"][-1] is not None else None
    return {
        "price": last(p),
        "price_yoy": change(p, 12),
        "listings": last(l),
        "listings_yoy": change(l, 12),
        "dom": last(d),
        "dom_yoy": change(d, 12, "diff"),
        "hpi_yoy": change(h, 4),
        "hpi_5y": change(h, 20),
    }


def main():
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        print("FRED_API_KEY is not set.", file=sys.stderr)
        return 1

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text())
        except ValueError:
            previous = {}

    today = dt.date.today()
    starts = {"M": dt.date(today.year - 6, today.month, 1).isoformat(),
              "Q": dt.date(today.year - 11, 1, 1).isoformat()}
    keep = {"M": MONTHS_KEPT, "Q": QUARTERS_KEPT}

    places = dict(STATES, US="United States")
    out, errors, fetched, failed = {}, [], 0, 0
    session = requests.Session()
    for st, name in places.items():
        entry = {"name": name}
        old = (previous.get("us") if st == "US" else previous.get("states", {}).get(st)) or {}
        for k, (pattern, freq) in SERIES.items():
            sid = pattern.format(st=st)
            try:
                pts = fetch(sid, key, starts[freq], session)
                packed = pack(pts, freq, keep[freq])
                if packed is None:
                    raise LookupError(f"{sid} returned no data")
                entry[k] = packed
                fetched += 1
            except Exception as exc:
                failed += 1
                errors.append(redact(f"{sid}: {exc}", key))
                if old.get(k):
                    entry[k] = old[k]          # keep last week's numbers
            time.sleep(PAUSE)
        entry["m"] = metrics(entry)
        out[st] = entry

    if fetched == 0:
        print("Every request failed; leaving the existing file untouched.", file=sys.stderr)
        for e in errors[:10]:
            print("  " + e, file=sys.stderr)
        return 1

    def latest(k):
        dates = []
        for e in out.values():
            s = e.get(k)
            if s:
                n = len(s["v"]) - 1
                d = dt.date.fromisoformat(s["start"])
                m = d.month - 1 + n * (1 if s["freq"] == "M" else 3)
                dates.append(dt.date(d.year + m // 12, m % 12 + 1, 1))
        return max(dates).isoformat() if dates else None

    us = out.pop("US")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "latest": {"listings": latest("price"), "hpi": latest("hpi")},
        "us": us,
        "states": out,
        "errors": errors,
    }, separators=(",", ":")))
    print(f"Wrote {OUT.relative_to(ROOT)}: {fetched} series fetched, {failed} failed.")
    for e in errors[:20]:
        print("  warning: " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
