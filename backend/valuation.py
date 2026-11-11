"""Eight-year valuation based on the existing TWMI cash-flow conventions."""
from decimal import Decimal

D = Decimal


def project(eps_history, dividends, nav, entry, pe, *, allow_excess_payout=False):
    if len(eps_history) != 8 or len(dividends) != 8 or any(x is None for x in (*eps_history, *dividends, nav, entry, pe)):
        raise ValueError("需填寫八年 EPS、股利、最新 NAV、買進價及本益比")
    if min(nav, entry, pe) <= 0 or any(x < 0 for x in dividends):
        raise ValueError("價格、淨值及倍數須為正數，股利須大於或等於零")
    eps = (sum(eps_history[:7])/7 + eps_history[-1])/2
    if eps <= 0:
        raise ValueError("代表性 EPS 非正數")
    roe = eps/nav
    payout = sum(dividends)/8/eps
    if payout > 1 and not allow_excess_payout:
        raise ValueError("配息率超過 100%，須明確確認此估值假設")
    cf = [-entry]
    for _ in range(8):
        earnings = nav*roe
        dividend = earnings*payout
        nav += earnings-dividend
        if nav <= 0:
            raise ValueError("推估期間淨值耗盡")
        cf.append(dividend)
    terminal = earnings*pe
    cf[-1] += terminal

    def present(rate):
        return sum(amount/(1+rate)**year for year, amount in enumerate(cf[1:],1))

    lo, hi = D("-.9999"), D(1)
    while present(hi) > entry and hi < 1_000_000:
        hi *= 2
    irr = None
    if present(lo) >= entry >= present(hi):
        for _ in range(110):
            mid = (lo+hi)/2
            if present(mid) > entry:
                lo = mid
            else:
                hi = mid
        irr = (lo+hi)/2
    return {"roe_pct": roe*100, "payout_pct": payout*100, "terminal": terminal, "irr_pct": irr*100 if irr is not None else None,
            "present_at_8_pct": present(D(".08")), "present_at_15_pct": present(D(".15")), "cash_flows": cf}


def multiples(db, market, code):
    row = db.execute("""
        SELECT v.pe,v.pb,v.yield_pct,v.day,v.batch_id,b.observed_at,s.url,s.publisher,s.license_url,
               i.industry
        FROM valuation_multiple v JOIN import_batch b ON b.id=v.batch_id
        JOIN source_registry s ON s.id=b.source_id
        JOIN security e ON (e.market,e.code)=(v.market,v.code) AND e.kind='ordinary'
        LEFT JOIN official_membership i ON (i.market,i.code)=(v.market,v.code) AND i.valid_during @> v.day
        WHERE v.market=%s AND v.code=%s
        ORDER BY v.day DESC,b.observed_at DESC,b.id DESC LIMIT 1
    """, (market,code)).fetchone()
    if not row:
        return {}
    company = {**row,"pe":row["pe"] if row["pe"] and row["pe"]>0 else None,"method":"交易所公告個股本益比"}
    sample = db.execute("""
        SELECT avg(v.pe) AS pe,count(v.pe) AS sample_count
        FROM valuation_multiple v JOIN official_membership i
          ON (v.market,v.code)=(i.market,i.code) AND i.valid_during @> v.day
        WHERE v.batch_id=%s AND i.industry=%s AND v.pe>0
    """, (row["batch_id"],row["industry"])).fetchone()
    return {"company":company,"industry":{**row,**sample,"method":"同市場同產業普通股正本益比等權平均"}}
