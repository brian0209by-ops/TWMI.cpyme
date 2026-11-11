from datetime import datetime, timedelta, timezone
from decimal import Decimal

from psycopg.types.json import Jsonb

from .analytics import MARKETS, radar
from .collectors import TAIPEI
from .research import stock_detail


def serializable(value):
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def market_sessions(db, day):
    return {row["market"]: row["is_open"] for row in db.execute(
        "SELECT market,is_open FROM market_calendar WHERE day=%s", (day,)
    )}


def write_report(db, day, slot, cutoff=None):
    cutoff = cutoff or datetime.now(timezone.utc)
    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{day}/{slot}",))
    if db.execute("SELECT 1 FROM research_report WHERE day=%s AND slot=%s", (day, slot)).fetchone():
        return "unchanged"
    sessions = market_sessions(db, day)
    if not any(sessions.values()):
        return "closed" if all(sessions.get(m) is False for m in MARKETS) else "calendar_pending"
    end = day - timedelta(days=1) if slot == "12:00" else day
    markets = []
    for market in MARKETS:
        if sessions.get(market) is not True:
            markets.append({"market":market,"status":"closed" if sessions.get(market) is False else "calendar_pending"})
            continue
        result = radar(db, market, cutoff=cutoff, history=False)
        if result["day"] and result["day"] > end:
            rows = db.execute("""
                SELECT max(b.market_day) AS day FROM import_batch b JOIN source_registry s ON s.id=b.source_id
                WHERE s.kind='quotes' AND s.market=%s AND b.market_day<=%s AND b.observed_at<=%s
            """, (market,end,cutoff)).fetchone()
            result = radar(db, market, day=rows["day"], cutoff=cutoff, history=False) if rows["day"] else {
                "day":None,"rows":[],"market_complete":False,"sources":[],"flow_sources":[]
            }
        market_status = "last_close" if slot == "12:00" else ("complete" if result["day"] == day and result["market_complete"] else "pending")
        markets.append({"market":market,"status":market_status,"data_day":result["day"],
                        "leaders":result["rows"][:5],"quotes_sources":result["sources"],"flow_sources":result["flow_sources"],
                        "flow_status":"available" if result["flow_sources"] and result["day"]==day else "pending"})
    scenario_count = 0
    if slot == "18:00":
        for watch in db.execute("""
            SELECT market,code FROM watchlist
            UNION
            SELECT market,code FROM portfolio_trade WHERE traded_on<=%s GROUP BY market,code
            HAVING sum(CASE WHEN side='buy' THEN quantity ELSE -quantity END)>0
        """,(day,)):
            if sessions.get(watch["market"]) is not True:
                continue
            stock = stock_detail(db, **watch, cutoff=cutoff, end=day)
            if not stock or stock["kind"] != "ordinary" or not stock["quotes"] or stock["quotes"][0]["day"] != day or stock["quotes"][0]["close"] is None:
                continue
            analysis = stock["expectation"]
            for horizon in (5,20):
                body = {
                    "rule_version":analysis["rule_version"], "conclusion":analysis["conclusion"],
                    "bull":"後續訂單、需求及出貨改善，且營收或利潤率出現相符改善。",
                    "base":"營運證據仍待補齊，持續觀察成交活躍度、營收與法人籌碼。",
                    "bear":"需求、出貨或利潤率轉弱，股價表現與營運證據失去支撐。",
                    "invalidation":analysis["invalidation"], "checks":analysis["checks"],
                    "quote_batch_id":stock["quotes"][0]["batch_id"],
                    "revenue_batch_id":stock["revenue"][0]["batch_id"] if stock["revenue"] else None,
                    "flow_batch_id":stock["flow"]["batch_id"] if stock["flow"] else None,
                }
                scenario_count += db.execute("""
                    INSERT INTO research_scenario (market,code,base_day,cutoff,horizon,base_price,body)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """, (stock["market"],stock["code"],day,cutoff,horizon,stock["quotes"][0]["close"],
                      Jsonb(serializable(body)))).rowcount
    status = "complete" if all(row["status"] in ("complete","closed") for row in markets) else "partial"
    db.execute("""
        INSERT INTO research_report (day,slot,cutoff,status,body) VALUES (%s,%s,%s,%s,%s)
    """, (day,slot,cutoff,status,Jsonb(serializable({"markets":markets,"scenarios_created":scenario_count}))))
    return status


def evaluate(db, cutoff=None):
    cutoff = cutoff or datetime.now(timezone.utc)
    count = 0
    for scenario in db.execute("""
        SELECT a.* FROM research_scenario a
        WHERE a.cutoff<=%s AND NOT EXISTS (SELECT 1 FROM scenario_outcome o WHERE o.scenario_id=a.id)
    """, (cutoff,)).fetchall():
        base = scenario["base_day"]
        days = db.execute("""
            SELECT day,is_open FROM market_calendar
            WHERE market=%s AND day>%s AND day<=%s ORDER BY day
        """, (scenario["market"],base,cutoff.astimezone(TAIPEI).date())).fetchall()
        expected, open_days = base + timedelta(days=1), []
        for entry in days:
            if entry["day"] != expected:
                break
            if entry["is_open"]:
                open_days.append(entry["day"])
            if len(open_days) == scenario["horizon"]:
                target = open_days[-1]
                price = db.execute("""
                    SELECT q.close,q.batch_id FROM quote q JOIN import_batch b ON b.id=q.batch_id
                    WHERE q.market=%s AND q.code=%s AND q.day=%s AND b.observed_at<=%s
                    ORDER BY b.observed_at DESC,b.id DESC LIMIT 1
                """, (scenario["market"],scenario["code"],target,cutoff)).fetchone()
                if price and price["close"] is not None:
                    value = (price["close"]/scenario["base_price"] - Decimal(1))*100
                    count += db.execute("""
                        INSERT INTO scenario_outcome (scenario_id,target_day,close,quote_batch_id,gross_price_return)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                    """, (scenario["id"],target,price["close"],price["batch_id"],value)).rowcount
                break
            expected += timedelta(days=1)
    return count
