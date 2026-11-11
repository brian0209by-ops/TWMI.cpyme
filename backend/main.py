from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field, HttpUrl
from psycopg.errors import ExclusionViolation, ForeignKeyViolation

from .analytics import radar, status
from .collectors import TAIPEI
from .db import connect
from .portfolio import portfolio, replay, trade_rows
from .research import stock_detail
from .valuation import multiples, project

app = FastAPI(title="TWMI Signals", version="1.4.0", docs_url=None, redoc_url=None, openapi_url=None)
Market = Literal["TWSE", "TPEX"]
Code = Annotated[str, Field(pattern=r"^[A-Z0-9]{2,12}$")]
Price = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]
Fee = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
Metric = Literal["orders","demand","capacity","production","shipments","inventory","gross_margin",
                 "operating_margin","eps","roe","valuation","etf_exposure","etf_concentration","etf_tracking"]


class Instrument(BaseModel):
    market: Market
    code: Code


class Trade(Instrument):
    side: Literal["buy","sell"]
    traded_on: date
    quantity: Annotated[int, Field(gt=0, le=10**9)]
    price: Price
    fees: Fee = Decimal(0)


class Evidence(Instrument):
    metric: Metric
    nature: Literal["actual","guidance","estimate","inference"]
    direction: Literal["supports","opposes","neutral","unknown"]
    period: date
    published_at: datetime
    value: Annotated[Decimal, Field(max_digits=24, decimal_places=6)] | None = None
    unit: Annotated[str, Field(min_length=1,max_length=40)] | None = None
    product: Annotated[str, Field(max_length=120)] | None = None
    evidence_url: HttpUrl
    note: Annotated[str, Field(min_length=1,max_length=1500)]


class ThemeMembership(Instrument):
    theme: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
    start: date
    end: date | None = None
    role: Annotated[str, Field(min_length=1,max_length=100)]
    evidence_url: HttpUrl
    confidence: Literal["high","medium","low"]


class Valuation(Instrument):
    eps_history: Annotated[list[Annotated[Decimal,Field(max_digits=18,decimal_places=6)]],Field(min_length=8,max_length=8)]
    dividends: Annotated[list[Fee],Field(min_length=8,max_length=8)]
    nav: Price
    entry: Price
    benchmark: Literal["industry","company"]
    financial_source: HttpUrl
    allow_excess_payout: bool = False


def lock_instrument(db, instrument):
    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"trade:{instrument.market}:{instrument.code}",))
    row = db.execute("SELECT kind FROM security WHERE market=%s AND code=%s",(instrument.market,instrument.code)).fetchone()
    if not row:
        raise HTTPException(404,"找不到證券")
    return row["kind"]


@app.get("/health")
def health():
    with connect() as db:
        db.execute("SELECT 1 FROM schema_migration LIMIT 1")
    return {"status":"ok"}


@app.get("/sources")
def sources():
    with connect() as db:
        return status(db)


@app.get("/radar")
def get_radar(market: Literal["ALL","TWSE","TPEX"]="ALL",
              classification: Literal["official","theme"]="official",
              day: date | None=None, period: int=5, group: str | None=Query(None,max_length=50)):
    with connect() as db:
        if period not in (5,20):
            raise HTTPException(422,"期間須為 5 或 20 個交易日")
        return radar(db,market,classification,day,period,group=group)


@app.get("/themes")
def themes():
    with connect() as db:
        return db.execute("SELECT * FROM theme ORDER BY slug").fetchall()


@app.post("/themes/members",status_code=201)
def add_theme(entry: ThemeMembership):
    if entry.evidence_url.scheme!="https" or (entry.end and entry.end<=entry.start):
        raise HTTPException(422,"需有 HTTPS 來源與有效日期")
    try:
        with connect() as db:
            if lock_instrument(db,entry)!="ordinary":
                raise HTTPException(422,"主題成分只接受普通股")
            db.execute("""
                INSERT INTO theme_membership (market,code,theme_slug,valid_during,role,evidence_url,confidence)
                VALUES (%s,%s,%s,daterange(%s,%s),%s,%s,%s)
            """,(entry.market,entry.code,entry.theme,entry.start,entry.end,entry.role,str(entry.evidence_url),entry.confidence))
    except (ExclusionViolation,ForeignKeyViolation):
        raise HTTPException(409,"主題不存在或關聯日期重疊")
    return {"status":"created"}


@app.get("/securities")
def securities(q: str=Query("",max_length=32)):
    with connect() as db:
        return db.execute("""
            SELECT * FROM security WHERE strpos(lower(code),lower(%s))>0 OR strpos(name,%s)>0 OR %s=''
            ORDER BY code=%s DESC, market,code LIMIT 30
        """,(q,q,q,q)).fetchall()


@app.get("/stocks/{market}/{code}")
def stock(market: Market, code: Annotated[str,Path(pattern=r"^[A-Z0-9]{2,12}$")]):
    with connect() as db:
        result=stock_detail(db,market,code)
    if not result:
        raise HTTPException(404,"找不到證券")
    return result


@app.post("/evidence",status_code=201)
def add_evidence(entry: Evidence):
    if entry.evidence_url.scheme!="https" or (entry.value is None)!=(entry.unit is None):
        raise HTTPException(422,"需有 HTTPS 來源，數值與單位需一併提供")
    if entry.published_at.utcoffset() is None or entry.published_at>datetime.now(timezone.utc):
        raise HTTPException(422,"發布時間須包含時區且不得晚於現在")
    with connect() as db:
        kind=lock_instrument(db,entry)
        if (kind=="etf") != entry.metric.startswith("etf_"):
            raise HTTPException(422,"證據類型與證券種類不符")
        return db.execute("""
            INSERT INTO operating_evidence (market,code,metric,nature,direction,period,published_at,value,unit,product,evidence_url,note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """,(entry.market,entry.code,entry.metric,entry.nature,entry.direction,entry.period,entry.published_at,
             entry.value,entry.unit,entry.product,str(entry.evidence_url),entry.note)).fetchone()


@app.post("/valuation")
def valuation(entry: Valuation):
    if entry.financial_source.scheme != "https":
        raise HTTPException(422,"需提供 HTTPS 財務資料來源")
    with connect() as db:
        benchmarks = multiples(db,entry.market,entry.code)
    benchmark = benchmarks.get(entry.benchmark)
    if not benchmark or benchmark["pe"] is None:
        raise HTTPException(422,"尚無可用的正本益比資料")
    try:
        result=project(entry.eps_history,entry.dividends,entry.nav,entry.entry,benchmark["pe"],
                       allow_excess_payout=entry.allow_excess_payout)
    except ValueError as error:
        raise HTTPException(422,str(error))
    return {**result,"benchmark":benchmark,"financial_source":str(entry.financial_source)}



@app.get("/portfolio")
def positions():
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return portfolio(db)


@app.post("/watchlist",status_code=201)
def watch(entry: Instrument):
    with connect() as db:
        lock_instrument(db,entry)
        db.execute("INSERT INTO watchlist VALUES (%s,%s) ON CONFLICT DO NOTHING",(entry.market,entry.code))
    return {"status":"saved"}


@app.delete("/watchlist/{market}/{code}")
def unwatch(market: Market,code: Code):
    with connect() as db:
        db.execute("DELETE FROM watchlist WHERE market=%s AND code=%s",(market,code))
    return {"status":"removed"}


@app.post("/portfolio/trades",status_code=201)
def add_trade(entry: Trade):
    if entry.traded_on>datetime.now(TAIPEI).date():
        raise HTTPException(422,"交易日期不得晚於今日")
    with connect() as db:
        lock_instrument(db,entry)
        row=db.execute("""
            INSERT INTO portfolio_trade (market,code,traded_on,side,quantity,price,fees)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """,(entry.market,entry.code,entry.traded_on,entry.side,entry.quantity,entry.price,entry.fees)).fetchone()
        try:
            replay(trade_rows(db,entry.market,entry.code))
        except ValueError as error:
            raise HTTPException(409,str(error))
        return row


@app.delete("/portfolio/trades/{id}")
def remove_trade(id: int):
    with connect() as db:
        row=db.execute("SELECT market,code FROM portfolio_trade WHERE id=%s",(id,)).fetchone()
        if not row:
            raise HTTPException(404,"找不到交易")
        lock_instrument(db,Instrument(**row))
        db.execute("DELETE FROM portfolio_trade WHERE id=%s",(id,))
        try:
            replay(trade_rows(db,row["market"],row["code"]))
        except ValueError as error:
            raise HTTPException(409,str(error))
    return {"status":"removed"}


@app.get("/reports")
def reports():
    with connect() as db:
        return db.execute("SELECT * FROM research_report ORDER BY day DESC,slot DESC LIMIT 30").fetchall()
