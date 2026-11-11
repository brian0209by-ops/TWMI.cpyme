from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from backend.analytics import compounded, pct, summarize
from backend.collectors import normalize, numeric, parse_date
from backend.research import expectation
from backend.sources import SOURCES
from backend.valuation import project


def test_roc_dates_and_missing_values():
    assert parse_date("115/11/10") == date(2026,11,10)
    assert parse_date("11510", month=True) == date(2026,10,1)
    assert numeric("X0.00") is None
    assert numeric("0", integral=True) == 0
    assert numeric("1,002", integral=True) == 1002
    with pytest.raises(ValueError):
        numeric("NaN")
    with pytest.raises(ValueError):
        numeric("1.7", integral=True)


def quote(code="2330", day="1151001"):
    return dict(Code=code,Date=day,Name="合成測試",
                OpeningPrice="100",HighestPrice="110",LowestPrice="90",ClosingPrice="105",
                TradeVolume="1000",TradeValue="100000",Change="+5")


def test_reject_duplicate_mixed_dates_and_partial_payload():
    source = replace(SOURCES["twse-quotes"],minimum=1)
    with pytest.raises(ValueError,match="duplicate"):
        normalize(source,[quote(),quote()])
    with pytest.raises(ValueError,match="date"):
        normalize(source,[quote(),quote("2308","1151002")])
    with pytest.raises(ValueError,match="threshold"):
        normalize(replace(source,minimum=2),[quote()])


def test_coverage_is_explicit():
    summary = summarize([
        {"turnover":100,"close":D(105),"change":D(5)},
        {"turnover":None,"close":None,"change":None},
        {"turnover":0,"close":D(100),"change":D(0)},
    ])
    assert summary["coverage_count"] == 2
    assert summary["breadth_pct"] == 50
    assert summary["return_pct"] == D("2.5")
    assert pct(0,10) == -100 and pct(1,0) is None
    assert compounded([D(10),D(-10)]) == D(-1)


def test_expectation_requires_actual_corroboration():
    evidence = [{"metric":key,"direction":"supports","nature":"guidance","period":date(2026,10,1)}
                for key in ("orders","shipments")]
    assert expectation(evidence,D(-5),D(10),100,D(1))["conclusion"] == "證據不足，暫不判斷"
    for record in evidence:
        record["nature"] = "actual"
    assert expectation(evidence,D(-5),D(10),100,D(1))["conclusion"] == "復甦具有基本面支撐"
    assert expectation(evidence,D(-5),D(10),None,D(1))["trigger"] is False


def test_eight_year_valuation_matches_existing_excel_fixture():
    r=project([D("2.02125")]*8,[D(".802")]*8,D("13.29"),D("129.17"),D(12))
    assert abs(r["irr_pct"]-D("-10.89870143900788"))<D("1e-9")
    assert len(r["cash_flows"])==9
    with pytest.raises(ValueError,match="100%"):
        project([D(1)]*8,[D(2)]*8,D(20),D(100),D(12))
    assert project([D(1)]*8,[D(2)]*8,D(20),D(100),D(12),allow_excess_payout=True)["payout_pct"] == 200
