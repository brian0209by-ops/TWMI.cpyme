from datetime import datetime, timezone
from decimal import Decimal

from .analytics import pct
from .valuation import multiples

CHECKS = (
    ("orders", "訂單"), ("demand", "產業需求"), ("capacity", "產能"),
    ("production", "產量"), ("shipments", "出貨"), ("inventory", "庫存"),
    ("gross_margin", "毛利率"), ("operating_margin", "營業利益率"), ("valuation", "估值"),
)


def expectation(evidence, revenue_yoy=None, activity_pct=None, institutional_net=None, price_change=None):
    by_metric = {}
    for row in evidence:
        by_metric.setdefault(row["metric"], []).append(row)
    checks = []
    for key, label in CHECKS:
        candidates = by_metric.get(key, [])
        eligible = [r for r in candidates if r["nature"] == "actual" and r["direction"] != "unknown"]
        period = max((r["period"] for r in eligible), default=None)
        directions = {r["direction"] for r in eligible if r["period"] == period}
        state = next(iter(directions)) if len(directions) == 1 else "unknown"
        checks.append({"metric": key, "label": label, "state": state, "evidence": candidates})
    supportive = {x["metric"] for x in checks if x["state"] == "supports"}
    opposing = {x["metric"] for x in checks if x["state"] == "opposes"}
    market_strong = all(v is not None and v > 0 for v in (activity_pct, institutional_net, price_change))
    trigger = market_strong and revenue_yoy is not None and revenue_yoy < 0
    verified_growth = bool(supportive & {"orders", "demand"}) and bool(supportive & {"capacity", "production", "shipments"})
    market_weak = all(v is not None and v <= 0 for v in (activity_pct, institutional_net, price_change))
    if trigger and len(opposing & {"orders", "demand", "shipments", "gross_margin", "operating_margin"}) >= 2:
        conclusion = "市場預期與基本面背離"
    elif trigger and verified_growth and not opposing:
        conclusion = "復甦具有基本面支撐"
    elif verified_growth and not opposing and market_weak and "valuation" in supportive:
        conclusion = "基本面改善但市場尚未充分反映"
    elif trigger and (supportive or opposing):
        conclusion = "成長品質仍待確認"
    else:
        conclusion = "證據不足，暫不判斷"
    return {
        "conclusion": conclusion, "trigger": trigger, "checks": checks, "rule_version": "1.4-mvp-1",
        "invalidation": "訂單、需求、出貨或毛利率的新實際揭露與原方向相反，或行情、法人與營收資料被修訂。",
    }


def stock_detail(db, market, code, cutoff=None, end=None):
    cutoff = cutoff or datetime.now(timezone.utc)
    security = db.execute("SELECT * FROM security WHERE market=%s AND code=%s", (market, code)).fetchone()
    if not security:
        return None
    quotes = db.execute("""
        SELECT DISTINCT ON (q.day) q.day,q.close,q.change,q.open,q.high,q.low,q.turnover,q.volume,
               b.id AS batch_id,b.observed_at,s.url,s.publisher,s.license_url
        FROM quote q JOIN import_batch b ON b.id=q.batch_id JOIN source_registry s ON s.id=b.source_id
        WHERE q.market=%s AND q.code=%s AND b.observed_at<=%s AND (%s::date IS NULL OR q.day<=%s)
        ORDER BY q.day DESC,b.observed_at DESC,b.id DESC LIMIT 65
    """, (market, code, cutoff, end, end)).fetchall()
    prior_turnovers = [r["turnover"] for r in quotes[1:6] if r["turnover"] is not None]
    activity = pct(quotes[0]["turnover"], Decimal(sum(prior_turnovers)) / 5) if len(prior_turnovers) == 5 else None
    revenue = db.execute("""
        SELECT DISTINCT ON (r.month) r.*,b.observed_at,s.url,s.publisher,s.license_url
        FROM revenue r JOIN import_batch b ON b.id=r.batch_id JOIN source_registry s ON s.id=b.source_id
        WHERE r.market=%s AND r.code=%s AND b.observed_at<=%s
            AND (%s::date IS NULL OR r.export_day<=%s)
        ORDER BY r.month DESC,b.observed_at DESC,b.id DESC LIMIT 24
    """, (market, code, cutoff, end, end)).fetchall()
    for r in revenue:
        r["yoy_pct"] = pct(r["revenue_thousand"], r["prior_year_thousand"])
        r["mom_pct"] = pct(r["revenue_thousand"], r["prior_month_thousand"])
    flow = db.execute("""
        SELECT f.*,b.observed_at,s.url,s.publisher,s.license_url
        FROM institutional_flow f JOIN import_batch b ON b.id=f.batch_id
        JOIN source_registry s ON s.id=b.source_id
        WHERE f.market=%s AND f.code=%s AND f.day=%s AND b.observed_at<=%s
        ORDER BY b.observed_at DESC,b.id DESC LIMIT 1
    """, (market, code, quotes[0]["day"], cutoff)).fetchone() if quotes else None
    net = None
    if flow and all(flow[k] is not None for k in ("foreign_net", "trust_net", "dealer_net")):
        net = flow["foreign_net"] + flow["trust_net"] + flow["dealer_net"]
    evidence = db.execute("""
        SELECT * FROM operating_evidence WHERE market=%s AND code=%s
            AND observed_at<=%s AND published_at<=%s AND (%s::date IS NULL OR period<=%s)
        ORDER BY published_at DESC,id DESC
    """, (market, code, cutoff, cutoff, end, end)).fetchall()
    scenarios = db.execute("""
        SELECT a.id,a.base_day,a.horizon,a.cutoff,a.body,o.target_day,o.gross_price_return,o.evaluated_at
        FROM research_scenario a LEFT JOIN scenario_outcome o ON a.id=o.scenario_id
        WHERE a.market=%s AND a.code=%s AND a.cutoff<=%s ORDER BY a.cutoff DESC,a.horizon LIMIT 10
    """, (market, code, cutoff)).fetchall()
    group = db.execute("""
        SELECT industry FROM official_membership WHERE market=%s AND code=%s
            AND valid_during @> %s::date
    """, (market, code, end or (quotes[0]["day"] if quotes else cutoff.date()))).fetchone()
    current_month = revenue[0]["month"] if revenue else None
    months = [r["month"].year * 12 + r["month"].month for r in revenue[:3]]
    revenue_3m = None
    if len(months) == 3 and months == list(range(months[0], months[0]-3, -1)) and all(
        r[k] is not None for r in revenue[:3] for k in ("revenue_thousand", "prior_year_thousand")
    ):
        revenue_3m = pct(sum(r["revenue_thousand"] for r in revenue[:3]), sum(r["prior_year_thousand"] for r in revenue[:3]))
    averages = {}
    for n in (5,20,60):
        prices = [q["close"] for q in quotes[:n] if q["close"] is not None]
        averages[str(n)] = sum(prices) / n if len(prices) == n else None
    return {**security, "industry": group["industry"] if group else None, "quotes": quotes, "flow": flow,
            "revenue": revenue, "revenue_month": current_month, "revenue_3m_yoy_pct": revenue_3m,
            "activity_pct": activity, "moving_averages": averages, "multiples": multiples(db,market,code), "evidence": evidence, "scenarios": scenarios,
            "expectation": expectation(evidence, revenue[0]["yoy_pct"] if revenue else None, activity, net,
                                       quotes[0]["change"] if quotes else None) if security["kind"] == "ordinary" else None}
