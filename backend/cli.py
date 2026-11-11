import argparse
import csv
from datetime import date, datetime
from pathlib import Path

from .collectors import TAIPEI, collect
from .db import connect, migrate
from .reports import evaluate, market_sessions, write_report
from .sources import SOURCES, register_sources

CALENDAR_PUBLISHERS = {
    "TWSE": ("www.twse.com.tw", "wwwc.twse.com.tw", "accessibility.twse.com.tw"),
    "TPEX": ("www.tpex.org.tw", "tpex.org.tw"),
}


def import_calendar(path):
    from urllib.parse import urlsplit
    values = []
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            market, day, status, url = (row[k].strip() for k in ("market","day","status","evidence_url"))
            key = market, date.fromisoformat(day)
            address = urlsplit(url)
            if address.scheme != "https" or address.hostname not in CALENDAR_PUBLISHERS.get(market, ()) or status not in ("open","closed") or key in seen:
                raise ValueError(f"invalid or duplicate calendar entry: {market} {day}")
            seen.add(key)
            values.append((*key,status=="open",url))
    if not values:
        raise ValueError("calendar contains no entries")
    with connect() as db, db.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO market_calendar VALUES (%s,%s,%s,%s)
            ON CONFLICT (market,day) DO UPDATE SET is_open=EXCLUDED.is_open,evidence_url=EXCLUDED.evidence_url
        """, values)


def sync(ids):
    failures = 0
    for source in ids:
        try:
            print(source, collect(source), flush=True)
        except Exception as error:
            print(source, "error", type(error).__name__, flush=True)
            failures += 1
    return failures


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("migrate")
    commands.add_parser("evaluate")
    fetch = commands.add_parser("collect")
    fetch.add_argument("sources", nargs="*", choices=list(SOURCES))
    cal = commands.add_parser("calendar")
    cal.add_argument("csv",type=Path)
    report = commands.add_parser("run-slot")
    report.add_argument("slot",choices=("12:00","14:00","18:00"))
    report.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    migrate()
    with connect() as db:
        register_sources(db)
    if args.command == "collect":
        return int(bool(sync(args.sources or [s.id for s in SOURCES.values() if s.permitted])))
    if args.command == "calendar":
        import_calendar(args.csv)
    if args.command == "evaluate":
        with connect() as db:
            print("evaluated",evaluate(db))
    if args.command == "run-slot":
        now = datetime.now(TAIPEI)
        slot = datetime.fromisoformat(f"{args.date}T{args.slot}").replace(tzinfo=TAIPEI)
        if now.date()!=args.date or now<slot:
            parser.error("scheduled slots can only run on the target Taipei date after the slot time")
        with connect() as db:
            sessions = market_sessions(db, args.date)
            if db.execute("SELECT 1 FROM research_report WHERE day=%s AND slot=%s",(args.date,args.slot)).fetchone():
                print("unchanged")
                return 0
        if not any(sessions.values()):
            print("closed" if len(sessions)==2 else "calendar_pending")
            return int(len(sessions)!=2)
        kinds = {"12:00":(), "14:00":("master","quotes","flow"), "18:00":("master","quotes","flow","revenue","multiples")}[args.slot]
        failures = sync([s.id for s in SOURCES.values() if s.permitted and sessions.get(s.market) and s.kind in kinds])
        if failures:
            print("部分來源擷取失敗。報告仍保留可用資料，後續時段重新收集。")
        with connect() as db:
            print(write_report(db,args.date,args.slot))
            if args.slot=="18:00":
                print("evaluated",evaluate(db))
        return int(bool(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
