from decimal import Decimal

ZERO = Decimal(0)


def replay(trades):
    quantity, cost, realized = 0, ZERO, ZERO
    for trade in sorted(trades, key=lambda r: (r["traded_on"], r["id"])):
        units = trade["quantity"]
        amount = trade["price"] * units
        if trade["side"] == "buy":
            quantity += units
            cost += amount + trade["fees"]
        else:
            if units > quantity:
                raise ValueError("賣出股數超過當時持股")
            allocated_cost = cost if units == quantity else cost * units / quantity
            realized += amount - trade["fees"] - allocated_cost
            cost -= allocated_cost
            quantity -= units
    return quantity, cost, realized


def trade_rows(db, market, code):
    return db.execute("""
        SELECT * FROM portfolio_trade WHERE market=%s AND code=%s ORDER BY traded_on,id
    """, (market, code)).fetchall()


def portfolio(db):
    codes = db.execute("""
        SELECT s.*, EXISTS(SELECT 1 FROM watchlist w WHERE (w.market,w.code)=(s.market,s.code)) AS watched
        FROM security s
        WHERE (s.market,s.code) IN (SELECT market,code FROM portfolio_trade UNION SELECT market,code FROM watchlist)
        ORDER BY s.market,s.code
    """).fetchall()
    positions = []
    for security in codes:
        args = (security["market"], security["code"])
        trades = trade_rows(db, *args)
        quantity, cost, realized = replay(trades)
        mark = db.execute("""
            SELECT q.close,q.day,b.observed_at,s.url,s.publisher,s.license_url
            FROM quote q JOIN import_batch b ON q.batch_id=b.id JOIN source_registry s ON b.source_id=s.id
            WHERE q.market=%s AND q.code=%s
            ORDER BY q.day DESC,b.observed_at DESC,b.id DESC LIMIT 1
        """, args).fetchone()
        value = mark["close"] * quantity if mark and mark["close"] is not None else None
        positions.append({**security, "quantity": quantity, "average_cost": cost/quantity if quantity else None,
                          "realized": realized, "unrealized": value-cost if value is not None else None,
                          "market_value": value, "mark": mark, "trades": trades})
    open_positions = [p for p in positions if p["quantity"]]
    dates = {p["mark"]["day"] for p in open_positions if p["mark"]}
    total = sum(p["market_value"] for p in open_positions) if len(dates)==1 and all(p["market_value"] is not None for p in open_positions) else None
    for position in positions:
        position["allocation_pct"] = position["market_value"] / total * 100 if total and position["market_value"] is not None else None
    return {"positions": positions, "total_market_value": total, "valuation_day": next(iter(dates)) if total is not None else None}
