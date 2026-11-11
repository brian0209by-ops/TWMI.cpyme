import json
import os
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.errors import ExclusionViolation, RaiseException

from backend.collectors import ingest
from backend.db import connect, migrate
from backend.main import app
from backend.reports import evaluate, write_report
from backend.sources import SOURCES, register_sources
from test_market import quote


@pytest.fixture
def database(monkeypatch):
    dsn = os.environ.get("TWMI_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set TWMI_TEST_DATABASE_URL to an isolated PostgreSQL service")
    name = "twmi_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    options = conninfo_to_dict(dsn)
    options["dbname"] = name
    monkeypatch.setenv("DATABASE_URL", make_conninfo(**options))
    try:
        migrate()
        migrate()
        with connect() as db:
            register_sources(db)
        yield TestClient(app)
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def source(id):
    return replace(SOURCES[id],minimum=1)


def raw(*rows):
    return json.dumps(rows,ensure_ascii=False).encode()


def test_market_ingestion_classification_radar_and_trades(database):
    master = raw({"公司代號":"2330","出表日期":"1151001","公司簡稱":"合成公司","產業別":"24"})
    assert ingest(source("twse-master"),master)=="updated"
    assert ingest(source("twse-master"),master)=="unchanged"
    payload = raw(quote(),quote("0050"))
    assert ingest(source("twse-quotes"),payload)=="updated"
    assert ingest(source("twse-quotes"),payload)=="unchanged"
    with pytest.raises(ValueError):
        ingest(source("twse-flow"),raw({}))
    twse = database.get("/radar?market=TWSE&period=5").json()
    assert twse["market_complete"] and len(twse["rows"])==1
    assert twse["rows"][0]["members_count"]==1
    assert twse["rows"][0]["turnover"]==100000
    assert float(twse["rows"][0]["share_pct"])==100
    assert twse["rows"][0]["relative_period_pp"] is None
    detail = database.get("/radar?market=TWSE&group=TWSE%3A24").json()["rows"][0]
    assert detail["members"][0]["code"] == "2330"
    assert detail["evidence"] == []
    combined = database.get("/radar").json()
    assert not combined["market_complete"] and combined["market_turnover"] is None
    assert database.get("/stocks/TWSE/0050").json()["kind"]=="etf"
    theme = dict(market="TWSE",code="2330",theme="ai",start="2026-10-01",
                 role="合成測試角色",confidence="high",evidence_url="https://example.com/")
    assert database.post("/themes/members",json=theme).status_code==201
    assert database.post("/themes/members",json=theme).status_code==409
    assert database.post("/themes/members",json={**theme,"theme":"semiconductor"}).status_code==201
    assert len(database.get("/radar?market=TWSE&classification=theme").json()["rows"])==2
    with pytest.raises(ExclusionViolation), connect() as db:
        batch = db.execute("SELECT id FROM import_batch WHERE source_id='twse-master'").fetchone()["id"]
        db.execute("INSERT INTO official_membership (market,code,industry,valid_during,batch_id) VALUES ('TWSE','2330','25','[2026-10-02,)',%s)",(batch,))
    trade = dict(market="TWSE",code="2330",traded_on="2026-10-01",side="buy",quantity=10,price="100",fees="5")
    buy = database.post("/portfolio/trades",json=trade)
    assert buy.status_code==201
    assert database.post("/portfolio/trades",json={**trade,"side":"sell","quantity":11}).status_code==409
    sale = database.post("/portfolio/trades",json={**trade,"side":"sell","quantity":4,"price":"110"})
    assert sale.status_code==201
    position = database.get("/portfolio").json()["positions"][0]
    assert position["quantity"]==6 and float(position["realized"])==33
    assert database.delete(f"/portfolio/trades/{buy.json()['id']}").status_code==409


def test_reports_and_outcomes_preserve_as_of_evidence(database):
    day = date(2026,10,1)
    later = day+timedelta(days=5)
    assert ingest(source("twse-master"),raw({"公司代號":"2330","出表日期":"1151001","公司簡稱":"合成公司","產業別":"24"}))=="updated"
    assert ingest(source("twse-quotes"),raw(quote()))=="updated"
    now = datetime.now(timezone.utc)
    with connect() as db:
        for offset in range(6):
            db.execute("INSERT INTO market_calendar VALUES ('TWSE',%s,true,'https://www.twse.com.tw/')",(day+timedelta(days=offset),))
            db.execute("INSERT INTO market_calendar VALUES ('TPEX',%s,false,'https://www.tpex.org.tw/')",(day+timedelta(days=offset),))
        assert write_report(db,day+timedelta(days=12),"12:00",now)=="calendar_pending"
        assert write_report(db,day,"12:00",now)=="partial"
        noon = db.execute("SELECT body FROM research_report WHERE slot='12:00'").fetchone()["body"]
        assert noon["markets"][0]["data_day"] is None
    assert database.post("/watchlist",json={"market":"TWSE","code":"2330"}).status_code==201
    with connect() as db:
        assert write_report(db,day,"18:00",now)=="complete"
        assert write_report(db,day,"18:00",now)=="unchanged"
        assert evaluate(db,now)==0
        assert db.execute("SELECT count(*) AS n FROM research_scenario").fetchone()["n"]==2
    with pytest.raises(RaiseException), connect() as db:
        db.execute("DELETE FROM research_scenario")
    assert ingest(source("twse-quotes"),raw(quote(day="1151006")) )=="updated"
    with connect() as db:
        assert evaluate(db,now)==0
        assert evaluate(db,datetime.now(timezone.utc))==1
        assert evaluate(db,datetime.now(timezone.utc))==0
        assert db.execute("SELECT target_day FROM scenario_outcome").fetchone()["target_day"]==later
