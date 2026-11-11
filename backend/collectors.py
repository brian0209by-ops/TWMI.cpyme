import hashlib
import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .db import connect
from .sources import SOURCES, Source, register_sources

TAIPEI = ZoneInfo("Asia/Taipei")
MISSING = {"", "--", "---", "-", "N/A", "NA", "除權", "除息", "除權息", "X", "X0.00"}
SECURITY_CODE = re.compile(r"[A-Z0-9]{2,12}")
ETF_CODE = re.compile(r"00[0-9]{2,4}[A-Z]?")
ORDINARY_CODE = re.compile(r"[1-9][0-9]{3}")
MAX_RESPONSE = 12 * 1024 * 1024


def parse_date(value, month=False):
    raw = re.sub(r"[/\-]", "", str(value).strip())
    if not raw.isdecimal():
        raise ValueError("invalid date")
    size = 2 if month else 4
    if len(raw) not in (size + 3, size + 4):
        raise ValueError("invalid date length")
    year = int(raw[:-size]) + (1911 if len(raw) == size + 3 else 0)
    return date(year, int(raw[-size:][:2]), 1 if month else int(raw[-2:]))


def numeric(value, *, integral=False, nonnegative=False):
    raw = str(value if value is not None else "").strip().replace(",", "").replace("＋", "+").replace("－", "-")
    if raw.upper() in MISSING:
        return None
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", raw):
        raise ValueError("invalid numeric field")
    result = Decimal(raw)
    if nonnegative and result < 0:
        raise ValueError("negative numeric field")
    if integral:
        if result != result.to_integral_value() or not -(2**63) <= result < 2**63:
            raise ValueError("invalid integer field")
        return int(result)
    return result


def normalize(source, payload):
    if not isinstance(payload, list) or len(payload) < source.minimum:
        raise ValueError("response row count below source threshold")
    if not payload or any(not isinstance(row, dict) for row in payload):
        raise ValueError("response must contain records")
    twse = source.market == "TWSE"
    records = {}
    for row in payload:
        if source.kind == "master":
            code_key, day_key, name_key, group_key = (
                ("公司代號", "出表日期", "公司簡稱", "產業別") if twse else
                ("SecuritiesCompanyCode", "Date", "CompanyAbbreviation", "SecuritiesIndustryCode")
            )
            code = str(row[code_key]).strip()
            # The exchange numbering convention reserves 91xx for depositary receipts.
            if not ORDINARY_CODE.fullmatch(code) or code.startswith("91"):
                continue
            day = parse_date(row[day_key])
            industry = str(row[group_key]).strip()
            name = str(row[name_key]).strip()
            if not re.fullmatch(r"[0-9]{1,2}", industry) or not name:
                raise ValueError("unrecognized company master row")
            fields = (name, industry.zfill(2))
        elif source.kind == "revenue":
            code = str(row["公司代號"]).strip()
            day = parse_date(row["資料年月"], month=True)
            export_day = parse_date(row["出表日期"])
            if export_day < day:
                raise ValueError("revenue export precedes its reporting month")
            fields = (export_day, *(numeric(row[k]) for k in (
                "營業收入-當月營收", "營業收入-上月營收", "營業收入-去年當月營收"
            )))
        else:
            code = str(row["Code" if twse else "SecuritiesCompanyCode"]).strip()
            day = parse_date(row["Date"])
            if source.kind == "quotes":
                names = ("OpeningPrice", "HighestPrice", "LowestPrice", "ClosingPrice", "Change", "TradeVolume", "TradeValue") if twse else (
                    "Open", "High", "Low", "Close", "Change", "TradingShares", "TransactionAmount"
                )
                ohlc = tuple(numeric(row[k], nonnegative=True) or None for k in names[:4])
                opening, high, low, close = ohlc
                if high is not None and low is not None and (
                    high < low or any(v is not None and not low <= v <= high for v in (opening, close))
                ):
                    raise ValueError("OHLC is inconsistent")
                name = str(row["Name" if twse else "CompanyName"]).strip()
                fields = (*ohlc, numeric(row[names[4]]),
                          *(numeric(row[k], integral=True, nonnegative=True) for k in names[5:]), name)
            elif source.kind == "multiples":
                fields = tuple(numeric(row[k]) for k in (
                    ("PEratio","PBratio","DividendYield") if twse else
                    ("PriceEarningRatio","PriceBookRatio","YieldRatio")
                ))
            else:
                fields = tuple(numeric(row[k], integral=True) for k in (
                    "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference",
                    "SecuritiesInvestmentTrustCompanies-Difference", "Dealers-Difference",
                ))
        if not SECURITY_CODE.fullmatch(code):
            raise ValueError("invalid security code")
        key = (code, day)
        if key in records:
            raise ValueError("duplicate security and date")
        records[key] = fields

    dates = {day for _, day in records}
    now = datetime.now(TAIPEI).date()
    if not dates or max(dates) > now or (source.kind != "revenue" and len(dates) != 1):
        raise ValueError("source trading date is invalid or inconsistent")
    if source.kind == "quotes" and sum(fields[3] is not None and fields[6] is not None for fields in records.values()) < source.minimum:
        raise ValueError("too few usable price and turnover rows")
    if source.kind == "master" and len(records) < source.minimum:
        raise ValueError("too few ordinary shares in master")
    return records


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def fetch(source):
    opener = build_opener(NoRedirect())
    request = Request(source.url, headers={"Accept": "application/json", "User-Agent": "TWMI Signals official dataset client"})
    for attempt in range(3):
        try:
            with opener.open(request, timeout=15) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError("source response exceeded size limit")
                return raw
        except (URLError, TimeoutError) as error:
            if (isinstance(error, HTTPError) and error.code < 500) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _write_master(db, source, batch_id, day, records):
    current = {
        row["code"]: row for row in db.execute("""
            SELECT code,industry,lower(valid_during) AS since
            FROM official_membership WHERE market=%s AND upper_inf(valid_during)
        """, (source.market,))
    }
    same_day = bool(db.execute("""
        SELECT 1 FROM import_batch WHERE source_id=%s AND market_day=%s AND id<>%s
    """, (source.id, day, batch_id)).fetchone())
    if current and len(records) < len(current) * 0.92:
        raise ValueError("company master unexpectedly shrank by more than 8%")
    for (code, _), (name, industry) in records.items():
        db.execute("""
            INSERT INTO security VALUES (%s,%s,%s,'ordinary')
            ON CONFLICT (market,code) DO UPDATE SET name=EXCLUDED.name, kind='ordinary'
        """, (source.market, code, name))
        previous = current.pop(code, None)
        if previous and previous["industry"] == industry:
            continue
        if previous and previous["since"] == day:
            db.execute("""
                UPDATE official_membership SET industry=%s,batch_id=%s
                WHERE market=%s AND code=%s AND upper_inf(valid_during)
            """, (industry, batch_id, source.market, code))
            continue
        if previous:
            db.execute("""
                UPDATE official_membership SET valid_during=daterange(lower(valid_during),%s)
                WHERE market=%s AND code=%s AND upper_inf(valid_during)
            """, (day, source.market, code))
        db.execute("""
            INSERT INTO official_membership VALUES (%s,%s,%s,daterange(%s,NULL),%s)
        """, (source.market, code, industry, day, batch_id))
    for code, previous in current.items():
        if same_day and previous["since"] == day:
            db.execute("""
                DELETE FROM official_membership WHERE market=%s AND code=%s AND lower(valid_during)=%s
            """, (source.market, code, day))
        else:
            db.execute("""
                UPDATE official_membership SET valid_during=daterange(lower(valid_during),%s)
                WHERE market=%s AND code=%s AND upper_inf(valid_during)
            """, (day, source.market, code))


def ingest(source: Source, raw: bytes):
    if not source.permitted:
        raise ValueError("source is not authorized for automated intake")
    records = normalize(source, json.loads(raw))
    day = max(day for _, day in records)
    digest = hashlib.sha256(raw).hexdigest()
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (source.id,))
        allowed = db.execute("SELECT permitted FROM source_registry WHERE id=%s", (source.id,)).fetchone()
        if not allowed or not allowed["permitted"]:
            raise ValueError("source is disabled in registry")
        if source.kind == "master":
            newest = db.execute("SELECT max(market_day) AS day FROM import_batch WHERE source_id=%s", (source.id,)).fetchone()["day"]
            if newest and day < newest:
                raise ValueError("older company master cannot overwrite classification")
        batch = db.execute("""
            INSERT INTO import_batch (source_id,market_day,content_sha256,row_count)
            VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id
        """, (source.id, day, digest, len(records))).fetchone()
        if not batch:
            db.execute("INSERT INTO import_attempt (source_id,outcome) VALUES (%s,'unchanged')", (source.id,))
            return "unchanged"
        batch_id = batch["id"]
        if source.kind == "master":
            _write_master(db, source, batch_id, day, records)
        elif source.kind == "quotes":
            with db.cursor() as cur:
                cur.executemany("INSERT INTO quote VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
                    (batch_id, source.market, code, record_day, *fields[:-1])
                    for (code, record_day), fields in records.items()
                ))
                cur.executemany("""
                    INSERT INTO security VALUES (%s,%s,%s,'etf')
                    ON CONFLICT (market,code) DO NOTHING
                """, ((source.market, code, fields[-1]) for (code, _), fields in records.items()
                      if ETF_CODE.fullmatch(code) and fields[-1] and not code.endswith(("L","R","B"))))
        elif source.kind == "revenue":
            with db.cursor() as cur:
                cur.executemany("INSERT INTO revenue VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (
                    (batch_id, source.market, code, record_day, *fields)
                    for (code, record_day), fields in records.items()
                ))
        elif source.kind == "multiples":
            with db.cursor() as cur:
                cur.executemany("INSERT INTO valuation_multiple VALUES (%s,%s,%s,%s,%s,%s,%s)", (
                    (batch_id, source.market, code, record_day, *fields)
                    for (code, record_day), fields in records.items()
                ))
        else:
            with db.cursor() as cur:
                cur.executemany("INSERT INTO institutional_flow VALUES (%s,%s,%s,%s,%s,%s,%s)", (
                    (batch_id, source.market, code, record_day, *fields)
                    for (code, record_day), fields in records.items()
                ))
        db.execute("INSERT INTO import_attempt (source_id,outcome) VALUES (%s,'updated')", (source.id,))
        return "updated"


def collect(source_id):
    source = SOURCES[source_id]
    with connect() as db:
        register_sources(db)
        allowed = db.execute("SELECT permitted FROM source_registry WHERE id=%s", (source_id,)).fetchone()
    if not source.permitted or not allowed["permitted"]:
        return "blocked"
    try:
        return ingest(source, fetch(source))
    except (ValueError, KeyError, RuntimeError, URLError, TimeoutError) as error:
        with connect() as db:
            db.execute("INSERT INTO import_attempt (source_id,outcome,detail) VALUES (%s,'error',%s)",
                       (source_id, type(error).__name__))
        raise
