from datetime import datetime, timedelta, timezone
from decimal import Decimal

MARKETS = ("TWSE", "TPEX")
INDUSTRIES = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業",
    "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造",
    "15": "航運業", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨",
    "20": "其他", "21": "化學工業", "22": "生技醫療", "23": "油電燃氣",
    "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
    "32": "文化創意業", "33": "農業科技業", "34": "電子商務", "35": "綠能環保",
    "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
}


def latest_batches(db, kind, markets, cutoff, before=None):
    return db.execute("""
        SELECT DISTINCT ON (s.market,b.market_day)
            s.market,b.id,b.market_day,b.observed_at,s.url,s.name,s.publisher,s.license_url
        FROM import_batch b JOIN source_registry s ON s.id=b.source_id
        WHERE s.kind=%s AND s.market=ANY(%s) AND b.observed_at <= %s
          AND (%s::date IS NULL OR b.market_day <= %s)
        ORDER BY s.market,b.market_day DESC,b.observed_at DESC,b.id DESC
    """, (kind, list(markets), cutoff, before, before)).fetchall()


def status(db):
    return db.execute("""
        SELECT s.id,s.market,s.kind,s.name,s.publisher,s.url,s.documentation,s.license_url,
               s.checked_on,s.limits,s.permitted,b.market_day,b.observed_at,
               b.row_count,a.outcome,a.attempted_at
        FROM source_registry s
        LEFT JOIN LATERAL (
            SELECT market_day,observed_at,row_count FROM import_batch
            WHERE source_id=s.id ORDER BY market_day DESC, observed_at DESC LIMIT 1
        ) b ON true
        LEFT JOIN LATERAL (
            SELECT outcome,attempted_at FROM import_attempt
            WHERE source_id=s.id ORDER BY attempted_at DESC,id DESC LIMIT 1
        ) a ON true
        ORDER BY s.market,s.kind
    """).fetchall()


def quote_groups(db, batches, day, cutoff, classification):
    if not batches:
        return []
    if classification == "official":
        return db.execute("""
            SELECT o.market,o.industry AS group_id,s.code,s.name,s.kind,q.close,q.change,q.turnover
            FROM official_membership o
            JOIN security s ON (s.market,s.code)=(o.market,o.code)
            JOIN import_batch m ON m.id=o.batch_id AND m.observed_at<=%s
            LEFT JOIN quote q ON q.market=s.market AND q.code=s.code AND q.batch_id=ANY(%s)
            WHERE o.market=ANY(%s) AND o.valid_during @> %s::date AND s.kind='ordinary'
        """, (cutoff, [b["id"] for b in batches], [b["market"] for b in batches], day)).fetchall()
    return db.execute("""
        SELECT s.market,t.theme_slug AS group_id,s.code,s.name,s.kind,q.close,q.change,q.turnover,
               t.role,t.evidence_url,t.confidence,lower(t.valid_during) AS valid_from,upper(t.valid_during) AS valid_to
        FROM theme_membership t
        JOIN security s ON (s.market,s.code)=(t.market,t.code)
        LEFT JOIN quote q ON q.market=s.market AND q.code=s.code AND q.batch_id=ANY(%s)
        WHERE s.market=ANY(%s) AND t.valid_during @> %s::date AND s.kind='ordinary' AND t.observed_at<=%s
    """, ([b["id"] for b in batches], [b["market"] for b in batches], day, cutoff)).fetchall()


def revenue_rows(db, cutoff, day, markets):
    return db.execute("""
        SELECT DISTINCT ON (r.market,r.code) r.*,b.observed_at,s.url,s.publisher,s.license_url
        FROM revenue r JOIN import_batch b ON b.id=r.batch_id JOIN source_registry s ON s.id=b.source_id
        WHERE r.market=ANY(%s) AND r.export_day<=%s AND b.observed_at<=%s
        ORDER BY r.market,r.code,r.month DESC,b.observed_at DESC,b.id DESC
    """, (list(markets), day, cutoff)).fetchall()


def pct(current, prior):
    if current is None or prior is None or prior <= 0:
        return None
    return (Decimal(current) / Decimal(prior) - 1) * 100


def summarize(rows):
    measured = [row for row in rows if row["turnover"] is not None]
    returns = [row["change"] / (row["close"] - row["change"]) for row in rows
               if row["change"] is not None and row["close"] is not None and row["close"] > row["change"]]
    return {
        "turnover": sum(row["turnover"] for row in measured) if measured else None,
        "coverage_count": len(measured),
        "members_count": len(rows),
        "breadth_pct": (Decimal(sum(value > 0 for value in returns)) / len(returns) * 100) if returns else None,
        "breadth_count": len(returns),
        "return_pct": sum(returns) / len(returns) * 100 if returns else None,
    }


def _key(row, classification):
    return f"{row['market']}:{row['group_id']}" if classification == "official" else row["group_id"]


def _group(rows, classification):
    grouped = {}
    for row in rows:
        grouped.setdefault(_key(row, classification), []).append(row)
    return grouped


def _revenue(rows, mapped):
    available = [mapped[(r["market"], r["code"])] for r in rows if (r["market"], r["code"]) in mapped]
    months = {r["month"] for r in available}
    if len(months) != 1:
        return {"month": None, "yoy_pct": None, "count": 0}
    valid = [r for r in available if r["revenue_thousand"] is not None and r["prior_year_thousand"] is not None]
    growth = [pct(r["revenue_thousand"],r["prior_year_thousand"]) for r in valid]
    return {
        "month": next(iter(months)),
        "yoy_pct": pct(sum(r["revenue_thousand"] for r in valid), sum(r["prior_year_thousand"] for r in valid)) if valid else None,
        "count": len(valid),
        "growing": sum(value is not None and value>0 for value in growth),
        "unchanged": sum(value==0 for value in growth),
        "declining": sum(value is not None and value<0 for value in growth),
        "sources": [{"url": url, "publisher": publisher, "license_url": license_url}
                    for url, publisher, license_url in sorted({(r["url"], r["publisher"], r["license_url"]) for r in valid})],
        "observed_at": max((r["observed_at"] for r in valid), default=None),
    }


def _flow(db, markets, day, cutoff):
    batches = [b for b in latest_batches(db, "flow", markets, cutoff, day) if b["market_day"] == day]
    rows = db.execute("SELECT * FROM institutional_flow WHERE batch_id=ANY(%s)",
                      ([b["id"] for b in batches],)).fetchall() if batches else []
    return {(r["market"], r["code"]): r for r in rows}, batches


def _flow_summary(rows, flows):
    vals = [flows[(r["market"], r["code"])] for r in rows if (r["market"], r["code"]) in flows]
    summary = {"count": len(vals)}
    for key in ("foreign_net", "trust_net", "dealer_net"):
        eligible = [r[key] for r in vals if r[key] is not None]
        summary[key] = sum(eligible) if eligible else None
        summary[f"{key}_count"] = len(eligible)
    return summary


def verified_history_days(db, markets, day, period):
    start = day - timedelta(days=period*4+14)
    sessions = db.execute("""
        SELECT day,bool_or(is_open) AS trading,count(*) AS confirmed
        FROM market_calendar WHERE day>=%s AND day<%s AND market=ANY(%s)
        GROUP BY day ORDER BY day DESC
    """, (start,day,list(markets))).fetchall()
    result, expected = [], day-timedelta(days=1)
    for row in sessions:
        if row["day"]!=expected or row["confirmed"]!=len(markets):
            return []
        if row["trading"]:
            result.append(expected)
        if len(result)==period:
            return result
        expected -= timedelta(days=1)
    return []


def full_summary(rows, markets):
    summary = summarize(rows)
    if len({row["market"] for row in rows}) != len(markets) or summary["members_count"] != summary["coverage_count"]:
        return None
    return summary


def compounded(values):
    result = Decimal(1)
    for value in values:
        result *= 1 + value/100
    return (result-1)*100


def radar(db, market="ALL", classification="official", day=None, period=5, cutoff=None, group=None, history=True):
    cutoff = cutoff or datetime.now(timezone.utc)
    markets = MARKETS if market == "ALL" else (market,)
    batches = latest_batches(db, "quotes", markets, cutoff, day)
    if not batches:
        return {"day": None, "market": market, "classification": classification, "rows": [],
                "sources": [], "flow_sources": [], "market_complete": False, "market_turnover": None}
    day = day or max(b["market_day"] for b in batches)
    current = [b for b in batches if b["market_day"] == day]
    official = quote_groups(db, current, day, cutoff, "official")
    market_summary = summarize(official)
    complete = len(current) == len(markets) and len({row["market"] for row in official}) == len(markets) and (
        market_summary["members_count"] > 0 and market_summary["coverage_count"] == market_summary["members_count"]
    )
    denom = market_summary["turnover"] if complete else None
    grouped = _group(official if classification == "official" else quote_groups(db, current, day, cutoff, "theme"), classification)
    names = {r["slug"]: r["name"] for r in db.execute("SELECT * FROM theme")}
    revenue = {(r["market"], r["code"]): r for r in revenue_rows(db, cutoff, day, markets)}
    flows, flow_sources = _flow(db, markets, day, cutoff)
    historic = {}
    if history:
        past_days = verified_history_days(db, markets, day, period)
        for past in past_days:
            past_batches = [b for b in batches if b["market_day"] == past]
            historical = quote_groups(db, past_batches, past, cutoff, classification)
            baseline = full_summary(quote_groups(db, past_batches, past, cutoff, "official"), markets)
            historic[past] = ({key: summarize(rows) for key, rows in _group(historical, classification).items()}, baseline)
    result = []
    for key, members in grouped.items():
        if group and key != group:
            continue
        stats = summarize(members)
        past = [v[0].get(key) for v in historic.values()]
        usable = [v for v in past if v and v["turnover"] is not None and v["coverage_count"] == v["members_count"]]
        turnover = stats["turnover"]
        activity = pct(turnover, sum(Decimal(v["turnover"]) for v in usable) / period) if len(usable) == period and stats["coverage_count"] == stats["members_count"] else None
        industry = members[0]["group_id"]
        relative = None
        if complete and stats["return_pct"] is not None and market_summary["return_pct"] is not None:
            relative = stats["return_pct"] - market_summary["return_pct"]
        relative_period = None
        if complete and len(historic)==period and stats["return_pct"] is not None and market_summary["return_pct"] is not None:
            relevant = [stats, *past[:period-1]]
            benchmarks = [market_summary, *(value[1] for value in list(historic.values())[:period-1])]
            if all(x and x["return_pct"] is not None and x["breadth_count"]==x["members_count"] for x in [*relevant,*benchmarks]):
                relative_period = compounded(x["return_pct"] for x in relevant) - compounded(x["return_pct"] for x in benchmarks)
        evidence = []
        if group:
            evidence = db.execute("""
                SELECT e.id,e.market,e.code,e.metric,e.nature,e.direction,e.period,e.published_at,
                       e.value,e.unit,e.product,e.evidence_url,e.note
                FROM operating_evidence e
                JOIN unnest(%s::text[],%s::text[]) AS m(market,code)
                    ON (e.market,e.code)=(m.market,m.code)
                WHERE e.observed_at<=%s AND e.published_at<=%s AND e.period<=%s
                ORDER BY e.published_at DESC,e.id DESC LIMIT 50
            """, ([r["market"] for r in members],[r["code"] for r in members],cutoff,cutoff,day)).fetchall()
        result.append({
            "id": key, "label": INDUSTRIES.get(industry, f"產業代碼 {industry}") if classification == "official" else names[industry],
            "market": members[0]["market"] if classification == "official" else market,
            **stats, "share_pct": Decimal(turnover) / denom * 100 if denom and turnover is not None and stats["coverage_count"] == stats["members_count"] else None,
            "activity_pct": activity, "relative_day_pp": relative, "relative_period_pp": relative_period, "revenue": _revenue(members, revenue),
            "flow": _flow_summary(members, flows),
            **({"members": members, "evidence": evidence} if group else {}),
        })
    result.sort(key=lambda row: (row["turnover"] is None, -(row["turnover"] or 0), row["id"]))
    return {"day": day, "market": market, "classification": classification, "period": period, "rows": result,
            "market_complete": complete, "market_turnover": denom, "market_coverage": market_summary,
            "sources": current, "flow_sources": flow_sources,
            "history_days": list(historic)}
