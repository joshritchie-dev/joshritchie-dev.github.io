"""Build the Michigan traffic dashboard data.

Loads the published tables in data/traffic/raw/ into a SQLite database,
runs the data checks and the queries in scripts/sql/, and writes
data/traffic.json for the dashboard page. Stops with an error if any
check fails, so a typo in a copied table never reaches the site.

Run from the repository root:  python scripts/build_traffic.py
Uses only the Python standard library.
"""

import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

YEAR = 2025  # latest full year of crash data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "traffic", "raw")
SQL_DIR = os.path.join(ROOT, "scripts", "sql")
SHAPES = os.path.join(ROOT, "data", "traffic", "mi_counties.json")
DB_OUT = os.path.join(ROOT, "data", "traffic", "traffic.db")
JSON_OUT = os.path.join(ROOT, "data", "traffic.json")

SCHEMA = """
CREATE TABLE county_crashes (
  year INTEGER NOT NULL, county TEXT NOT NULL, county_code TEXT,
  total INTEGER NOT NULL, fatal INTEGER NOT NULL, injury INTEGER NOT NULL, pdo INTEGER NOT NULL,
  interstate INTEGER, us_route INTEGER, state_route INTEGER, local_street INTEGER, route_unknown INTEGER,
  PRIMARY KEY (year, county));
CREATE TABLE deer_crashes (
  year INTEGER NOT NULL, county TEXT NOT NULL, deer_crashes INTEGER NOT NULL,
  PRIMARY KEY (year, county));
CREATE TABLE population (county TEXT PRIMARY KEY, population INTEGER NOT NULL);
CREATE TABLE statewide_by_year (
  year INTEGER PRIMARY KEY, crashes INTEGER NOT NULL,
  vmt_billions REAL, registered_vehicles_millions REAL, population_millions REAL);
CREATE TABLE time_of_day (
  year INTEGER, bin INTEGER, label TEXT, all_crashes INTEGER, deer_crashes INTEGER,
  PRIMARY KEY (year, bin));
CREATE TABLE day_of_week (year INTEGER, dow INTEGER, day TEXT, crashes INTEGER, PRIMARY KEY (year, dow));
CREATE TABLE month_totals (year INTEGER, month INTEGER, crashes INTEGER, PRIMARY KEY (year, month));
CREATE TABLE crash_types (crash_type TEXT PRIMARY KEY, crashes INTEGER);
CREATE TABLE statewide (measure TEXT PRIMARY KEY, value_2024 INTEGER, value_2025 INTEGER);
"""


def read_csv(name):
    with open(os.path.join(RAW, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    """CSV text to int/float; blank cells become NULL."""
    v = (v or "").strip().replace(",", "")
    if v == "":
        return None
    return float(v) if "." in v else int(v)


def insert(db, table, rows, columns, extra=None):
    extra = extra or {}
    cols = list(extra) + columns
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    text_cols = {"county", "county_code", "label", "day", "crash_type", "measure"}
    db.executemany(sql, [
        list(extra.values()) + [r[c].strip() if c in text_cols else num(r[c]) for c in columns]
        for r in rows])


def load(db):
    db.executescript(SCHEMA)
    insert(db, "county_crashes", read_csv(f"county_crashes_{YEAR}.csv"),
           ["county_code", "county", "total", "fatal", "injury", "pdo", "interstate",
            "local_street", "state_route", "us_route", "route_unknown"], {"year": YEAR})
    insert(db, "county_crashes", read_csv(f"county_crashes_{YEAR - 1}.csv"),
           ["county", "total", "fatal", "injury", "pdo", "interstate", "us_route",
            "state_route", "local_street"], {"year": YEAR - 1})
    for y in (YEAR, YEAR - 1):
        insert(db, "deer_crashes", read_csv(f"deer_county_{y}.csv"), ["county", "deer_crashes"], {"year": y})
    insert(db, "population", read_csv("population_2024.csv"), ["county", "population"])
    insert(db, "statewide_by_year", read_csv("statewide_by_year.csv"),
           ["year", "crashes", "vmt_billions", "registered_vehicles_millions", "population_millions"])
    insert(db, "time_of_day", read_csv("time_of_day.csv"),
           ["year", "bin", "label", "all_crashes", "deer_crashes"])
    insert(db, "day_of_week", read_csv("day_of_week.csv"), ["year", "dow", "day", "crashes"])
    insert(db, "month_totals", read_csv("month.csv"), ["year", "month", "crashes"])
    insert(db, "crash_types", read_csv(f"crash_type_{YEAR}.csv"), ["crash_type", "crashes"])
    insert(db, "statewide", read_csv(f"statewide_{YEAR}.csv"), ["measure", "value_2024", "value_2025"])
    db.commit()


def query(db, filename):
    with open(os.path.join(SQL_DIR, filename), encoding="utf-8") as f:
        sql = f.read()
    params = {"year": YEAR} if ":year" in sql else {}
    cur = db.execute(sql, params)
    names = [c[0] for c in cur.description]
    return sql, [dict(zip(names, row)) for row in cur.fetchall()]


def main():
    if os.path.exists(DB_OUT):
        os.remove(DB_OUT)
    db = sqlite3.connect(DB_OUT)
    load(db)

    queries, results = {}, {}
    for name in sorted(os.listdir(SQL_DIR)):
        if name.endswith(".sql"):
            queries[name], results[name] = query(db, name)

    checks = [dict(r, passed=(r["expected"] == r["actual"])) for r in results["01_checks.sql"]]
    for c in checks:
        print(("PASS " if c["passed"] else "FAIL ") + c["check_name"], f"(expected {c['expected']}, got {c['actual']})")
    if not all(c["passed"] for c in checks):
        db.close()
        sys.exit("Data checks failed. Fix the raw files before publishing.")

    s = {m: {"value_2024": a, "value_2025": b}
         for m, a, b in db.execute("SELECT measure, value_2024, value_2025 FROM statewide")}
    total, deer = s["total_crashes"]["value_2025"], s["deer_crashes"]["value_2025"]
    days = 366 if YEAR % 4 == 0 else 365
    vmt_miles = s["vmt_thousands"]["value_2025"] * 1000

    # Road types: the MTCF summaries leave out crashes with no route recorded,
    # so report how many fall outside the four named road types.
    unknown_route = db.execute(
        "SELECT SUM(total - interstate - us_route - state_route - local_street) FROM county_crashes WHERE year = ?",
        (YEAR - 1,)).fetchone()[0]

    with open(SHAPES, encoding="utf-8") as f:
        shapes = json.load(f)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "year": YEAR,
        "headline": {
            "crashes": total,
            "crashes_prev": s["total_crashes"]["value_2024"],
            "per_day": round(total / days),
            "deer": deer,
            "deer_share": round(100 * deer / total, 1),
            "licensed_drivers": s["licensed_drivers"]["value_2025"],
            "registrations": s["vehicle_registrations"]["value_2025"],
            "miles_driven": vmt_miles,
            "miles_per_crash": round(vmt_miles / total),
            "drivers_in_crashes": s["drivers_in_crashes"]["value_2025"],
        },
        "statewide": {k: {"prev": v["value_2024"], "cur": v["value_2025"]} for k, v in s.items()
                      if v["value_2024"] is not None},
        "counties": {r["county"]: r for r in results["02_counties.sql"]},
        "trend": results["03_trend.sql"],
        "time_of_day": results["04_time_of_day.sql"],
        "day_of_week": results["05_day_of_week.sql"],
        "month": results["06_month.sql"],
        "crash_types": results["07_crash_types.sql"],
        "checks": checks,
        "flags": results["08_flags.sql"],
        "notes": {"unknown_route_prev_year": unknown_route},
        "queries": {k: v for k, v in queries.items()},
        "shapes": shapes,
    }
    db.close()
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote {os.path.relpath(JSON_OUT, ROOT)} ({os.path.getsize(JSON_OUT) // 1024} KB) "
          f"and {os.path.relpath(DB_OUT, ROOT)}")


if __name__ == "__main__":
    main()
